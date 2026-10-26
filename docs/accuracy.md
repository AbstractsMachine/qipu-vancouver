# Accuracy

Two different questions get two different measurements: how well the model reads a page, and how often a published fact is
wrong. Both are below, with how they were measured and what they do not tell you.

## Reading a page

The reader was scored against gold pages: an answer key of the decisions on each page, written by a stronger model told to be
exhaustive. For Vancouver, 21 of the 48 key decisions were checked by hand against the scans, and all were right. The reader is
Claude Haiku with the prompts in `src/qipu_records/read/prompts/` and default thinking.

| | Vancouver (30 pages, 48 decisions) | San Francisco (40 pages, 117 decisions) |
|---|---|---|
| decisions found | 1.00 | 0.95 |
| items listed that are real decisions | 1.00 | 0.96 |
| number, action and vote counts all right | 0.98 | 0.95 |
| vote names exactly right | 0.98 | 0.95 |

These are small sets of mostly typed, well-scanned pages. Older handwritten or badly scanned volumes will do worse.

With thinking switched off, "all three right" fell to about 0.81 on both cities. The best open-weights model we tried, Gemma 4
26B on one GPU, scored 0.84 on San Francisco and 0.49 on Vancouver, where it made up roll-call counts for motions the minutes
only mark "CARRIED".

## Published facts

The October 2026 check drew a fresh random sample of facts from qipu's San Francisco dataset, about 34 facts per kind of fact
(seed 20261026), after the date, outcome and rezoning rules in this repository were applied. A fact was checked when it cites
an archive.org page: 287 of the 400 sampled. Each was compared with the OCR of its page and the two pages either side.

| kind of fact | checked | with a flaw | rate |
|---|---|---|---|
| reference to another item | 33 | 1 | 3% |
| rezoning | 26 | 1 | 4% |
| vote | 34 | 3 | 9% |
| amount of money | 34 | 4 | 12% |
| party to a decision | 34 | 4 | 12% |
| outcome | 30 | 6 | 20% |
| **kinds this extractor makes** | **191** | **19** | **9.9% (95% interval 6.5–15.0%)** |
| all kinds, including facts from directories and reports | 287 | 40 | 13.9% (10.4–18.4%) |

"With a flaw" means the checker found the fact wrong, or right about the decision but wrong in a detail. Only one of the 40 was
plainly wrong. The most common flaw was the date: 16 of the 40 overall, 11 of the 19 for decision facts. Eight came from
pages of a single 1999 volume that print no meeting header, so their dates were carried from earlier pages. Other patterns:
"excused" members recorded as "absent", and an outcome or a date taken from another line of the same item.

The same check before the date, outcome and rezoning rules gave 17.5% over all kinds; rezoning facts went from 45% flawed to 4%.

## How the checking was done, and its limits

- The checker was a model (Claude Sonnet) reading the page OCR, with a stronger model (Claude Opus) re-reading every fact the
  first one doubted and a tenth of the ones it accepted. Where they disagreed, the stronger model's verdict was used.
- A blind sheet of 50 of these facts for a human checker is prepared but has not been filled in. Until it is, treat the rates
  as the checker's opinion, not ground truth.
- The checker read OCR text, not images. A fact that matches garbled OCR but not the scan would pass.
- The sample is stratified by kind of fact, so the "all kinds" rate weights each kind equally, not by how common it is.
- Vancouver records from this reader have been scored on the gold pages above, but not yet checked on a random sample of a
  full run.

Every record carries its quote and a link to its page, so anyone can check one in a few seconds. Corrections are welcome as
issues.
