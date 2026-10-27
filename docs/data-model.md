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
