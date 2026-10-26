"""Command line: ``qipu-records fetch | read | build | gazetteer | demo``."""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from pathlib import Path

from qipu_records.cities import CITIES, get_city
from qipu_records.collection import Collection
from qipu_records.export.records import Context
from qipu_records.fetch.archive import ArchiveClient
from qipu_records.fetch.run import fetch_items
from qipu_records.map import gazetteer
from qipu_records.pipeline import build
from qipu_records.read.readers import AnthropicReader, OpenAICompatibleReader, Reader, ReaderConfigError, ReplayReader
from qipu_records.read.run import read_pages
from qipu_records.verify.privacy import Embargo


def _reader(args: argparse.Namespace) -> Reader:
    if args.replay:
        return ReplayReader(Path(args.replay))
    if args.base_url:
        return OpenAICompatibleReader(model=args.model, base_url=args.base_url, api_key_env=args.api_key_env)
    return AnthropicReader(model=args.model)


def _context(args: argparse.Namespace) -> Context:
    city = get_city(args.city)
    places = gazetteer.Gazetteer.load(Path(args.gazetteer)) if args.gazetteer else None
    return Context(city, Embargo(city.embargo_years), places)


def cmd_fetch(args: argparse.Namespace) -> int:
    added = fetch_items(Collection(Path(args.out)), ArchiveClient(Path(args.cache)), args.identifiers)
    print(f"pages added to {args.out}: {added}")
    return 0


def cmd_read(args: argparse.Namespace) -> int:
    count = read_pages(Collection(Path(args.out)), _reader(args), get_city(args.city), args.max_pages)
    print(f"pages read: {count}")
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    summary = build(_context(args), Collection(Path(args.out)))
    print(json.dumps(summary.as_dict(), indent=1))
    return 0


def cmd_gazetteer(args: argparse.Namespace) -> int:
    if args.city != "vancouver":
        print("only the Vancouver gazetteer can be downloaded for now", file=sys.stderr)
        return 2
    count = gazetteer.write_gazetteer(gazetteer.vancouver_rows(), Path(args.out))
    print(f"places written to {args.out}: {count}")
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    """Run read and build on the sample pages, with the model's recorded answers: no key, no network."""
    out, sample = Path(args.out), Path(args.sample)
    collection = Collection(out)
    for name in ("items.json", "pages.jsonl", "pagemaps.json"):
        shutil.copy(sample / name, out / name)
    collection.path("readings.jsonl").unlink(missing_ok=True)
    city = get_city("vancouver")
    read = read_pages(collection, ReplayReader(sample / "readings.jsonl"), city, max_pages=1000)
    places = gazetteer.Gazetteer.load(sample / "gazetteer.csv")
    summary = build(Context(city, Embargo(city.embargo_years), places), collection)
    print(f"pages read from recorded answers: {read}")
    print(json.dumps(summary.as_dict(), indent=1))
    print(f"output in {out}/: decisions.jsonl, decisions.geojson, rejected.jsonl, summary.json")
    return 0


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(prog="qipu-records", description=__doc__)
    top.add_argument("-v", "--verbose", action="store_true")
    sub = top.add_subparsers(dest="command", required=True)

    def command(name: str, help_text: str, out_default: str | None = None) -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--city", choices=sorted(CITIES), default="vancouver")
        p.add_argument("--out", required=out_default is None, default=out_default, help="the collection folder")
        return p

    p = command("fetch", "download items' OCR pages and page maps from archive.org")
    p.add_argument("identifiers", nargs="+", help="archive.org identifiers, e.g. 19740219")
    p.add_argument("--cache", default=".cache/archive", help="where archive.org downloads are kept")
    p.set_defaults(run=cmd_fetch)

    p = command("read", "have a model read the pages not read yet")
    p.add_argument("--max-pages", type=int, default=20, help="stop after this many pages (default 20)")
    p.add_argument("--model", default="claude-haiku-5-5")
    p.add_argument("--base-url", help="an OpenAI-compatible endpoint, e.g. http://localhost:8000/v1 for vLLM")
    p.add_argument("--api-key-env", default="OPENAI_API_KEY", help="the variable holding the key for --base-url")
    p.add_argument("--replay", help="a readings.jsonl of recorded answers to replay instead of calling a model")
    p.set_defaults(run=cmd_read)

    p = command("build", "turn readings into checked decision records")
    p.add_argument("--gazetteer", help="a gazetteer CSV (see the gazetteer command) to place decisions on the map")
    p.set_defaults(run=cmd_build)

    p = command("gazetteer", "download the city's addresses, intersections and neighbourhoods")
    p.set_defaults(run=cmd_gazetteer)

    p = command("demo", "run the pipeline on the bundled sample, offline", out_default="build/demo")
    p.add_argument("--sample", default="examples/vancouver", help="the sample folder")
    p.set_defaults(run=cmd_demo)
    return top


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(message)s")
    try:
        code: int = args.run(args)
    except ReaderConfigError as error:
        print(f"qipu-records: {error}", file=sys.stderr)
        return 2
    return code


if __name__ == "__main__":
    sys.exit(main())
