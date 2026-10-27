"""Reading loose values from open data (numbers as strings, blanks, free-text dates), and the most common of several."""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Hashable, Iterable
from typing import Any, Protocol, TypeVar

# A four-digit year from 1800 to 2099, anywhere in a text: "1925", "c. 1925", "1925-06-01", "1920s".
YEAR = re.compile(r"(1[89]\d\d|20\d\d)")


class _Sortable(Hashable, Protocol):
    def __lt__(self, other: Any, /) -> bool: ...


T = TypeVar("T", bound=_Sortable)


def as_int(v: Any) -> int | None:
    """A whole number from a number or a string such as " 1951 "; None for a blank, a fraction or anything else."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v) if v.is_integer() else None
    try:
        return int(str(v).strip())
    except ValueError:
        return None


def as_float(v: Any) -> float | None:
    """A finite number from a number or a string; None for anything else."""
    if v is None or isinstance(v, bool):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def as_positive(v: Any) -> float | None:
    """`as_float`, and None unless above zero: a height or a diameter of 0 means "not measured"."""
    x = as_float(v)
    return x if x is not None and x > 0 else None


def as_text(v: Any) -> str | None:
    """The value as a stripped string; None when that is empty."""
    s = str(v).strip() if v is not None else ""
    return s or None


def year_in(text: str | None) -> int | None:
    """The first year in a free-text date, or None."""
    m = YEAR.search(text or "")
    return int(m.group(1)) if m else None


def most_common(values: Iterable[T]) -> T | None:
    """The value given most often; a tie goes to the smallest, so the answer does not depend on the input's order."""
    counts = Counter(values)
    if not counts:
        return None
    return min(counts, key=lambda v: (-counts[v], v))
