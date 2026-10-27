# Privacy

Council minutes are public records, and publishing them is the point. But a record that was harmless in a bound volume on a
library shelf reads differently when it is one search away. A claim for an injury, a welfare case or an enforcement order
at someone's home can follow a person, or their family, for decades.

So qipu withholds names, not records. Every decision, every motion as printed and every page link is published. What is
withheld is the name of a private person, in a record about that person's sensitive matter, while the record is less than
100 years old.

## The rule

A record 100 years old or more is completely open: the cutoff is the current year minus 100, so 1926 in 2026. In a newer
record, one thing is masked: the name of a private person, and only when the record is about that person's sensitive
matter. The sensitive matters are:

- health;
- social or income assistance;
- a police or criminal matter, or an enforcement order at someone's home (nuisance, unsightly or unsafe premises);
- a person's debts, tax arrears, bankruptcy, damage or injury claim, or lawsuit against the City;
- a discrimination or harassment complaint;
- a child (foster care, juvenile, custody, adoption);
- the discipline or dismissal of an employee who is not an official.

The mask replaces the name with `[name withheld]`. Everything else stays.

These are never masked: councillors, the mayor, aldermen, city officials and staff acting in their role; delegations,
speakers, petitioners and letter writers addressing council; applicants and owners in rezoning, development, permit and
licence matters; businesses and organisations; contractors and payees; people honoured or named in ceremonies; places and
things named after people; and anything the minutes publish as part of the public record.

A land-use, permit, licence, contract, grant, appointment or honour record is never a sensitive matter, even when a
sensitive word appears in it. A record on a sensitive topic that names no private person (a policy report on the interest
rate for tax arrears) has nothing to mask.

A payee is masked only when the payment settles the sensitive matter itself: the payee of a damage claim is the claimant,
and the matter rule covers them. A payee in an ordinary payment stays named.

## Where it comes from

- **BC Freedom of Information and Protection of Privacy Act (FIPPA), s. 33(4)**: a public body may disclose personal
  information for archival or historical purposes if "the information is in a record that has been in existence for 100
  or more years". Hence records 100 years old or more are fully open; newer records follow s. 22.
  ([FIPPA Part 3](https://www.bclaws.gov.bc.ca/civix/document/id/complete/statreg/96165_03))
- **FIPPA s. 22(3)**: disclosure is presumed an unreasonable invasion of privacy when the information relates to a medical
  history or condition, to an investigation into a possible violation of law, to eligibility for income assistance or
  social service benefits, to employment history, or to a person's finances. These are the sensitive matters above.
  ([FIPPA Part 2](https://www.bclaws.gov.bc.ca/civix/document/id/complete/statreg/96165_02))
- **FIPPA s. 22(4)**: disclosure is not an unreasonable invasion when the information is about a person's position or
  functions as an officer or employee of a public body, a contract to supply goods or services to a public body, a licence
  or permit, or a discretionary benefit of a financial nature. Hence officials, contractors, payees, applicants and permit
  and licence holders are never masked. (same source)
- **Vancouver Charter s. 165.1**: "A meeting of the Council must be open to the public". The minutes are the public record
  of those meetings, so delegations, speakers and petitioners in public session, and the decisions themselves, are public.
- **City of Vancouver Archives practice**: finding aids for records with personal information restrict access "for 100
  years from creation date due to FOIPPA legislation"
  ([example](https://searcharchives.vancouver.ca/yearend-tax-statements)). The Archives restrict files of personal
  information, not council minutes, which are open on archive.org and council.vancouver.ca.

San Francisco records follow the same matters, with San Francisco's own cutoff of 75 years.

## How it is applied

`packages/records` applies the rule when it builds records (`qipu_records/verify/privacy.py`). The patterns for the seven
matters, the public-function test and the words that show a name in a public role are the rule's own, kept in that one
file. A name is looked for in the record's parties (except those in a public role: contractor, applicant, payee and so on)
and after a title ("Mr.", "Mrs.", "Miss", "Dr.") anywhere in its text. It is kept when it belongs to an official (the
mover, the seconder, the roll call, anyone named next to a role on the page), an organisation, or anyone the record shows
in a public role somewhere (after "letter from" or "delegation", before "Ltd." or "Street"). A claimant is always withheld,
even when an alderman on the page shares the surname. A withheld name is replaced in every form it is printed: "Miss
Jessie I. Hendry", "Jessie Hendry", "Miss Hendry", "Hendry's", except where that form is part of a firm's or a place's name.

`packages/updates` checks every release in both directions before publishing it (`qipu_updates/gates/privacy.py`):

- **Leak:** in every record about a sensitive matter and under 100 years old, the rule, run again on the published text,
  finds no private name still shown.
- **Over-redaction:** no mask in a record that is not about a sensitive matter or is 100 years old or more; none in the
  record's source, date, action or outcome, or on a mover, seconder or voter; none right after a word that shows a public
  role; none right before a firm, organisation, place or role word.

Either gate failing stops the release.

## Limits

- The matters are recognised from words. A sensitive matter described in words the patterns do not know will not be
  caught; a name the record never prints after a title and never lists as a party will not be found. Report any you find.
- Withholding applies to what is published: `decisions.jsonl`, `decisions.geojson`, `rejected.jsonl` and `summary.json`.
  The working files next to them, `pages.jsonl` and `readings.jsonl`, hold the page text and the model's answers as they
  came, names included; they are not for publishing. The scans themselves stay public on archive.org.
- The rule does not decide what is lawful to publish where you are. If you publish records built with these tools, the
  decision and the duty of care are yours.

## The sample

The pages in `examples/vancouver/` are inside the 100-year window. One of them records a claim by a private person. That
name was withheld in the sample's page text and in the recorded model answers before they were added to this repository,
using `qipu_records.verify.privacy.mask`, so the repository itself does not carry it.
