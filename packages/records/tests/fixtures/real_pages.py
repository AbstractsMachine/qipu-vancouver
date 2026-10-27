"""Lines from real City of Vancouver minutes pages on archive.org, kept just long enough to test verify/dates.py.

The text is the item's own OCR (`<prefix>_hocr_searchtext.txt.gz`, cut at its page index), unchanged, including its
spacing and mistakes. "Scan page" counts from 0, the way `fetch_page_texts` returns pages. To add one, see
CONTRIBUTING.md ("Adding a regression fixture").
"""

# https://archive.org/details/19741022, scan page 1: a running head with doubled spaces and stray marks after it.
RUNNING_HEAD_1974 = "Regular  Council,  October  22,  1974\n4  si'\n2\nUNFINISHED  BUSINESS\nThe  following  items "

# https://archive.org/details/19741022, scan page 0: the meeting opens on the page.
MEETING_OPENING_1974 = (
    "CITY  OF  VANCOUVER\nREGULAR  COUNCIL  MEETING\nA  regular  meeting  of  the  Council  of  the  City  of  "
    "Vancouver was  held  on  Tuesday,   October  22,   1974,   in  the  Council  Chamber, commencing  at  2.00  p.m.\n"
)

# https://archive.org/details/CVAN_1967-05-30, scan page 19: the last lines of one meeting (May 30) ...
CHANGE_BEFORE_1967 = (
    "20\nMAY 30 1967 Regular Council, May 30, 1967 ......... 4... ..6.. 2... . 20\nREPORTS (cont'd)\n"
    "x * x The above are the Minutes of Council dated May 30, 1967, and the ee appearing on For 'In Camera' Minutes "
    "pages -are those See Separate Minute Book.\n"
)
# ... and scan page 20, which opens a different meeting (Special Council, June 1).
CHANGE_AFTER_1967 = (
    "21\nJUN 1 1967 CITY OF VANCOUVER\nSPECIAL COUNCIL - JUNE Fs 1967 #1 Committee Room - 9:30 a.m.\n"
    "A Special Meeting of the Council of the City of Vancouver as held on Thursday, June 1, 1967, in the #1 Comm"
)

# https://archive.org/details/CVAN_1967-05-30, scan page 5: a clean running head ...
CLEAN_HEAD_1967 = "6\nMAY 3 0 1967 Regular Council, May 30, 1967 ........4.2.2.2.242.242.242.24"
# ... and scan page 6: the OCR read the day "30" as "50", so the head dates nothing and the page keeps May 30.
GARBLED_HEAD_1967 = "MAY 3 0 1967 Regular Council, May 50, 1967 et a? let es. Zo a as\n' REPORTS (cont'd)\n"

# https://archive.org/details/CVAN_1967-05-30, scan page 21: a clerk's "JUN 14 1967" stamp over the garbled head of the
# June 1 Special Council ("June 1l,."); the page belongs to the June 1 meeting that opened on scan page 20.
STAMP_OVER_GARBLED_HEAD_1967 = (
    "22\nJUN 14 1967 Special Council, June 1l,. 1967 wow ae wee Oe RR ee a eS le ee\n2. Railway Crossing\n"
    "Powell Street at Campbell Avenue\nAfter receiving a Report Reference from the City Engineer in regard to Clause 6 "
    "of the report of the Board of Administration (Works and Water matters), dated May 26, 1967, it was,\n"
    "MOVED by Ald. Bird,"
)
# https://archive.org/details/CVAN_1967-05-30, scan page 25: the same stamp beside a readable council head.
STAMP_BESIDE_COUNCIL_HEAD_1967 = (
    "26\nJUN 14 1967 Adjourned Council, June 1, 1967 .........4.2..+24424482424422\n"
    "Sale and Rezoning: (A & W Drive Ins) (cont'd)\n"
)
# https://archive.org/details/19700609, scan page 25: a Board of Administration report of June 5 bound into the minutes
# of the June 9 council meeting; the stamp names the meeting.
STAMP_OVER_REPORT_HEAD_1970 = (
    "'JUN   9  1970\nBOARD  OF  ADMINISTRATION     .   .   .  (WORKS)\nJUNE  5th,  1970.\n"
    "The  following  is  a  report  of  the  Board  of  Administration:\n"
)
