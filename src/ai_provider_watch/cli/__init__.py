from __future__ import annotations

import argparse
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from ai_provider_watch.core.feeds import (
    SEVERITY_RANK,
    artifact_diffs,
    build_artifacts,
    filter_events,
    load_events,
    write_artifacts,
)
from ai_provider_watch.core.io import package_data_root, read_json, repo_root, write_json_text
from ai_provider_watch.core.validation import validate
from ai_provider_watch.pipeline.candidates import (
    build_candidates,
    ensure_unique_candidate_ids,
    read_observation_bundle,
    write_candidate_files,
)
from ai_provider_watch.pipeline.ecosystem import ECOSYSTEM_TARGETS, build_ecosystem_mapping
from ai_provider_watch.pipeline.llm_review import (
    DEFAULT_REVIEWER,
    REVIEWER_BACKENDS,
    build_review_request,
    evaluate_review_result,
)
from ai_provider_watch.pipeline.notifications import build_slack_payload, build_webhook_payload
from ai_provider_watch.pipeline.release import parse_release_date, run_release_dry_run
from ai_provider_watch.pipeline.repo_impact import repo_impact_report
from ai_provider_watch.pipeline.review_pr import build_review_pr_body, read_candidate_files
from ai_provider_watch.source_watch.fixtures import validate_parser_fixtures
from ai_provider_watch.source_watch.http import (
    fetch_source,
    read_fingerprint_state,
    write_fingerprint_state,
    write_observations,
)
from ai_provider_watch.sources.registry import load_source_descriptors, validate_source_packages


def _root(value: str | None) -> Path:
    return repo_root(Path(value) if value else None)


def _is_package_data_root(root: Path) -> bool:
    try:
        return root.resolve() == package_data_root().resolve()
    except OSError:
        return False


def _require_checkout_root(args: argparse.Namespace, root: Path, command: str) -> bool:
    if args.root is None and _is_package_data_root(root):
        print(
            f"{command} requires an APW checkout; rerun inside a checkout or pass --root",
            file=sys.stderr,
        )
        return False
    return True


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
    if not _require_checkout_root(args, root, "index"):
        return 1
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


def cmd_source_test(args: argparse.Namespace) -> int:
    root = _root(args.root)
    issues = validate_source_packages(root) + validate_parser_fixtures(root)
    if issues:
        for issue in issues:
            print(issue.render(), file=sys.stderr)
        return 1
    packages = sorted((root / "sources").glob("*/source.json"))
    print(f"ok: validated {len(packages)} source packages and parser fixtures")
    return 0


def cmd_source_fetch(args: argparse.Namespace) -> int:
    root = _root(args.root)
    if not _require_checkout_root(args, root, "source fetch"):
        return 1
    state_path = root / args.state
    observations_path = _output_path(root, args.observations) if args.observations else None
    previous_state = read_fingerprint_state(state_path)
    sources = load_source_descriptors(root, enabled_only=True)
    if args.source:
        wanted = set(args.source)
        sources = [source for source in sources if source.key in wanted]
    observations = [
        fetch_source(
            source,
            previous_state,
            timeout=args.timeout,
            limit_bytes=args.limit_bytes,
        )
        for source in sources
    ]
    if observations_path:
        write_observations(observations_path, observations)
    if args.write_state:
        write_fingerprint_state(state_path, observations)

    changed = [observation.source_key for observation in observations if observation.changed]
    _print_json(
        {
            "source_count": len(observations),
            "changed_source_keys": changed,
            "state_path": str(state_path.relative_to(root)),
        }
    )
    return 0


def _path_from_root(root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return root / path


def _output_path(root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    if _is_package_data_root(root):
        return Path.cwd() / path
    return root / path


def cmd_candidate_generate(args: argparse.Namespace) -> int:
    root = _root(args.root)
    if not _require_checkout_root(args, root, "candidate generate"):
        return 1
    observations_path = _path_from_root(root, args.observations)
    output_dir = _output_path(root, args.output)
    try:
        result = build_candidates(
            read_observation_bundle(observations_path),
            load_source_descriptors(root, enabled_only=False),
            created_at=args.created_at,
        )
    except ValueError as exc:
        print(f"candidate generation failed: {exc}", file=sys.stderr)
        return 1
    try:
        ensure_unique_candidate_ids(result.candidates)
    except ValueError as exc:
        print(f"candidate generation failed: {exc}", file=sys.stderr)
        return 1
    if args.dry_run:
        _print_json(result.candidates)
        return 0

    try:
        written = write_candidate_files(output_dir, result.candidates, clean=args.clean)
    except (FileExistsError, ValueError) as exc:
        print(f"candidate generation failed: {exc}", file=sys.stderr)
        return 1
    _print_json(
        {
            "candidate_count": len(result.candidates),
            "written_paths": [str(path.relative_to(root)) if path.is_relative_to(root) else str(path) for path in written],
            "skipped_observations": result.skipped_observations,
        }
    )
    return 0


def cmd_candidate_review_pr_body(args: argparse.Namespace) -> int:
    root = _root(args.root)
    observations_path = _path_from_root(root, args.observations)
    candidate_dir = _path_from_root(root, args.candidates)
    validation_output = ""
    if args.validation_output:
        validation_output_path = _path_from_root(root, args.validation_output)
        if not validation_output_path.exists():
            print(f"validation output not found: {validation_output_path}", file=sys.stderr)
            return 1
        validation_output = validation_output_path.read_text(encoding="utf-8")
    body = build_review_pr_body(
        read_observation_bundle(observations_path),
        read_candidate_files(candidate_dir),
        root=root,
        validation_output=validation_output,
    )
    sys.stdout.write(body)
    return 0


def _created_at(value: str | None) -> str:
    if value:
        return value
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def cmd_review_request(args: argparse.Namespace) -> int:
    root = _root(args.root)
    candidate_dir = _path_from_root(root, args.candidates)
    try:
        request = build_review_request(
            read_candidate_files(candidate_dir),
            root=root,
            created_at=_created_at(args.created_at),
            reviewer=args.reviewer,
            model=args.model,
        )
    except ValueError as exc:
        print(f"review request failed: {exc}", file=sys.stderr)
        return 1
    output = write_json_text(request)
    if args.output:
        output_path = _output_path(root, args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output, encoding="utf-8")
    else:
        sys.stdout.write(output)
    return 0


def _schema_errors(root: Path, schema_filename: str, payload: Any) -> list[str]:
    schema = read_json(root / "schemas" / schema_filename)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [
        f"{'.'.join(str(part) for part in error.path) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(payload), key=lambda item: list(item.path))
    ]


def cmd_review_eval(args: argparse.Namespace) -> int:
    root = _root(args.root)
    request = read_json(_path_from_root(root, args.request))
    result = read_json(_path_from_root(root, args.result))
    errors = [
        *(f"request {error}" for error in _schema_errors(root, "llm-review-request.schema.json", request)),
        *(f"result {error}" for error in _schema_errors(root, "llm-review-result.schema.json", result)),
    ]
    if errors:
        for error in errors:
            print(f"review eval failed: {error}", file=sys.stderr)
        return 1
    report = evaluate_review_result(
        request,
        result,
        expected_candidate_ids=set(args.expected_candidate_id or []),
    )
    output = write_json_text(report)
    if args.output:
        output_path = _output_path(root, args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output, encoding="utf-8")
    else:
        sys.stdout.write(output)
    return 0 if report["passed"] else 1


def cmd_repo_check(args: argparse.Namespace) -> int:
    root = _root(args.root)
    try:
        report = repo_impact_report(
            root,
            Path(args.repo),
            since=args.since,
            risk=args.risk,
        )
    except ValueError as exc:
        print(f"repo check failed: {exc}", file=sys.stderr)
        return 1
    output = write_json_text(report)
    if args.output:
        output_path = _output_path(root, args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output, encoding="utf-8")
    else:
        sys.stdout.write(output)
    return 0


def _write_or_print(root: Path, payload: Any, output: str | None) -> None:
    rendered = write_json_text(payload)
    if output:
        output_path = _output_path(root, output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)


def cmd_notify_webhook(args: argparse.Namespace) -> int:
    root = _root(args.root)
    try:
        payload = build_webhook_payload(
            root,
            since=args.since,
            risk=args.risk,
            provider=args.provider,
            kind=args.kind,
            event_id=args.event_id,
            limit=args.limit,
            created_at=args.created_at,
            source_url=args.source_url,
        )
    except ValueError as exc:
        print(f"notify webhook failed: {exc}", file=sys.stderr)
        return 1
    _write_or_print(root, payload, args.output)
    return 0


def cmd_notify_slack(args: argparse.Namespace) -> int:
    root = _root(args.root)
    try:
        payload = build_slack_payload(
            root,
            since=args.since,
            risk=args.risk,
            provider=args.provider,
            kind=args.kind,
            event_id=args.event_id,
            limit=args.limit,
            created_at=args.created_at,
            source_url=args.source_url,
        )
    except ValueError as exc:
        print(f"notify slack failed: {exc}", file=sys.stderr)
        return 1
    _write_or_print(root, payload, args.output)
    return 0


def cmd_ecosystem_render(args: argparse.Namespace) -> int:
    root = _root(args.root)
    try:
        payload = build_ecosystem_mapping(
            root,
            target=args.target,
            since=args.since,
            risk=args.risk,
            provider=args.provider,
            kind=args.kind,
            event_id=args.event_id,
            limit=args.limit,
            created_at=args.created_at,
            source_url=args.source_url,
        )
    except ValueError as exc:
        print(f"ecosystem render failed: {exc}", file=sys.stderr)
        return 1
    _write_or_print(root, payload, args.output)
    return 0


def cmd_release_dry_run(args: argparse.Namespace) -> int:
    root = _root(args.root)
    if not _require_checkout_root(args, root, "release dry-run"):
        return 1
    try:
        release_date = parse_release_date(args.release_date)
    except ValueError as exc:
        print(f"release dry run failed: invalid --release-date: {exc}", file=sys.stderr)
        return 1
    try:
        result = run_release_dry_run(
            root,
            release_date=release_date,
            output_dir=_path_from_root(root, args.output),
            release_id=args.release_id,
            source_commit=args.source_commit,
            require_clean=args.require_clean,
        )
    except ValueError as exc:
        print(f"release dry run failed: {exc}", file=sys.stderr)
        return 1
    if result.failed_checks:
        for check in result.failed_checks:
            print(f"failed: {check.name}: {check.details}", file=sys.stderr)
        print(f"wrote release dry-run report: {result.report_path}", file=sys.stderr)
        return 1
    _print_json(
        {
            "release_id": result.report["release_id"],
            "check_count": len(result.report["checks"]),
            "artifact_count": len(result.report["release_artifacts"]),
            "report_path": str(result.report_path.relative_to(root))
            if result.report_path.is_relative_to(root)
            else str(result.report_path),
        }
    )
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

    source_parser = subparsers.add_parser("source", help="source package and fetch commands")
    source_subparsers = source_parser.add_subparsers(dest="source_command", required=True)
    source_test_parser = source_subparsers.add_parser("test", help="validate source packages")
    source_test_parser.set_defaults(func=cmd_source_test)
    source_fetch_parser = source_subparsers.add_parser("fetch", help="fetch enabled official sources")
    source_fetch_parser.add_argument(
        "--state",
        default="data/source-state/fingerprints.json",
        help="fingerprint state path relative to repo root",
    )
    source_fetch_parser.add_argument(
        "--observations",
        default=".apw/source-observations.json",
        help="observation output path relative to repo root",
    )
    source_fetch_parser.add_argument("--write-state", action="store_true")
    source_fetch_parser.add_argument("--source", action="append", help="limit to a source key")
    source_fetch_parser.add_argument("--timeout", type=float, default=20.0)
    source_fetch_parser.add_argument("--limit-bytes", type=int, default=1_000_000)
    source_fetch_parser.set_defaults(func=cmd_source_fetch)

    candidate_parser = subparsers.add_parser("candidate", help="candidate extraction commands")
    candidate_subparsers = candidate_parser.add_subparsers(dest="candidate_command", required=True)
    candidate_generate_parser = candidate_subparsers.add_parser(
        "generate",
        help="generate review candidates from source observations",
    )
    candidate_generate_parser.add_argument("--observations", required=True)
    candidate_generate_parser.add_argument("--output", default="data/candidates")
    candidate_generate_parser.add_argument("--created-at", required=True)
    candidate_generate_parser.add_argument("--clean", action="store_true")
    candidate_generate_parser.add_argument("--dry-run", action="store_true")
    candidate_generate_parser.set_defaults(func=cmd_candidate_generate)
    candidate_review_body_parser = candidate_subparsers.add_parser(
        "review-pr-body",
        help="render a draft candidate-review PR body",
    )
    candidate_review_body_parser.add_argument("--observations", required=True)
    candidate_review_body_parser.add_argument("--candidates", default="data/candidates/review")
    candidate_review_body_parser.add_argument("--validation-output")
    candidate_review_body_parser.set_defaults(func=cmd_candidate_review_pr_body)

    review_parser = subparsers.add_parser("review", help="LLM and agent review helper commands")
    review_subparsers = review_parser.add_subparsers(dest="review_command", required=True)
    review_request_parser = review_subparsers.add_parser(
        "request",
        help="render a bounded review-only request packet for Codex or another reviewer",
    )
    review_request_parser.add_argument("--candidates", default="data/candidates/review")
    review_request_parser.add_argument(
        "--reviewer",
        choices=sorted(REVIEWER_BACKENDS),
        default=DEFAULT_REVIEWER,
    )
    review_request_parser.add_argument(
        "--model",
        help="reviewer model identifier; defaults by reviewer backend",
    )
    review_request_parser.add_argument(
        "--created-at",
        help="RFC3339 timestamp for deterministic review packets; defaults to now in UTC",
    )
    review_request_parser.add_argument("--output", help="write JSON request to this path instead of stdout")
    review_request_parser.set_defaults(func=cmd_review_request)
    review_eval_parser = review_subparsers.add_parser(
        "eval",
        help="validate and score a review result against a review request",
    )
    review_eval_parser.add_argument("--request", required=True)
    review_eval_parser.add_argument("--result", required=True)
    review_eval_parser.add_argument(
        "--expected-candidate-id",
        action="append",
        help="candidate id expected to be found within the review packet window",
    )
    review_eval_parser.add_argument("--output", help="write JSON eval report to this path instead of stdout")
    review_eval_parser.set_defaults(func=cmd_review_eval)

    repo_parser = subparsers.add_parser("repo", help="downstream repository impact commands")
    repo_subparsers = repo_parser.add_subparsers(dest="repo_command", required=True)
    repo_check_parser = repo_subparsers.add_parser(
        "check",
        help="scan a downstream repo for refs affected by reviewed APW events",
    )
    repo_check_parser.add_argument("--repo", required=True, help="downstream repository path to scan")
    repo_check_parser.add_argument("--since", default="3650d", help="event date cutoff or day window")
    repo_check_parser.add_argument("--risk", choices=sorted(SEVERITY_RANK), help="minimum event severity")
    repo_check_parser.add_argument("--output", help="write JSON report to this path instead of stdout")
    repo_check_parser.set_defaults(func=cmd_repo_check)

    notify_parser = subparsers.add_parser("notify", help="render downstream notification payloads")
    notify_subparsers = notify_parser.add_subparsers(dest="notify_command", required=True)
    notify_webhook_parser = notify_subparsers.add_parser("webhook", help="render a generic webhook JSON payload")
    notify_slack_parser = notify_subparsers.add_parser("slack", help="render a Slack-compatible JSON payload")
    for payload_parser, default_limit in (
        (notify_webhook_parser, 20),
        (notify_slack_parser, 5),
    ):
        payload_parser.add_argument("--since", default="7d", help="event date cutoff or day window")
        payload_parser.add_argument("--risk", choices=sorted(SEVERITY_RANK), help="minimum event severity")
        payload_parser.add_argument("--provider", help="provider id or provider: ref")
        payload_parser.add_argument("--kind", help="event kind filter")
        payload_parser.add_argument("--event-id", help="single event id filter")
        payload_parser.add_argument("--limit", type=int, default=default_limit, help="maximum events to include")
        payload_parser.add_argument("--created-at", help="RFC3339 timestamp for deterministic payloads")
        payload_parser.add_argument(
            "--source-url",
            default="https://github.com/ottto-ai/ai-provider-watch",
            help="source URL to include in the payload",
        )
        payload_parser.add_argument("--output", help="write JSON payload to this path instead of stdout")
    notify_webhook_parser.set_defaults(func=cmd_notify_webhook)
    notify_slack_parser.set_defaults(func=cmd_notify_slack)

    ecosystem_parser = subparsers.add_parser("ecosystem", help="render ecosystem integration mapping payloads")
    ecosystem_subparsers = ecosystem_parser.add_subparsers(dest="ecosystem_command", required=True)
    ecosystem_render_parser = ecosystem_subparsers.add_parser(
        "render",
        help="render target-specific mapping payloads for catalog, gateway, or observability tools",
    )
    ecosystem_render_parser.add_argument("--target", required=True, choices=sorted(ECOSYSTEM_TARGETS))
    ecosystem_render_parser.add_argument("--since", default="7d", help="event date cutoff or day window")
    ecosystem_render_parser.add_argument("--risk", choices=sorted(SEVERITY_RANK), help="minimum event severity")
    ecosystem_render_parser.add_argument("--provider", help="provider id or provider: ref")
    ecosystem_render_parser.add_argument("--kind", help="event kind filter")
    ecosystem_render_parser.add_argument("--event-id", help="single event id filter")
    ecosystem_render_parser.add_argument("--limit", type=int, default=20, help="maximum events to include")
    ecosystem_render_parser.add_argument("--created-at", help="RFC3339 timestamp for deterministic payloads")
    ecosystem_render_parser.add_argument(
        "--source-url",
        default="https://github.com/ottto-ai/ai-provider-watch",
        help="source URL to include in the payload",
    )
    ecosystem_render_parser.add_argument("--output", help="write JSON payload to this path instead of stdout")
    ecosystem_render_parser.set_defaults(func=cmd_ecosystem_render)

    release_parser = subparsers.add_parser("release", help="release verification commands")
    release_subparsers = release_parser.add_subparsers(dest="release_command", required=True)
    release_dry_run_parser = release_subparsers.add_parser(
        "dry-run",
        help="verify and stage a local data release dry run without publishing",
    )
    release_dry_run_parser.add_argument("--release-date", help="release date as YYYY-MM-DD; defaults to today in UTC")
    release_dry_run_parser.add_argument(
        "--release-id",
        help="override CalVer release id; must match data-YYYY.MM.DD and --release-date",
    )
    release_dry_run_parser.add_argument("--source-commit", help="override source commit SHA for offline dry runs")
    release_dry_run_parser.add_argument("--output", default=".apw/release-dry-run")
    release_dry_run_parser.add_argument(
        "--require-clean",
        action="store_true",
        help="fail when tracked files are modified",
    )
    release_dry_run_parser.set_defaults(func=cmd_release_dry_run)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)
