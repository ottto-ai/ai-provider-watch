from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


def _max_severity(events: list[dict[str, Any]]) -> str | None:
    severities = [event.get("severity") for event in events if event.get("severity") in SEVERITY_RANK]
    if not severities:
        return None
    return max(severities, key=lambda value: SEVERITY_RANK[value])


def _summary(report: dict[str, Any]) -> str:
    events = report.get("events", [])
    lines = [
        "# AI Provider Watch",
        "",
        f"- Scanned files: {report.get('scanned_files', 0)}",
        f"- Matched refs: {len(report.get('matched_refs', []))}",
        f"- Impacting events: {len(events) if isinstance(events, list) else 0}",
        "",
    ]
    if not events:
        lines.append("No reviewed APW events matched this repository.")
        return "\n".join(lines) + "\n"
    lines.extend(
        [
            "| Severity | Date | Event | Matched refs |",
            "| --- | --- | --- | --- |",
        ]
    )
    for event in events:
        matched_refs = ", ".join(event.get("matched_refs", []))
        lines.append(
            f"| {event.get('severity')} | {event.get('event_date')} | "
            f"`{event.get('id')}` {event.get('title')} | `{matched_refs}` |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    parser.add_argument("--fail-on-severity", choices=sorted(SEVERITY_RANK))
    args = parser.parse_args(argv)

    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    events = report.get("events", [])
    events = events if isinstance(events, list) else []
    summary = _summary(report)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with Path(summary_path).open("a", encoding="utf-8") as handle:
            handle.write(summary)
    else:
        sys.stdout.write(summary)

    max_severity = _max_severity(events)
    if args.fail_on_severity and max_severity:
        if SEVERITY_RANK[max_severity] >= SEVERITY_RANK[args.fail_on_severity]:
            print(
                f"APW matched event severity {max_severity} >= {args.fail_on_severity}",
                file=sys.stderr,
            )
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
