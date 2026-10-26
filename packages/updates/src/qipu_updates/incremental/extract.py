"""Run qipu-records on one document: read the pages not read yet, then build its records.

This is the one place that drives the extractor. Reading costs money, so a run has a page budget shared by all its documents;
a document whose pages are not all read when the budget runs out is left for the next run, which picks up where this one
stopped (readings already made are kept).
"""

from __future__ import annotations

import datetime as dt
import hashlib
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path
from typing import Any, cast

from qipu_records.cities import City
from qipu_records.export.records import Context
from qipu_records.map.gazetteer import Gazetteer
from qipu_records.pipeline import build_records
from qipu_records.read.readers import Reader, Reading
from qipu_records.read.run import read_pages
from qipu_records.read.schema import prompt_version
from qipu_records.verify.privacy import Embargo
from qipu_updates.incremental.workspace import Workspace
from qipu_updates.sources import Document


@dataclass
class Budget:
    pages: int

    def spend(self, n: int) -> None:
        self.pages = max(0, self.pages - n)


@dataclass
class DocResult:
    doc: Document
    complete: bool
    pages_read: int = 0
    records: list[dict[str, Any]] = field(default_factory=list)
    rejected: int = 0


def _file_digest(path: Path | None) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12] if path else "none"


@dataclass(frozen=True)
class Extractor:
    city: City
    reader: Reader
    model: str
    """The model the reader uses: readings made by another model are not reused."""
    as_of: dt.date
    gazetteer_path: Path | None = None

    @property
    def prompt_version(self) -> str:
        return prompt_version(self.city.system_prompt())

    @property
    def embargo(self) -> Embargo:
        return Embargo(self.city.embargo_years, today=self.as_of)

    @property
    def build_key(self) -> str:
        """Changes when a document's records would come out differently from the same pages."""
        return "|".join(
            [
                f"qipu-records {metadata.version('qipu-records')}",
                self.prompt_version,
                self.model,
                f"gazetteer {_file_digest(self.gazetteer_path)}",
                f"embargo after {self.embargo.cutoff_year}",
            ]
        )

    def reusable(self, reading: Reading) -> bool:
        return reading.prompt_version == self.prompt_version and reading.model == self.model

    def context(self) -> Context:
        places = Gazetteer.load(self.gazetteer_path) if self.gazetteer_path else None
        return Context(self.city, self.embargo, places)

    def process(self, workspace: Workspace, doc: Document, budget: Budget, context: Context) -> DocResult:
        """Read and build the document's staged copy. Promote it with `Workspace.promote` once complete."""
        collection = workspace.collection(doc.doc_id, staged=True)
        waiting = workspace.unread(doc.doc_id, staged=True)
        stored = read_pages(collection, self.reader, self.city, budget.pages) if budget.pages and waiting else 0
        # read_pages returns the answers it stored; it may have sent up to min(budget, waiting) pages.
        budget.spend(min(budget.pages, waiting))
        if workspace.unread(doc.doc_id, staged=True):
            return DocResult(doc, complete=False, pages_read=stored)
        records, rejected, _ = build_records(context, collection)
        # From here a record is plain JSON, which gets a provenance block before it is released.
        return DocResult(
            doc, complete=True, pages_read=stored, records=cast(list[dict[str, Any]], records), rejected=len(rejected)
        )
