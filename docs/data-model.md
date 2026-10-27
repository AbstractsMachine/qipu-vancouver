# Data model

`build` writes one JSON object per line to `decisions.jsonl`. Text fields the page does not print are `null` or empty lists.

| field | meaning |
|---|---|
| `id` | `<archive.org item>:<OCR page>/<position on the page>`, stable for a given reading |
| `city`, `body` | which council |
| `date` | the meeting date, `YYYY-MM-DD`, from the minutes themselves |
| `date_source` | how the date was found: `meeting opens on the page`, `running head`, `carried from the meeting in progress`, `archive.org item date` or `none` |
| `kind` | `ordinance` (including by-laws), `resolution`, `motion`, `claim`, `appointment`, `permit`, `license`, `contract`, `hearing`, `appeal`, `charter_amendment`, `ballot_measure` or `other` |
| `number`, `file` | the by-law, ordinance or resolution number and the file number, as printed |
| `action` | the last action on the item on this page, as the model read it |
| `stage` | the step that action marks: `adopted`, `final passage`, `first reading`, `referred`, `continued`, `hearing`, ... |
| `outcome` | `passed`, `submitted to voters`, `refused`, `vetoed`, `veto overridden`, `withdrawn`, `pending` (still open on this page) or `unknown` |
| `amended` | whether the item was amended before the action |
| `zoning` | `rezoned` (final passage only), `rezoning proposed`, or `null` |
| `summary` | one plain sentence written by the model |
| `quote` | the first words of the item's heading, copied from the OCR |
| `quote_check` | `exact` or `fuzzy`: how the quote was found on the page. Items whose quote was not found are in `rejected.jsonl` instead |
| `vote` | `ayes`, `noes`, `absent` counts and names when a roll call is printed for the item, else `null`. Many minutes only say "CARRIED" |
| `mover`, `seconder` | as printed |
| `money` | amounts with `currency`, `purpose` and `payee` |
| `parties` | people and organisations with a role: `claimant`, `contractor`, `appointee`, `owner`, `applicant`, `payee`, `grantee`, `grantor`, `petitioner`, `employee`, `sponsor`, `other` |
| `places` | each place as printed, with its `precision`; placed ones add `lat`, `lon` and `placed_as` (`address`, `intersection` or `area`) |
| `topics` | broad subjects such as `housing`, `parks`, `transit` |
| `names_withheld` | `true` when a private person's name was withheld (see [privacy.md](privacy.md)) |
| `source` | `item`, `title`, `ocr_page`, `page_url` (the page in the archive.org viewer, or `null` when it cannot be placed exactly), `item_url`, `licence`, `archive` |
| `reading` | the `model` and `prompt_version` that read the page |
| `provenance` | in a release made by packages/updates only: the `run_id` that built the record, the `document` it came from, the document's `fingerprint`, and the `page_sha256` of the page text it was read from (see [updates.md](updates.md)) |

`decisions.geojson` has one point feature per placed place, with the record's `id`, `date`, `kind`, `outcome`, `summary`,
`quote`, `zoning`, `page_url` and amounts as properties.

`rejected.jsonl` lists the items the model gave whose quote could not be found on the page, with the quote, so they can be
looked at.

`summary.json` counts pages, pages read, decisions, rejected items, and how many records were found exactly or fuzzily,
dated, linked to a page, placed on the map and had names withheld.

## Block shards

The viewer can also read decisions already grouped by block, in the files qipu.org publishes for its whole-city maps under
`/data/<country>/<city>/city/`. Nothing in this repository writes them; the demo's sample in
`packages/viewer/demo/public/sample` is a cut of them. The parsers are `packages/viewer/src/data/{blocks,city,records}.ts`.
A folder holds:

| file                      | what                                                                                                                                                                                                                                                                                   |
| ------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `manifest.json`           | `proj`, the local projection of the outlines (`lon0`, `lat0`, `mpd` metres per degree of latitude, `cosl` = cos `lat0`), and `chunks`, whose entry with `kind: "blocks"` lists `hoodNames`                                                                                             |
| `base/blocks.qc`          | the block outlines, a QCT1 binary chunk (`src/data/qct.ts` documents the container): per block `cnt` vertices, `sc` scale, `ox`/`oy` origin and `z` ground height in decimetres, `hood` index into `hoodNames` (255 for none); per vertex `vx`/`vy` offsets in tenths of 2^`sc` metres |
| `base/blocks-id.json`     | the block ids in outline order: `id` (strings) or `block_idx` (numbers)                                                                                                                                                                                                                |
| `blocks/block-index.json` | one entry per block, in outline order: `b` ids (must equal `blocks-id.json`), `n` decisions placed, `y0`/`y1` first and last year (0 for none), and `meta.shards`, the number of shard files                                                                                           |
| `blocks/block-NN.json`    | the decisions of block number _i_ (its position in `b`) are in shard `i % meta.shards`, named with two digits: an object keyed by block id, each `{"d": [rows], "s": [street keys such as "PINE                                                                                        | ST"]}` |
| `blocks/block-money.json` | optional: `b`, places by block id, each with `slug`, `name`, `kind`, amounts `agreed` and `paid` (qipu.org's own files name them `agreed_usd` and `paid_usd` in every city), `n_contracts`; `currency` (ISO 4217) for the amounts; `href`, the place page pattern with `{slug}`        |

A shard row:

| field    | meaning                                                                                                                                                                                                                     |
| -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `y`      | the year                                                                                                                                                                                                                    |
| `d`      | `MM-DD`, or empty when the record gives no day                                                                                                                                                                              |
| `k`      | the record series, a code the city config names (`C` council vote, `N` council minutes, `P` building permit, `R` resolution, ...)                                                                                           |
| `p`      | how it was placed, 0 to 4: `street`, `corner`, `segment`, `address`, `stated` (the record names the block)                                                                                                                  |
| `a`      | the largest amount printed on the row, in the city's currency; 0 for none                                                                                                                                                   |
| `t`      | the record's own words                                                                                                                                                                                                      |
| `pl`     | optional, a plain-English reading of the record                                                                                                                                                                             |
| `hp`     | optional outcome: `d` decided, `n` pending, `f` failed, `u` unrecorded                                                                                                                                                      |
| `ad`     | optional, the address register's match, as `"349 E\|6TH\|AV"`                                                                                                                                                               |
| `u`, `c` | the citation and its system: no `c`, an Internet Archive volume (`u` = `<identifier>/<leaf>`); `b`, a San Francisco Clerk PDF (`<stem>/<page>`); `l`, a Legistar meeting (`<id>~<guid>/<page>`); `x`, `u` is the URL itself |
| `approx` | optional, `1` or `true` when the page link may be a page or two off                                                                                                                                                         |

Other fields in qipu.org's rows are ignored by the viewer.

When the viewer is given a `decisions.jsonl` instead (`CityConfig.data.decisions`), it builds the same index and rows from
it: `date` gives `y` and `d`, `kind` is the series, `quote` the words, `summary` the plain reading, the largest `money` amount
`a`, `outcome` the outcome (`passed`, `submitted to voters` and `veto overridden` are decided; `refused`, `vetoed` and
`withdrawn` failed; `unknown` unrecorded), and `source.page_url` (or `item_url`) the link. Each place with `lat` and `lon`
placed as an `address` or `intersection` puts the row on the block it falls in, or the nearest within 25 m; places placed
only as an `area`, and rows with no date, are left out.
