"""Keep published council records up to date.

A run finds what a source has published since the last release, extracts records from only the new and changed documents
(with qipu-records), checks the whole release, publishes it as a new version and keeps every earlier version for
rollback.
"""

__version__ = "0.1.0"
