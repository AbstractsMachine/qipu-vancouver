#!/bin/sh
# Fetch the Vancouver council meeting of 26 February 1974, read three pages and build the records.
# With Claude: export ANTHROPIC_API_KEY first. With a local open model: set BASE_URL and MODEL, e.g.
#   BASE_URL=http://localhost:8000/v1 MODEL=Qwen/Qwen3-32B sh examples/read_a_meeting.sh
set -eu

OUT=${OUT:-work/19740226}
qipu-records fetch --out "$OUT" 19740226

if [ -n "${BASE_URL:-}" ]; then
    qipu-records read --out "$OUT" --max-pages 3 --model "${MODEL:?set MODEL}" --base-url "$BASE_URL"
else
    qipu-records read --out "$OUT" --max-pages 3
fi

[ -f work/vancouver-places.csv ] || qipu-records gazetteer --out work/vancouver-places.csv
qipu-records build --out "$OUT" --gazetteer work/vancouver-places.csv
echo "records in $OUT/decisions.jsonl"
