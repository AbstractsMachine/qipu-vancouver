# Sample records

A cut of the block records qipu.org publishes, so the demo runs without a server of its own.
Built with `scripts/build-sample.mjs` from the site's data folders on 26 October 2026.

| folder | blocks | decisions | neighbourhoods | licence |
| --- | --- | --- | --- | --- |
| `sf/` | 343 | 10,473 | Mission, Haight Ashbury, Chinatown | qipu data, CC0. The records quoted are San Francisco Board of Supervisors proceedings, public domain. |
| `vancouver/` | 287 | 1,711 | Strathcona, Mount Pleasant | City of Vancouver records, CC BY 3.0 and the Open Government Licence – Vancouver: © City of Vancouver. |

Geometry (`base/`) and the block index are whole; only the decisions are cut, and blocks outside the
sample have a count of zero. The money file (`blocks/block-money.json`) names its amounts `agreed`, `paid` and
`payees_paid` and states their `currency` (USD for San Francisco, CAD for Vancouver); qipu.org's own files call
them `agreed_usd` and the like in both cities, and the viewer reads either. The full files are on www.qipu.org under `/data/us/sf/city` and
`/data/ca/vancouver/city`.

`vancouver/decisions.jsonl` is different: it is the output of `make -C packages/records demo` on the Vancouver example (two
meetings, 1970 and 1974), refreshed with `make records-sample`, and the demo reads it with `?decisions=sample`. It is the
format packages/records writes, not a cut of qipu.org's files.
