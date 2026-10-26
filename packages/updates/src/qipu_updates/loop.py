"""One scheduled run, start to finish.

    pause? due? lock -> discover -> plan -> for each new or changed document: fetch, read (budgeted), build
    -> assemble the release (carry over the rest, apply corrections) -> gates -> publish -> report

Every outcome ends in a report saved with the releases: published, no-change, refused (a gate failed), publish-paused,
dry-run, paused, not-due, busy or failed. A dry run writes nothing to the store.
"""

from __future__ import annotations

import datetime as dt
import shutil
from dataclasses import dataclass
from typing import Any

from qipu_updates.config import Config, format_every
from qipu_updates.gates.suite import run_all
from qipu_updates.incremental.extract import Budget, Extractor
from qipu_updates.incremental.plan import Built, Plan, listing_looks_short, make_plan
from qipu_updates.incremental.workspace import Workspace
from qipu_updates.monitor import metrics
from qipu_updates.monitor.metrics import RunReport
from qipu_updates.publish import Store
from qipu_updates.publish import releases as rel
from qipu_updates.release import corrections
from qipu_updates.release.assemble import Draft, assemble, stamp
from qipu_updates.release.manifest import Manifest, next_version
from qipu_updates.schedule import control
from qipu_updates.sources import Document, Source, SourceError


@dataclass(frozen=True)
class Options:
    run_id: str
    as_of: dt.date
    now: dt.datetime
    dry_run: bool = False
    force: bool = False
    """Run even when the source is not due."""
    publish: bool = True
    """False builds and checks but does not publish (the workflow's UPDATES_PUBLISH=off)."""


BuiltDocs = dict[str, tuple[Document, list[dict[str, Any]]]]


class WorkspacePages:
    """Page texts for the gates, read from the working copy."""

    def __init__(self, workspace: Workspace) -> None:
        self.workspace = workspace
        self._docs: dict[str, tuple[list[str], str | None] | None] = {}

    def document(self, doc_id: str) -> tuple[list[str], str | None] | None:
        if doc_id not in self._docs:
            found = None
            if self.workspace.has(doc_id):
                collection = self.workspace.collection(doc_id)
                found = ([p.text for p in collection.pages()], collection.items()[doc_id].date)
            self._docs[doc_id] = found
        return self._docs[doc_id]

    def text(self, page_id: str) -> str | None:
        doc_id, _, n = page_id.rpartition(":")
        document = self.document(doc_id)
        if document is None or not n.isdigit() or int(n) >= len(document[0]):
            return None
        return document[0][int(n)]


class Run:
    def __init__(self, config: Config, store: Store, workspace: Workspace, source: Source, extractor: Extractor) -> None:
        self.config, self.store, self.workspace, self.source, self.extractor = config, store, workspace, source, extractor

    def __call__(self, opts: Options) -> RunReport:
        report = RunReport(opts.run_id, self.config.name, opts.as_of.isoformat(), opts.now.isoformat(), dry_run=opts.dry_run)
        pause = control.paused(self.store)
        if pause and pause.scope == "all":
            return self._end(report, "paused", f"paused since {pause.since}: {pause.reason}", opts)
        if not opts.force and not control.due(control.last_check(self.store), self.config.source.every, opts.now):
            return self._end(report, "not-due", f"checked less than {format_every(self.config.source.every)} ago", opts)
        try:
            if not opts.dry_run:
                control.acquire(self.store, opts.run_id, opts.now)
        except control.BusyError as error:
            return self._end(report, "busy", str(error), opts)
        try:
            self._run(report, opts, publish_paused=bool(pause))
        except Exception as error:  # the report says what broke; the CLI exits non-zero so the alert fires
            report.status, report.detail = "failed", f"{type(error).__name__}: {error}"
        finally:
            if not opts.dry_run:
                control.release(self.store, opts.run_id)
        return self._end(report, report.status, report.detail, opts)

    def _end(self, report: RunReport, status: str, detail: str, opts: Options) -> RunReport:
        report.status, report.detail, report.finished = status, detail, dt.datetime.now(dt.UTC).isoformat()
        if not opts.dry_run:
            metrics.save(self.store, report)
        return report

    def _plan(self, previous: Manifest | None, opts: Options) -> Plan:
        found = self.source.discover(opts.as_of)
        known = previous.documents if previous else {}
        if listing_looks_short(len(found), len(known)):
            raise SourceError(f"the source lists {len(found)} documents, the last release had {len(known)}")
        return make_plan(found, {k: Built(v.fingerprint, v.build_key) for k, v in known.items()}, self.extractor.build_key)

    def _build(self, docs: tuple[Document, ...], report: RunReport) -> BuiltDocs:
        budget = Budget(self.config.reader.max_pages_per_run)
        context = self.extractor.context()
        built: BuiltDocs = {}
        for doc in docs:
            report.readings_reused += self.workspace.refresh(doc.doc_id, self.source.content(doc), self.extractor.reusable)
            result = self.extractor.process(self.workspace, doc, budget, context)
            report.pages_read += result.pages_read
            if not result.complete:
                report.documents_left.append(doc.doc_id)
                continue
            stamp(result.records, doc, report.run_id, self.workspace.page_hashes(doc.doc_id))
            built[doc.doc_id] = (doc, result.records)
            report.documents_built.append(doc.doc_id)
            report.rejected += result.rejected
        return built

    def _run(self, report: RunReport, opts: Options, publish_paused: bool) -> None:
        pointer = rel.current(self.store)
        previous = rel.manifest(self.store, pointer.version) if pointer else None
        plan = self._plan(previous, opts)
        report.plan = plan.counts()
        built = self._build(plan.work, report)
        if not opts.dry_run:
            control.mark_checked(self.store, opts.now)
        report.records_before = previous.counts.get("records", 0) if previous else 0
        rules_digest = corrections.digest(self.config.corrections)
        if previous and not built and previous.corrections_sha256 == rules_digest:
            report.status, report.records = "no-change", report.records_before
            report.detail = f"nothing new or changed since {previous.version}"
            return
        draft = self._assemble(previous, built, rules_digest, opts)
        results = run_all(
            draft,
            WorkspacePages(self.workspace),
            as_of=opts.as_of,
            embargo_years=self.extractor.city.embargo_years,
            records_before=report.records_before or None,
            limits=self.config.gate_limits,
        )
        draft.manifest.gates = {r.name: r.to_dict() for r in results}
        draft.write_manifest()
        report.release, report.records, report.gates = draft.manifest.version, len(draft.records), draft.manifest.gates
        failed = [r.name for r in results if not r.passed]
        if failed:
            report.status, report.detail = "refused", f"gates failed: {', '.join(failed)}; {draft.manifest.version} not published"
        elif opts.dry_run:
            report.status, report.detail = "dry-run", f"{draft.manifest.version} built and checked, not published"
        elif publish_paused or not opts.publish:
            report.status, report.detail = "publish-paused", f"{draft.manifest.version} built and checked; publishing is paused"
        else:
            rel.publish(self.store, draft.folder, draft.manifest, opts.now, opts.run_id)
            report.status, report.published = "published", True
            report.detail = f"{draft.manifest.version} published; documents rebuilt: {len(built)}"

    def _assemble(self, previous: Manifest | None, built: BuiltDocs, rules_digest: str, opts: Options) -> Draft:
        version = next_version(rel.versions(self.store), opts.as_of)
        drafts = self.workspace.root / "releases"
        shutil.rmtree(drafts, ignore_errors=True)
        header = Manifest(
            version=version,
            parent=previous.version if previous else None,
            created=opts.now.isoformat(),
            run_id=opts.run_id,
            city=self.extractor.city.key,
            source=self.config.source.kind,
            config_sha256=self.config.digest,
            build_key=self.extractor.build_key,
            corrections_sha256=rules_digest,
        )

        def read_previous(key: str) -> bytes:
            data = self.store.read(f"{rel.RELEASES}/{previous.version}/{key}") if previous else None
            if data is None:
                raise rel.PublishError(f"{key} of the published release is missing from the store")
            return data

        rules = corrections.load(self.config.corrections)
        return assemble(drafts / version, header, built=built, previous=previous, read_previous=read_previous, rules=rules)
