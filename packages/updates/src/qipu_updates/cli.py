"""Command line: ``qipu-updates run | status | releases | pause | resume | rollback | alert``.

Every command takes --config (a city's TOML file). --store replaces the config's publish target with a local folder,
which is how CI and the demo run without credentials.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import secrets
import sys
from pathlib import Path

from qipu_records.cities import get_city
from qipu_records.read.readers import ReaderConfigError
from qipu_updates.config import Config, ConfigError, format_every, load
from qipu_updates.incremental.extract import Extractor
from qipu_updates.incremental.workspace import Workspace
from qipu_updates.loop import Options, Run
from qipu_updates.monitor import alert, metrics
from qipu_updates.monitor.metrics import RunReport
from qipu_updates.publish import Store
from qipu_updates.publish import releases as rel
from qipu_updates.schedule import control
from qipu_updates.wiring import make_reader, make_source, make_store

EXIT = {"refused": 3, "failed": 1}


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(microsecond=0)


def _store(args: argparse.Namespace, config: Config) -> Store:
    return make_store(config.publish, Path(args.store) if args.store else None)


def _date(text: str) -> dt.date:
    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a date in YYYY-MM-DD form: {text!r}") from None


def _positive(text: str) -> int:
    if not text.isdigit() or int(text) < 1:
        raise argparse.ArgumentTypeError(f"must be a whole number of at least 1, not {text!r}")
    return int(text)


def cmd_run(args: argparse.Namespace, config: Config) -> int:
    """Run the source once: list, extract what changed, check, publish. Exit 0 when it succeeded, 3 when a gate refused,
    1 when it failed."""
    now = _now()
    if args.as_of:  # run as if today were that date: replays and tests
        now = dt.datetime.combine(args.as_of, now.timetz())
    as_of = now.date()
    run_id = args.run_id or f"{now:%Y%m%dT%H%M%SZ}-{secrets.token_hex(3)}"
    work = Path(args.work or Path(".updates-work") / config.name)
    try:
        city = get_city(config.city)
    except ValueError as error:
        raise ConfigError(f"[city] key: {error}") from error
    extractor = Extractor(city, make_reader(config.reader), config.reader.model, as_of, config.gazetteer)
    run = Run(config, _store(args, config), Workspace(work), make_source(config.source, work / "cache"), extractor)
    report = run(Options(run_id, as_of, now, dry_run=args.dry_run, force=args.force, publish=not args.no_publish))
    summary = metrics.markdown(report)
    print(summary)
    if args.summary:
        with Path(args.summary).open("a", encoding="utf-8") as out:
            out.write(summary)
    if args.report:
        Path(args.report).write_text(report.to_json(), encoding="utf-8")
    return EXIT.get(report.status, 0)


def cmd_status(args: argparse.Namespace, config: Config) -> int:
    """Print what is published, whether runs are paused, when the source was last checked and the latest runs."""
    store = _store(args, config)
    pointer = rel.current(store)
    pause = control.paused(store)
    print(f"published: {pointer.version + ' since ' + pointer.published if pointer else 'nothing yet'}")
    print(f"paused: {pause.scope + ' since ' + pause.since + ': ' + pause.reason if pause else 'no'}")
    last = control.last_check(store)
    print(f"last check: {last.isoformat() if last else 'never'} (every {format_every(config.source.every)})")
    for line in (store.read(metrics.METRICS) or b"").decode("utf-8").splitlines()[-args.last :]:
        run = json.loads(line)
        print(f"  {run['started']}  {run['status']:<14} {run.get('release') or '-':<14} {run['detail']}")
    return 0


def cmd_releases(args: argparse.Namespace, config: Config) -> int:
    """List the releases in the store, newest last, marking the published one and each one's gate result."""
    store = _store(args, config)
    pointer = rel.current(store)
    for version in rel.versions(store):
        found = rel.manifest(store, version)
        if found is None:
            continue
        mark = "*" if pointer and pointer.version == version else " "
        gates = "gates passed" if rel.gates_passed(found) else "gates FAILED"
        print(f"{mark} {version:<14} {found.counts.get('records', 0):>6} records  {gates}  run {found.run_id}")
    return 0


def cmd_pause(args: argparse.Namespace, config: Config) -> int:
    """Pause publishing (or all runs) until `resume`."""
    marker = control.pause(_store(args, config), args.scope, args.reason, _now())
    print(f"paused ({marker.scope}) since {marker.since}")
    return 0


def cmd_resume(args: argparse.Namespace, config: Config) -> int:
    control.resume(_store(args, config), _now())
    print("resumed")
    return 0


def cmd_rollback(args: argparse.Namespace, config: Config) -> int:
    """Point the published version at an earlier release and pause publishing so the next run does not undo it."""
    store = _store(args, config)
    pointer = rel.rollback(store, _now(), args.reason, args.to)
    print(f"latest is now {pointer.version} (was {pointer.previous})")
    if not args.keep_publishing:
        control.pause(store, "publish", f"rolled back from {pointer.previous}: {args.reason}", _now())
        print("publishing paused until `qipu-updates resume`, so the next run does not publish the same content again")
    return 0


def cmd_alert(args: argparse.Namespace, config: Config) -> int:
    """Open or update the GitHub issue for a failed scheduled run."""
    path = Path(args.report)
    if path.exists():
        summary = metrics.markdown(RunReport(**json.loads(path.read_text(encoding="utf-8"))))
    else:
        summary = f"### {config.name}: failed\n\nThe run stopped before it wrote a report; see the log."
    print(alert.raise_alert(alert.GhIssues(args.repo), config.name, summary, args.run_url))
    return 0


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(prog="qipu-updates", description=__doc__)
    sub = top.add_subparsers(dest="command", required=True)

    def command(name: str, help_text: str) -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--config", required=True, help="the city's TOML file")
        p.add_argument("--store", help="publish to this local folder instead of the config's target")
        return p

    p = command("run", "one scheduled run: find what changed, extract it, check, release, publish")
    p.add_argument("--work", help="the working copy kept between runs (default .updates-work/<name>)")
    p.add_argument(
        "--as-of",
        type=_date,
        help="run as if today were this date (YYYY-MM-DD): for replays and tests, on a scratch store",
    )
    p.add_argument("--run-id", default=os.environ.get("GITHUB_RUN_ID"))
    p.add_argument("--dry-run", action="store_true", help="do everything but write to the store")
    p.add_argument("--force", action="store_true", help="run even if the source is not due")
    p.add_argument("--no-publish", action="store_true", help="build and check, do not publish")
    p.add_argument("--summary", default=os.environ.get("GITHUB_STEP_SUMMARY"), help="append the report as Markdown")
    p.add_argument("--report", help="write the report as JSON")
    p.set_defaults(run=cmd_run)

    p = command("status", "what is published, whether paused, the last runs")
    p.add_argument("--last", type=_positive, default=10, help="how many recent runs to list")
    p.set_defaults(run=cmd_status)

    command("releases", "every release in the store; * marks the published one").set_defaults(run=cmd_releases)

    p = command("pause", "stop publishing (scope publish) or stop runs (scope all)")
    p.add_argument("--scope", choices=control.SCOPES, default="publish")
    p.add_argument("--reason", required=True)
    p.set_defaults(run=cmd_pause)

    command("resume", "undo pause").set_defaults(run=cmd_resume)

    p = command("rollback", "publish an earlier release again (default: the one before the current)")
    p.add_argument("--to", help="the version to go back to")
    p.add_argument("--reason", required=True)
    p.add_argument("--keep-publishing", action="store_true", help="do not pause publishing after the rollback")
    p.set_defaults(run=cmd_rollback)

    p = command("alert", "open or update the GitHub issue for a failed run")
    p.add_argument("--report", required=True, help="the JSON report written by run --report")
    p.add_argument("--run-url", required=True)
    p.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    p.set_defaults(run=cmd_alert)
    return top


def main(argv: list[str] | None = None) -> int:
    """Run one command. Exit 0 on success, 1 for a failed run, 2 for a bad config or setup, 3 for a refused release."""
    args = parser().parse_args(argv)
    try:
        code: int = args.run(args, load(Path(args.config)))
    except (ConfigError, ReaderConfigError) as error:
        print(f"qipu-updates: {error}", file=sys.stderr)
        return 2
    except FileNotFoundError as error:
        print(f"qipu-updates: no such file: {error.filename}", file=sys.stderr)
        return 2
    return code


if __name__ == "__main__":
    sys.exit(main())
