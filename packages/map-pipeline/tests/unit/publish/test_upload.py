import base64
import hashlib
import importlib
import threading
from pathlib import Path
from typing import Any

import pytest

from qipu_map.publish.upload import (
    LocalStore,
    PublishError,
    S3Store,
    Upload,
    content_type,
    describe,
    open_store,
    plan_upload,
    run_upload,
    s3_client,
)


class FakeS3:
    """The two calls S3Store makes, with S3's ETag and paging behaviour."""

    def __init__(self, page_size: int = 2, fail: str | None = None) -> None:
        self.objects: dict[str, dict[str, Any]] = {}
        self.order: list[str] = []
        self.page_size, self.fail = page_size, fail
        self.lock = threading.Lock()

    def list_objects_v2(self, *, Bucket: str, Prefix: str, ContinuationToken: str | None = None) -> dict[str, Any]:  # noqa: N803
        keys = sorted(k for k in self.objects if k.startswith(Prefix))
        start = int(ContinuationToken or 0)
        page = keys[start : start + self.page_size]
        out: dict[str, Any] = {"Contents": [{"Key": k, "ETag": f'"{self.objects[k]["md5"]}"'} for k in page]}
        if start + self.page_size < len(keys):
            out |= {"IsTruncated": True, "NextContinuationToken": str(start + self.page_size)}
        return out

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, **headers: str) -> None:  # noqa: N803
        if self.fail and Key.endswith(self.fail):
            raise OSError("connection reset")
        md5 = hashlib.md5(Body, usedforsecurity=False).digest()
        assert base64.b64decode(headers["ContentMD5"]) == md5
        with self.lock:
            self.objects[Key] = {"md5": md5.hex(), **headers}
            self.order.append(Key)


def _files(tmp_path: Path) -> tuple[dict[str, Path], dict[str, str]]:
    files = {}
    for key, body in [("today/0/0/0.webp", b"a"), ("today/1/0/0.webp", b"b"), ("switch/1950-2026/0/0/0.png", b"c"),
                      ("ground.json", b"{}"), ("manifest.json", b'{"format": "qipu-tiles/1"}')]:  # fmt: skip
        path = tmp_path / "src" / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        files[key] = path
    return files, {k: hashlib.md5(p.read_bytes(), usedforsecurity=False).hexdigest() for k, p in files.items()}


def _plan(tmp_path: Path, remote: dict[str, str]) -> list[Upload]:
    files, digests = _files(tmp_path)
    return plan_upload(
        files, digests, remote, cache_control="public, max-age=300", manifest_cache_control="public, max-age=60"
    )


def test_plan_puts_the_manifest_last_with_its_own_cache_header(tmp_path: Path) -> None:
    plan = _plan(tmp_path, {})
    assert [u.key for u in plan][-1] == "manifest.json"
    assert {u.key: u.cache_control for u in plan}["manifest.json"] == "public, max-age=60"
    assert {u.key: u.cache_control for u in plan}["today/0/0/0.webp"] == "public, max-age=300"
    assert {u.key: u.content_type for u in plan} == {
        "today/0/0/0.webp": "image/webp",
        "today/1/0/0.webp": "image/webp",
        "switch/1950-2026/0/0/0.png": "image/png",
        "ground.json": "application/json",
        "manifest.json": "application/json",
    }


def test_plan_skips_what_is_already_there(tmp_path: Path) -> None:
    files, digests = _files(tmp_path)
    remote = dict(digests) | {"today/1/0/0.webp": "0" * 32}
    plan = plan_upload(files, digests, remote, cache_control="c", manifest_cache_control="m")
    assert [u.key for u in plan] == ["today/1/0/0.webp"]


def test_plan_needs_a_manifest_and_known_types(tmp_path: Path) -> None:
    files, digests = _files(tmp_path)
    del files["manifest.json"]
    with pytest.raises(PublishError, match="manifest"):
        plan_upload(files, digests, {}, cache_control="c", manifest_cache_control="m")
    with pytest.raises(PublishError, match="content type"):
        content_type("a/b.tif")


def test_s3_upload_sends_headers_and_the_manifest_last(tmp_path: Path) -> None:
    s3 = FakeS3()
    store = S3Store(s3, "qipu-tiles", "/ca/vancouver/city/r1/")
    run_upload(store, _plan(tmp_path, store.md5s()), threads=4)
    assert s3.order[-1] == "ca/vancouver/city/r1/manifest.json"
    obj = s3.objects["ca/vancouver/city/r1/today/0/0/0.webp"]
    assert obj["ContentType"] == "image/webp"
    assert obj["CacheControl"] == "public, max-age=300"
    again = _plan(tmp_path, store.md5s())
    assert again == []


def test_s3_listing_pages_and_ignores_multipart_etags() -> None:
    s3 = FakeS3(page_size=1)
    s3.objects = {"p/a": {"md5": "1" * 32}, "p/b": {"md5": "abc-2"}, "p/c": {"md5": "3" * 32}, "q/d": {"md5": "4" * 32}}
    assert S3Store(s3, "bucket", "p").md5s() == {"a": "1" * 32, "c": "3" * 32}
    assert len(S3Store(s3, "bucket", "").md5s()) == 3


def test_a_failed_tile_keeps_the_old_manifest(tmp_path: Path) -> None:
    s3 = FakeS3(fail="1/0/0.webp")
    store = S3Store(s3, "b", "r1")
    with pytest.raises(PublishError, match="manifest was not updated"):
        run_upload(store, _plan(tmp_path, {}), threads=2)
    assert "r1/manifest.json" not in s3.objects
    assert "r1/today/0/0/0.webp" in s3.objects


def test_local_publish_copies_and_is_idempotent(tmp_path: Path) -> None:
    store = open_store(f"file://{tmp_path / 'site' / 'r1'}", "UNUSED")
    assert isinstance(store, LocalStore)
    assert store.md5s() == {}
    plan = _plan(tmp_path, store.md5s())
    run_upload(store, plan)
    assert (tmp_path / "site" / "r1" / "today" / "1" / "0" / "0.webp").read_bytes() == b"b"
    assert _plan(tmp_path, store.md5s()) == []
    assert isinstance(open_store(str(tmp_path), "UNUSED"), LocalStore)


def test_describe_lists_each_object(tmp_path: Path) -> None:
    lines = describe(_plan(tmp_path, {}))
    assert len(lines) == 5
    assert lines[-1].startswith("manifest.json  26 bytes  application/json")


def test_unknown_schemes_are_refused() -> None:
    with pytest.raises(PublishError, match="cannot publish"):
        open_store("gs://bucket/x", "UNUSED")


def test_s3_client_uses_the_endpoint_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("boto3", reason="boto3 is the optional 'publish' extra")
    monkeypatch.setenv("TEST_ENDPOINT", "https://example.r2.cloudflarestorage.com")
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    client = s3_client("TEST_ENDPOINT")
    assert client.meta.endpoint_url == "https://example.r2.cloudflarestorage.com"
    assert client.meta.region_name == "auto"
    store = open_store("s3://qipu-tiles/ca/vancouver", "TEST_ENDPOINT")
    assert isinstance(store, S3Store)
    assert store.bucket == "qipu-tiles"
    assert store.prefix == "ca/vancouver"


def test_s3_without_boto3_says_how_to_get_it(monkeypatch: pytest.MonkeyPatch) -> None:
    real = importlib.import_module

    def no_boto(name: str, package: str | None = None) -> Any:
        if name.startswith(("boto3", "botocore")):
            raise ImportError(name)
        return real(name, package)

    monkeypatch.setattr(importlib, "import_module", no_boto)
    with pytest.raises(PublishError, match=r"qipu-map\[publish\]"):
        s3_client("UNUSED")
