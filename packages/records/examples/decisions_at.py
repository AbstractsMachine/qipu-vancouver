"""Find decisions by place or outcome in a decisions.jsonl, with the standard library only.

python examples/decisions_at.py build/demo/decisions.jsonl --place Pendrell
python examples/decisions_at.py build/demo/decisions.jsonl --outcome refused
"""

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("records", type=Path)
    parser.add_argument("--place", default="", help="part of a place name, e.g. 'Pendrell'")
    parser.add_argument("--outcome", default="", help="passed, refused, pending, ...")
    args = parser.parse_args()
    with args.records.open(encoding="utf-8") as lines:
        for record in map(json.loads, lines):
            places = " ".join(place["text"] for place in record["places"])
            if args.place.lower() in places.lower() and args.outcome in record["outcome"]:
                print(f"{record['date']}  {record['outcome']:<8} {record['summary']}")
                print(f"            {record['source']['page_url']}")


if __name__ == "__main__":
    main()
