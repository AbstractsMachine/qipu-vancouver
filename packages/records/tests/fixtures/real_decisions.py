"""Passages of real City of Vancouver minutes on archive.org, for testing verify/fields.py and verify/quotes.py.

The text is as in examples/vancouver/pages.jsonl (archive.org's OCR, joined line by line), cut to the item tested.
"""

# https://archive.org/details/19700609, scan page 10: item 3, the Y.M.C.A. development permit application.
NO_FURTHER_ACTION_1970 = """3. Y.M.C.A. Building at 2617 East
Broadway: Use for Travelling Youth
and Young Men (Clause 8, Board of
Administration report, Building and
Planning matters, dated June 5, 19 70)
MOVED by Aid. Adams,
THAT no further action be taken on this development permit
application to permit the requested use of emergency sleeping
accommodation for travelling youth and young men during the summer
months ;
FURTHER THAT the Y.M.C.A. be congratulated for their efforts
to assist in this matter,
- CARRIED
"""

# https://archive.org/details/19700609, scan page 11: item 4, an amendment that was lost, then the main motion carried.
AMENDMENT_LOST_1970 = """4 . Social Assistance: I.W.A. Members
MOVED by Aid. Hardwick,
(a) THAT the Acting Social Service Administrator be requested
to act forthwith on the latest directive he has received from the
Provincial Authorities in Victoria in respect of this whole matter;
(Carried) *
MOVED by Aid. Phillips, in Amendment,
THAT the Acting Social Service Administrator be instructed
to follow the relevant Federal and Provincial laws on this matter.
- LOST
Alderman Hardwick 's motion was put and - CARRIED*
(During consideration of the foregoing business, the
Council recessed at approximately 4:30 p.m.
"""

# https://archive.org/details/19740219, scan page 1: the Birks Building, carried with one alderman against.
VOTED_AGAINST_1974 = """MOVED by Aid. Volrich,
THAT this whole matter be deferred pending a report from the
Board of Administration on:
(a) the City's legal position in the matter,
FURTHER THAT a Special Committee of Council be authorized to
meet with representatives of the Vancouver Centre Development Limited
to discuss the matter further.
- CARRIED
(Alderman Massey voted against the motion)
COMMUNICATIONS OR PETITIONS
"""

# https://archive.org/details/19700609, scan page 10 (top): the continued heading of Capilano Stadium ...
CONTINUED_HEADING_1970 = """DELEGATIONS , COMMUNICATIONS AND BOARD OF ADMINISTRATION
AND OTHER REPORTS (Cont'd.)
Capilano Stadium: Future Uses (Cont'd.)
After due consideration, it was
MOVED by Aid. Hardwick,
THAT the foregoing recommendations of the Sub-Committee of
the General Purposes Committee be adopted, subject to a program
of joint usage of the building facilities being worked out in
- CARRIED
"""
# ... and the bottom of scan page 9, where the item's text runs on from (archive.org hOCR, whitespace collapsed).
CONTINUED_FROM_1970 = """Capilano Stadium: Future Uses
The Sub-Committee of the General Purposes Committee
Subsequent to the last meeting of the Sub-Committee the Board
of Parks and Public Recreation passed the following resolution:
"""
# The quote and summary the model gave for it (examples/vancouver/readings.jsonl, 19700609:10, item 1).
CONTINUED_QUOTE_1970 = (
    "Capilano Stadium: Future Uses (Cont'd.) Subsequent to the last meeting of the Sub-Committee the Board"
)
CONTINUED_SUMMARY_1970 = (
    "Council adopted committee recommendations to trial Park Board operation of Capilano Stadium for summer 2019, "
    "with joint usage studied."
)
