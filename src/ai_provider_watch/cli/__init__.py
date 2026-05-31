from __future__ import annotations

import argparse
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from ai_provider_watch.core.feeds import (
    SEVERITY_RANK,
    artifact_diffs,
    build_artifacts,
    filter_events,
    load_events,
    write_artifacts,
)
from ai_provider_watch.core.io import repo_root, write_json_text
from ai_provider_watch.core.validation import validate


def _root(value: str | None) -> Path:
    return repo_root(Path(value) if value else None)


def _print_json(value: Any) -> None:
    sys.stdout.write(write_json_text(value))


def _parse_since(value: str) -> date:
    if value.endswith("d") and value[:-1].isdigit():
        return (datetime.now(UTC) - timedelta(days=int(value[:-1]))).date()
    return date.fromisoformat(value)


def cmd_validate(args: argparse.Namespace) -> int:
    root = _root(args.root)
    issues = validate(root)
    if issues:
        for issue in issues:
            print(issue.render(), file=sys.stderr)
        return 1
    print(f"ok: validated {root}")
    return 0


def cmd_index(args: argparse.Namespace) -> int:
    root = _root(args.root)
    artifacts = build_artifacts(root)
    if args.check:
        diffs = artifact_diffs(root, artifacts)
        if diffs:
            for path in diffs:
                print(f"out of date: {path}", file=sys.stderr)
            return 1
        print("ok: generated artifacts are current")
        return 0
    write_artifacts(root, artifacts)
    print(f"wrote {len(artifacts)} artifacts")
    return 0


def cmd_latest(args: argparse.Namespace) -> int:
    _print_json(filter_events(load_events(_root(args.root)), provider=args.provider, min_severity=args.risk)[: args.limit])
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    cutoff = _parse_since(args.since)
    events = filter_events(load_events(_root(args.root)), provider=args.provider)
    _print_json([event for event in events if date.fromisoformat(event["event_date"]) >= cutoff])
    return 0


def cmd_explain(args: argparse.Namespace) -> int:
    event = next((item for item in load_events(_root(args.root)) if item["id"] == args.event_id), None)
    if event is None:
        print(f"event not found: {args.event_id}", file=sys.stderr)
        return 1
    print(event["title"])
    print(f"{event['id']} | {event['event_kind']} | {event['severity']} | {event['confidence']}")
    print(f"\n{event['summary']}\n\nEvidence:")
    for evidence in event.get("evidence_refs", []):
        print(f"- {evidence['authority']}: {evidence['url']}")
    print("\nImpacts:")
    for impact in event.get("impacts", []):
        print(f"- {impact['scope_ref']} {impact['impact_kind']} {impact['direction']} ({impact['severity']}, {impact['confidence']})")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="apw")
    parser.add_argument("--root", help="APW repository root")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser("validate", help="validate schemas, registries, and events")
    validate_parser.set_defaults(func=cmd_validate)
    index_parser = subparsers.add_parser("index", help="generate feeds, indexes, and manifests")
    index_parser.add_argument("--check", action="store_true")
    index_parser.set_defaults(func=cmd_index)
    latest_parser = subparsers.add_parser("latest", help="print latest events as JSON")
    latest_parser.add_argument("--risk", choices=sorted(SEVERITY_RANK))
    latest_parser.add_argument("--provider")
    latest_parser.add_argument("--limit", type=int, default=20)
    latest_parser.set_defaults(func=cmd_latest)
    diff_parser = subparsers.add_parser("diff", help="print events since a date or window")
    diff_parser.add_argument("--since", default="7d")
    diff_parser.add_argument("--provider")
    diff_parser.set_defaults(func=cmd_diff)
    explain_parser = subparsers.add_parser("explain", help="explain one event")
    explain_parser.add_argument("event_id")
    explain_parser.set_defaults(func=cmd_explain)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)
