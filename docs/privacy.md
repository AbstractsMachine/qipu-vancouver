# Privacy

Council minutes are public records, and publishing them is the point. But a record that was harmless in a bound volume on a
library shelf reads differently when it is one search away. A claim for an injury, a welfare case or an eviction can follow a
person, or their family, for decades.

So qipu-records withholds names, not records. Everything is published except the names of private people in sensitive
matters, and only for records younger than the city's embargo.

## The rule

A name is replaced with `[name withheld]` when all of these hold:

- **The record is inside the embargo.** 92 years in Vancouver, 75 in San Francisco, counted back from today. Records with no
  date are treated as recent.
- **The matter is sensitive.** The item is a claim, has a claimant, or its heading or summary speaks of injury, damages,
  accidents, illness or hospital care, welfare or social assistance, eviction, nuisance, a lawsuit, a crime, an arrest, a victim,
  a prisoner or a child in care. The word list is `SENSITIVE` in `verify/privacy.py`.
- **The person is private.** Not the mover or seconder, not in the roll call, not named next to a public role on the page
  ("Ald. Linnell", "Mayor Phillips", "City Clerk Little"), and not an organisation (a firm, society, association, union,
  hospital, government body and the like).

Then the name is withheld in the quote, the summary, the parties, the payee of any amount, and the text of any place, in every
form it is printed: "Miss Jessie I. Hendry", "Jessie Hendry", "Miss Hendry", "Hendry's".

What stays: the decision, its date, its outcome, the amount and the address. Officials, businesses, petitioners, delegations
and applicants stay named, because they acted in public.

## Limits

- The sensitive-matter test matches words. It errs towards withholding, but a matter described in words it does not know will
  not be caught. Report any you find.
- Withholding applies to what this tool publishes. The page text it reads, and the scan itself, stay public on archive.org.
- The rule does not decide what is lawful to publish where you are. If you publish records built with this tool, the decision
  and the duty of care are yours.

## The sample

The pages in `examples/vancouver/` are inside Vancouver's embargo. One of them records a claim by a private person. That name
was withheld in the sample's page text and in the recorded model answers before they were added to this repository, using
`qipu_records.verify.privacy.mask`, so the repository itself does not carry it.
