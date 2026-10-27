"""Copy a release to its bucket (any S3-compatible store, such as Cloudflare R2) or to a local folder.

Rules:
- Compare MD5s before writing and skip what is already there. Re-running a publish after a small fix then costs a few
  writes, not thousands (each write is a billed operation on R2).
- Upload with threads in one process. Parallel processes (`gsutil -m`) crashed Python on macOS; 32 threads in one
  process moved about 2,000 tiles a minute where a single-threaded copy moved 170.
- Tiles first, manifest last, and only when every tile made it: a viewer that reads the new manifest finds every tile it
  names. Nothing is ever deleted, so a viewer still holding the old manifest keeps working too.
"""

from __future__ import annotations

import base64
import importlib
import logging
import os
import shutil
from collections.abc import Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

from qipu_map.hashing import file_digest

log = logging.getLogger(__name__)

CONTENT_TYPES = {".webp": "image/webp", ".png": "image/png", ".json": "application/json"}
MANIFEST_KEY = "manifest.json"
THREADS = 16


class Store(Protocol):
    def md5s(self) -> dict[str, str]:
        """The MD5 (hex) of every object already in the release, by key."""

    def put(self, item: Upload) -> None: ...


@dataclass(frozen=True)
class Upload:
    key: str
    source: Path
    md5: str
    content_type: str
    cache_control: str


class PublishError(RuntimeError):
    pass


def content_type(key: str) -> str:
    suffix = Path(key).suffix
    try:
        return CONTENT_TYPES[suffix]
    except KeyError:
        raise PublishError(f"no content type for {key!r}") from None


def plan_upload(
    files: Mapping[str, Path],
    digests: Mapping[str, str],
    remote: Mapping[str, str],
    *,
    cache_control: str,
    manifest_cache_control: str,
) -> list[Upload]:
    """The objects whose MD5 differs from the store's, sorted by key, with the manifest (if it changed) at the end."""
    if MANIFEST_KEY not in files:
        raise PublishError("a release needs its manifest.json")
    plan = []
    for key in sorted(files, key=lambda k: (k == MANIFEST_KEY, k)):
        if remote.get(key) == digests[key]:
            continue
        cache = manifest_cache_control if key == MANIFEST_KEY else cache_control
        plan.append(Upload(key, files[key], digests[key], content_type(key), cache))
    return plan


def run_upload(store: Store, plan: list[Upload], threads: int = THREADS) -> None:
    """Upload everything but the manifest in parallel; then the manifest, only if all of that succeeded."""
    body = [u for u in plan if u.key != MANIFEST_KEY]
    manifest = [u for u in plan if u.key == MANIFEST_KEY]
    failed: list[tuple[str, BaseException]] = []
    with ThreadPoolExecutor(max_workers=threads) as pool:
        futures = [(u.key, pool.submit(store.put, u)) for u in body]
        for key, future in futures:
            error = future.exception()
            if error is not None:
                failed.append((key, error))
    if failed:
        first_key, first_error = failed[0]
        raise PublishError(
            f"{len(failed)} of {len(body)} uploads failed (first: {first_key}: {first_error}); "
            "the manifest was not updated"
        )
    for u in manifest:
        store.put(u)


class LocalStore:
    """A release in a folder: for a local viewer, a test, or a disk that a web server serves."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def md5s(self) -> dict[str, str]:
        if not self.root.is_dir():
            return {}
        return {
            p.relative_to(self.root).as_posix(): file_digest(p, "md5")
            for p in sorted(self.root.rglob("*"))
            if p.is_file() and not p.name.endswith(".part")
        }

    def put(self, item: Upload) -> None:
        dest = self.root / item.key
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".part")
        shutil.copyfile(item.source, tmp)
        tmp.replace(dest)


class S3Store:
    """A release under s3://bucket/prefix. `client` is a boto3 S3 client (or anything with the same two calls)."""

    def __init__(self, client: Any, bucket: str, prefix: str) -> None:
        self.client, self.bucket, self.prefix = client, bucket, prefix.strip("/")

    def _key(self, key: str) -> str:
        return f"{self.prefix}/{key}" if self.prefix else key

    def md5s(self) -> dict[str, str]:
        out: dict[str, str] = {}
        start = f"{self.prefix}/" if self.prefix else ""
        kwargs: dict[str, Any] = {"Bucket": self.bucket, "Prefix": start}
        while True:
            page = self.client.list_objects_v2(**kwargs)
            for obj in page.get("Contents", []):
                etag = str(obj["ETag"]).strip('"')
                if "-" not in etag:  # a multipart ETag is not an MD5; such an object is simply uploaded again
                    out[str(obj["Key"])[len(start) :]] = etag
            if not page.get("IsTruncated"):
                return out
            kwargs["ContinuationToken"] = page["NextContinuationToken"]

    def put(self, item: Upload) -> None:
        self.client.put_object(
            Bucket=self.bucket,
            Key=self._key(item.key),
            Body=item.source.read_bytes(),
            ContentType=item.content_type,
            CacheControl=item.cache_control,
            ContentMD5=base64.b64encode(bytes.fromhex(item.md5)).decode("ascii"),
        )


def s3_client(endpoint_env: str, threads: int = THREADS) -> Any:
    """A boto3 client. Credentials come from the standard AWS_* variables; the endpoint (for R2) from `endpoint_env`."""
    try:
        boto3 = importlib.import_module("boto3")
        botocore_config = importlib.import_module("botocore.config")
    except ImportError as e:
        raise PublishError("publishing to s3:// needs boto3: pip install 'qipu-map[publish]'") from e
    endpoint = os.environ.get(endpoint_env) or None
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or ("auto" if endpoint else None)
    config = botocore_config.Config(max_pool_connections=threads, retries={"max_attempts": 8, "mode": "standard"})
    return boto3.client("s3", endpoint_url=endpoint, region_name=region, config=config)


def open_store(url: str, endpoint_env: str, threads: int = THREADS) -> Store:
    """s3://bucket/prefix, file:///path, or a plain path."""
    parsed = urlparse(url)
    if parsed.scheme == "s3":
        return S3Store(s3_client(endpoint_env, threads), parsed.netloc, parsed.path)
    if parsed.scheme == "file":
        return LocalStore(Path(parsed.path))
    if parsed.scheme == "":
        return LocalStore(Path(url))
    raise PublishError(f"cannot publish to {url!r}: use s3://bucket/prefix or a folder")


def describe(plan: Iterable[Upload]) -> list[str]:
    """One line per object a publish would write, for --dry-run."""
    return [f"{u.key}  {u.source.stat().st_size} bytes  {u.content_type}  {u.cache_control}" for u in plan]
