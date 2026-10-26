# qipu-records

City councils have kept minutes for more than a century, and many of them have been scanned and put on the Internet Archive.
They answer questions people still ask: who approved this building, when was this street widened, how did the vote go. But a
scan is hard to search, and its OCR text is harder still.

qipu-records turns those scans into structured decision records. A language model reads each page and lists the decisions on
it: what was decided, where, when, who moved it and how the vote went, and any amount of money. Plain code then checks every
record before it is published:

- the quote the model gave as evidence must be found on the page;
- the date comes from the meeting header printed in the minutes, not from the model;
- every record links to the exact page in the archive.org viewer, so anyone can check it against the scan;
- the names of private people in sensitive matters (a claim for damages, an illness, welfare) are withheld.

The repository has the extractor, those checks, a small map viewer, and a sample of real pages from the Vancouver City Council
minutes, scanned by the City of Vancouver Archives, so the whole thing runs offline in a few seconds.

**Live demo:** https://www.qipu.org/vancouver

![The map preview showing 1970s Vancouver council decisions](map-preview/screenshot.png)

## Quickstart

You need Python 3.11 or newer. Nothing else: the core uses only the standard library.

```sh
make demo     # reads the sample pages with recorded model answers, checks them, writes build/demo/
make serve    # then open http://localhost:8000/map-preview/
```

`make demo` needs no API key and no network. It runs the same code as a real run, with the model's answers replayed from
`examples/vancouver/readings.jsonl`. (The map page itself loads MapLibre and the basemap from the web.) It prints a summary:

```json
{
 "pages": 9,
 "pages_read": 9,
 "decisions": 33,
 "rejected": 0,
 "dated": 33,
 "linked_to_page": 33,
 "placed": 9,
 "quote_exact": 31,
 "quote_fuzzy": 2,
 "with_names_withheld": 1
}
```

One of the records it writes, shortened:

```json
{
  "id": "19740219:4/6",
  "date": "1974-02-19",
  "date_source": "running head",
  "kind": "other",
  "outcome": "passed",
  "summary": "Council approved acquiring 1139 Pendrell Street as a park site.",
  "quote": "Acquisition for Park Site - 1139 Pendrell Street",
  "quote_check": "exact",
  "mover": "Harcourt",
  "places": [{"text": "1139 Pendrell Street", "precision": "address", "lat": 49.281947, "lon": -123.130875, "placed_as": "address"}],
  "source": {
    "item": "19740219",
    "title": "Council Meeting Minutes : Feb. 19, 1974",
    "page_url": "https://archive.org/details/19740219/page/n4",
    "licence": "http://creativecommons.org/publicdomain/zero/1.0/"
  },
  "reading": {"model": "claude-haiku-5-5", "prompt_version": "v21-db2bcbe8fe"}
}
```

[docs/data-model.md](../../docs/data-model.md) describes every field.

## Reading more minutes

Install the package with the client for the model you want to use:

```sh
python -m venv .venv && . .venv/bin/activate
pip install -e '.[anthropic]'        # or '.[openai]' for an open-weights model behind an OpenAI-compatible server
```

Then fetch some meetings, read them, and build the records. The archive.org identifiers of the Vancouver minutes are listed in
the [City of Vancouver council minutes collection](https://archive.org/details/cityofvancouvercouncilminutes).

```sh
qipu-records fetch --out work/van 19740219 19740226
export ANTHROPIC_API_KEY=...                       # read from the environment only, never stored
qipu-records read --out work/van --max-pages 20
qipu-records gazetteer --out work/vancouver-places.csv
qipu-records build --out work/van --gazetteer work/vancouver-places.csv
```

`read` stops after `--max-pages` pages (20 by default), so a mistake costs cents. Pages already read are skipped, so you can
run it again to continue. With Claude Haiku a page costs about a fifth of a US cent.

To use an open-weights model instead, serve it with [vLLM](https://docs.vllm.ai) or [Ollama](https://ollama.com), or use a
hosted endpoint, and point `read` at it:

```sh
qipu-records read --out work/van --model Qwen/Qwen3-32B --base-url http://localhost:8000/v1
```

The model must support JSON-schema output. Open models follow the instructions less reliably than Claude. On the same test
pages the best one we tried, Gemma 4 26B on a single GPU, got 0.84 of San Francisco decisions fully right but only 0.49 of
Vancouver's, because it invented vote counts the minutes do not print. Check a sample before trusting a run.

San Francisco's Board of Supervisors is the second worked example (`--city san_francisco`), with the prompt used to read its
Journal of Proceedings from 1906 to 2016.

## How it works

The code is split by stage, in the order the data moves:

| stage | what it does |
|---|---|
| `fetch` | downloads an item's catalogue record and the OCR text of each page from archive.org, once |
| `read` | sends each page to the model, which lists the decisions on it with a quote for each |
| `verify` | finds the quote on the page, dates the item from the meeting header, names the outcome, withholds private names |
| `link` | turns the OCR page number into the page the archive.org viewer shows |
| `map` | places the decision from the address, corner or neighbourhood it names |
| `export` | writes `decisions.jsonl`, `decisions.geojson` for the map, and a summary of every check |

The model is the only step that guesses. Everything after it is deterministic and tested. [ARCHITECTURE.md](ARCHITECTURE.md)
has the diagram and explains each step and why it is there.

## Tests

```sh
make install   # .venv with the pinned development tools
make check     # ruff, mypy --strict, unit and integration tests with coverage (fails under 85%)
make e2e       # make demo, then the map page in headless Chromium, with its archive.org links checked
```

## How accurate it is

We check what we publish against the pages, on a fixed random sample, and publish the result.

- **Reading a page.** On test pages with an answer key, the reader found every decision on 30 Vancouver pages and got the item number,
  the action and the vote counts all right for 0.98 of 48 decisions. On 40 San Francisco pages it found 0.95 of 117 decisions
  and got all three right on 0.95 of those.
- **Published facts.** In the latest check of qipu's San Francisco dataset, built with this method, about **1 in 7 facts had
  a flaw**: 40 of 287 checkable facts, 13.9% (95% interval 10.4–18.4%). Only one was plainly wrong. Most were right about the
  decision but wrong about something next to it, and the most common flaw was the date (16 of the 40), mostly on pages that
  print no meeting header. That dataset also holds facts read from city directories and reports. Counting only the kinds of
  fact this extractor makes (votes, amounts, parties, outcomes, rezonings and references to other items), it was about 1 in 10:
  19 of 191, 9.9% (6.5–15.0%), and 11 of those 19 were dates.
- **Who checked.** The sample was checked by a model reading the page OCR, with a stronger model re-checking every fact the
  first one doubted. A blind human check of 50 of those facts is prepared but not done yet. Vancouver records have been
  checked on the gold pages above but not yet on a random sample of a full run.

[docs/accuracy.md](../../docs/accuracy.md) has the method, the tables and the known failure patterns.

## Privacy

Council minutes are public records, and most names in them belong to officials, firms and groups acting in public. They stay.
In sensitive matters (a claim for damages, an injury, an illness, welfare, an eviction, a crime) a private person's name is
replaced with `[name withheld]` in everything published, for records younger than the city's embargo: 92 years in Vancouver,
75 in San Francisco. The decision, its place, amount and outcome stay visible. [docs/privacy.md](../../docs/privacy.md) explains the
rule and its limits. The sample in this repository already has those names withheld; the full text remains on archive.org.

## Limitations

- OCR errors pass through. A misread amount or name in the scan's text will be in the record, though the quote and the page
  link make it easy to see.
- Dates are only as good as the headers. A page without a printed header takes the meeting in progress from the page before,
  which is usually right and sometimes not.
- Only places that still exist as an address, a corner or a neighbourhood are put on the map. Old addresses, landmarks and
  streets named without a number are kept in the record but not placed.
- The privacy rule matches words. It withholds too much rather than too little, but it can miss a sensitive matter described
  in words it does not know.
- The gazetteer download covers Vancouver. San Francisco records are built without map points unless you supply a gazetteer.

## Data and licences

The code is under the [Apache License 2.0](../../LICENSE). The records it produces, and the records in `examples/vancouver/`, are dedicated to
the public domain under [CC0 1.0](../../LICENSE-DATA). The sample's page text comes from scans the City of Vancouver Archives
published on archive.org under CC0; the sample gazetteer is City of Vancouver open data under the Open Government Licence –
Vancouver. See [examples/vancouver](../../examples/vancouver).

## Credits

The scans and their OCR are the work of the [Internet Archive](https://archive.org) and the libraries and archives that
digitised the records: the [City of Vancouver Archives](https://searcharchives.vancouver.ca) and the
[San Francisco Public Library](https://sfpl.org). Addresses and neighbourhoods come from the
[City of Vancouver Open Data Portal](https://opendata.vancouver.ca). The map uses [MapLibre GL JS](https://maplibre.org) and
[OpenFreeMap](https://openfreemap.org) tiles built from [OpenStreetMap](https://www.openstreetmap.org/copyright) data.

qipu-records is the extraction core of [qipu](https://www.qipu.org), which publishes San Francisco's decisions as open data at
[data.qipu.org](https://data.qipu.org). See [CONTRIBUTING.md](../../CONTRIBUTING.md) to help.
