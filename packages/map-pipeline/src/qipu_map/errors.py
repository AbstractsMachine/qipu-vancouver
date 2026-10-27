"""The one error a stage raises for an expected failure: an input missing, a file it cannot use, a bad option.

`qipu-map` prints its message on one line and exits with status 2; anything else is a bug and shows its traceback.
"""

from __future__ import annotations


class StageError(Exception):
    """A stage cannot run as asked. The message says what is wrong and, where there is one, the command that fixes
    it."""
