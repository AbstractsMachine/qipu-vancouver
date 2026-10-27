"""The `qipu-map` command: one sub-command per stage, in the order the data moves."""

from __future__ import annotations

import argparse
import importlib
import logging
import sys
from collections.abc import Sequence

from qipu_map.errors import StageError

STAGES = ("ingest", "scene", "render", "paint", "tiles", "eras", "publish")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qipu-map", description=__doc__)
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    for stage in STAGES:
        importlib.import_module(f"qipu_map.{stage}.command").register(sub)
    importlib.import_module("qipu_map.sample").register(sub)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    try:
        result: int = args.run(args)
    except StageError as e:
        sys.stderr.write(f"qipu-map {args.command}: {e}\n")
        return 2
    return result


if __name__ == "__main__":
    sys.exit(main())
