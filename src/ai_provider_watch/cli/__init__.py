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
    build_release_evidence_index,
    filter_events,
    load_events,
    write_artifacts,
)
from ai_provider_watch.core.io import package_data_root, read_json, repo_root, write_json_text
from ai_provider_watch.core.remote import (
    JSON_REMOTE_ARTIFACTS,
    REMOTE_ARTIFACTS,
    RemoteFeedError,
    fetch_remote_json,
    fetch_remote_text,
)
from ai_provider_watch.core.validation import validate
from ai_provider_watch.pipeline.agent_dashboard import build_agent_dashboard
from ai_provider_watch.pipeline.candidate_event_packet import build_candidate_to_event_packet
from ai_provider_watch.pipeline.candidate_queue import (
    build_candidate_action_queue,
    render_candidate_action_queue_markdown,
)
from ai_provider_watch.pipeline.candidate_scaffold import (
    CandidateScaffoldError,
    build_candidate_event_scaffold,
    render_candidate_event_scaffold_command,
)
from ai_provider_watch.pipeline.candidates import (
    build_candidates,
    ensure_unique_candidate_ids,
    read_observation_bundle,
    write_candidate_files,
)
from ai_provider_watch.pipeline.coverage import build_source_coverage_report
from ai_provider_watch.pipeline.ecosystem import ECOSYSTEM_TARGETS, build_ecosystem_mapping
from ai_provider_watch.pipeline.event_scaffold import (
    DETAIL_KIND_TO_EVENT_KINDS,
    EventScaffoldError,
    build_event_scaffold,
    sha256_file,
)
from ai_provider_watch.pipeline.launch_gate import build_v1_launch_gate
from ai_provider_watch.pipeline.llm_review import (
    DEFAULT_REVIEWER,
    REVIEW_DECISIONS,
    REVIEWER_BACKENDS,
    build_review_request,
    evaluate_review_result,
)
from ai_provider_watch.pipeline.missing_event_issue import (
    build_missing_event_issue_triage,
    render_missing_event_issue_triage_markdown,
)
from ai_provider_watch.pipeline.notifications import build_slack_payload, build_webhook_payload
from ai_provider_watch.pipeline.operations import build_operations_report
from ai_provider_watch.pipeline.promotion import build_promotion_readiness_report
from ai_provider_watch.pipeline.quality import (
    build_candidate_quality_report,
    build_reviewed_evidence_index,
    duplicate_event_ids_for_candidate,
)
from ai_provider_watch.pipeline.release import (
    build_release_automation_readiness,
    build_release_publication_packet,
    parse_release_date,
    run_release_dry_run,
    verify_release_artifacts,
)
from ai_provider_watch.pipeline.repo_impact import repo_impact_report
from ai_provider_watch.pipeline.review_pr import build_review_pr_body, read_candidate_files
from ai_provider_watch.pipeline.source_owner_packet import build_source_owner_packet
from ai_provider_watch.pipeline.source_refresh_gate import (
    build_source_refresh_review_gate_from_files,
    render_source_refresh_review_gate_summary,
    write_github_output,
)
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


def cmd_freshness(args: argparse.Namespace) -> int:
    root = _root(args.root)
    path = root / "data" / "feeds" / "freshness.json"
    if not path.exists():
        print("freshness metadata not found; run apw index from a checkout", file=sys.stderr)
        return 1
    freshness = read_json(path)
    if args.summary:
        print(f"release_id: {freshness['release_id']}")
        print(f"data_tag: {freshness['data_tag'] or 'none'}")
        print(f"package_version: {freshness['package_version']}")
        print(f"generated_at: {freshness['generated_at']}")
        print(f"event_count: {freshness['event_count']}")
        print(f"latest_event_date: {freshness['latest_event_date'] or 'none'}")
        print(f"latest_observed_at: {freshness['latest_observed_at']}")
        print(f"source_state_latest_retrieved_at: {freshness['source_state']['latest_retrieved_at'] or 'none'}")
        print(f"checksums_path: {freshness['release_artifacts']['checksums_path']}")
    else:
        _print_json(freshness)
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


def cmd_event_scaffold(args: argparse.Namespace) -> int:
    root = _root(args.root)
    try:
        content_sha256 = args.content_sha256 or sha256_file(Path(args.content_text_file))
        event = build_event_scaffold(
            event_id=args.event_id,
            event_date=args.event_date,
            provider=args.provider,
            event_kind=args.kind,
            title=args.title,
            summary=args.summary,
            source_url=args.source_url,
            source_key=args.source_key,
            source_authority=args.source_authority,
            content_sha256=content_sha256,
            scope_type=args.scope_type,
            scope_ref=args.scope_ref,
            impact_kind=args.impact_kind,
            direction=args.direction,
            severity=args.severity,
            confidence=args.confidence,
            observed_at=args.observed_at,
            lifecycle_status=args.lifecycle_status,
            date_confidence=args.date_confidence,
            announced_at=args.announced_at,
            effective_at=args.effective_at,
            expires_at=args.expires_at,
            migration_deadline=args.migration_deadline,
            detail_kind=args.detail_kind,
            model_refs=args.model_ref,
            replacement_refs=args.replacement_ref,
            lifecycle_action=args.lifecycle_action,
            migration_notes=args.migration_notes,
            new_default=args.new_default,
            old_default=args.old_default,
            status=args.status,
            components=args.component,
            subscription_impact=args.subscription_impact,
            api_usage_impact=args.api_usage_impact,
            who_should_care=args.who,
            recommended_action=args.recommended_action,
            selector=args.selector,
            snapshot_ref=args.snapshot_ref,
            license_note=args.license_note,
            tags=args.tag,
            limitations=args.limitation,
        )
    except (OSError, EventScaffoldError) as exc:
        print(f"event scaffold failed: {exc}", file=sys.stderr)
        return 1
    _write_or_print(root, event, args.output)
    return 0


def cmd_event_issue_triage(args: argparse.Namespace) -> int:
    root = _root(args.root)
    try:
        issue_body = Path(args.issue_body).read_text(encoding="utf-8")
    except OSError as exc:
        print(f"event issue-triage failed: {exc}", file=sys.stderr)
        return 1
    triage = build_missing_event_issue_triage(issue_body)
    if args.format == "json":
        _write_or_print(root, triage.as_dict(), args.output)
        return 0
    rendered = render_missing_event_issue_triage_markdown(triage)
    if args.output:
        output_path = _output_path(root, args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


def _expect_remote_list(value: Any, *, artifact: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise RemoteFeedError(f"remote {artifact} feed is not a JSON array")
    return value


def _expect_remote_dict(value: Any, *, artifact: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RemoteFeedError(f"remote {artifact} feed is not a JSON object")
    return value


def cmd_remote_latest(args: argparse.Namespace) -> int:
    try:
        events = _expect_remote_list(
            fetch_remote_json(
                "events",
                ref=args.ref,
                timeout=args.timeout,
                limit_bytes=args.limit_bytes,
            ),
            artifact="events",
        )
    except (RemoteFeedError, ValueError) as exc:
        print(f"remote latest failed: {exc}", file=sys.stderr)
        return 1
    _print_json(filter_events(events, provider=args.provider, min_severity=args.risk)[: args.limit])
    return 0


def cmd_remote_freshness(args: argparse.Namespace) -> int:
    try:
        freshness = _expect_remote_dict(
            fetch_remote_json(
                "freshness",
                ref=args.ref,
                timeout=args.timeout,
                limit_bytes=args.limit_bytes,
            ),
            artifact="freshness",
        )
    except (RemoteFeedError, ValueError) as exc:
        print(f"remote freshness failed: {exc}", file=sys.stderr)
        return 1
    if args.summary:
        print(f"release_id: {freshness['release_id']}")
        print(f"data_tag: {freshness['data_tag'] or args.ref}")
        print(f"package_version: {freshness['package_version']}")
        print(f"event_count: {freshness['event_count']}")
        print(f"latest_event_date: {freshness['latest_event_date'] or 'none'}")
    else:
        _print_json(freshness)
    return 0


def cmd_remote_feed(args: argparse.Namespace) -> int:
    root = _root(args.root)
    try:
        if args.name in JSON_REMOTE_ARTIFACTS:
            output = write_json_text(
                fetch_remote_json(
                    args.name,
                    ref=args.ref,
                    timeout=args.timeout,
                    limit_bytes=args.limit_bytes,
                )
            )
        else:
            output = fetch_remote_text(
                args.name,
                ref=args.ref,
                timeout=args.timeout,
                limit_bytes=args.limit_bytes,
            )
    except (RemoteFeedError, ValueError) as exc:
        print(f"remote feed failed: {exc}", file=sys.stderr)
        return 1
    if args.output:
        output_path = _output_path(root, args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output, encoding="utf-8")
    else:
        sys.stdout.write(output)
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
    if args.include_disabled and args.write_state:
        print(
            "source fetch failed: --include-disabled is maintainer-smoke only and cannot be combined with --write-state",
            file=sys.stderr,
        )
        return 1
    if args.include_disabled and not args.source:
        print("source fetch failed: --include-disabled requires at least one --source", file=sys.stderr)
        return 1
    state_path = root / args.state
    observations_path = _output_path(root, args.observations) if args.observations else None
    previous_state = read_fingerprint_state(state_path)
    sources = load_source_descriptors(root, enabled_only=not args.include_disabled)
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


def cmd_source_coverage(args: argparse.Namespace) -> int:
    root = _root(args.root)
    report = build_source_coverage_report(root, created_at=args.created_at)
    if args.summary:
        summary = report["summary"]
        print(f"provider_count: {summary['provider_count']}")
        print(f"source_count: {summary['source_count']}")
        print(f"enabled_deterministic_source_count: {summary['enabled_deterministic_source_count']}")
        print(f"fetched_enabled_source_count: {summary['fetched_enabled_source_count']}")
        print(f"missing_enabled_source_count: {summary['missing_enabled_source_count']}")
        print(f"blocked_pending_parser_source_count: {summary['blocked_pending_parser_source_count']}")
        print(f"manual_review_only_source_count: {summary['manual_review_only_source_count']}")
        print(f"reviewed_event_count: {summary['reviewed_event_count']}")
        print(f"latest_event_date: {summary['latest_event_date'] or 'none'}")
        print(f"candidate_backlog_count: {summary['candidate_backlog_count']}")
        print(f"warning_count: {summary['warning_count']}")
        print(f"source_state_latest_retrieved_at: {report['source_state']['latest_retrieved_at'] or 'none'}")
    else:
        _write_or_print(root, report, args.output)
    return 0


def cmd_source_review_needed(args: argparse.Namespace) -> int:
    root = _root(args.root)
    observations_path = _path_from_root(root, args.observations)
    candidate_generation_path = _path_from_root(root, args.candidate_generation)
    gate = build_source_refresh_review_gate_from_files(
        observations_path,
        candidate_generation_path,
    )
    if args.output:
        output_path = _path_from_root(root, args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(write_json_text(gate), encoding="utf-8")
    if args.github_output:
        write_github_output(Path(args.github_output), gate)
    if args.summary:
        sys.stdout.write(render_source_refresh_review_gate_summary(gate))
    else:
        _print_json(gate)
    return 0


def cmd_operations_report(args: argparse.Namespace) -> int:
    root = _root(args.root)
    report = build_operations_report(root, created_at=args.created_at)
    if args.summary:
        summary = report["summary"]
        print(f"overall_status: {report['overall_status']}")
        print(f"latest_event_date: {summary['latest_event_date'] or 'none'}")
        print(f"latest_reviewed_event_age_days: {summary['latest_reviewed_event_age_days']}")
        print(f"source_state_latest_retrieved_at: {summary['source_state_latest_retrieved_at'] or 'none'}")
        print(f"source_state_age_hours: {summary['source_state_age_hours']}")
        print(f"enabled_source_coverage_ratio: {summary['enabled_source_coverage_ratio']}")
        print(f"missing_enabled_source_count: {summary['missing_enabled_source_count']}")
        print(f"candidate_backlog_count: {summary['candidate_backlog_count']}")
        print(f"warning_count: {summary['warning_count']}")
    else:
        _write_or_print(root, report, args.output)
    return 0


def cmd_operations_launch_gate(args: argparse.Namespace) -> int:
    root = _root(args.root)
    report = build_v1_launch_gate(
        root,
        created_at=args.created_at,
        package_version=args.package_version,
    )
    if args.summary:
        summary = report["summary"]
        print(f"status: {report['status']}")
        print(f"package_version: {report['package']['version']}")
        print(f"local_check_count: {summary['local_check_count']}")
        print(f"local_pass_count: {summary['local_pass_count']}")
        print(f"local_fail_count: {summary['local_fail_count']}")
        print(f"external_smoke_step_count: {summary['external_smoke_step_count']}")
        for check in report["local_checks"]:
            print(f"{check['id']}: {check['status']}")
    else:
        _write_or_print(root, report, args.output)
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
    skipped_reviewed_duplicate_ids: list[str] = []
    if args.skip_reviewed_duplicates:
        reviewed_by_evidence = build_reviewed_evidence_index(root)
        filtered_candidates: list[dict[str, Any]] = []
        for candidate in result.candidates:
            duplicate_event_ids = duplicate_event_ids_for_candidate(candidate, reviewed_by_evidence)
            candidate_id = candidate.get("id")
            if duplicate_event_ids and isinstance(candidate_id, str):
                skipped_reviewed_duplicate_ids.append(candidate_id)
                continue
            filtered_candidates.append(candidate)
        result = type(result)(
            candidates=filtered_candidates,
            skipped_observations=result.skipped_observations,
        )
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
            "skipped_reviewed_duplicate_count": len(skipped_reviewed_duplicate_ids),
            "skipped_reviewed_duplicate_ids": skipped_reviewed_duplicate_ids,
            "written_paths": [str(path.relative_to(root)) if path.is_relative_to(root) else str(path) for path in written],
            "skipped_observations": result.skipped_observations,
        }
    )
    return 0


def cmd_candidate_review_pr_body(args: argparse.Namespace) -> int:
    root = _root(args.root)
    observations_path = _path_from_root(root, args.observations)
    candidate_dir = _path_from_root(root, args.candidates)
    observation_bundle = read_observation_bundle(observations_path)
    candidate_files = read_candidate_files(candidate_dir)
    created_at = observation_bundle.get("created_at") if isinstance(observation_bundle, dict) else None
    if not isinstance(created_at, str):
        created_at = _created_at(None)
    validation_output = ""
    if args.validation_output:
        validation_output_path = _path_from_root(root, args.validation_output)
        if not validation_output_path.exists():
            print(f"validation output not found: {validation_output_path}", file=sys.stderr)
            return 1
        validation_output = validation_output_path.read_text(encoding="utf-8")
    try:
        promotion_report = build_promotion_readiness_report(
            candidate_files,
            load_source_descriptors(root, enabled_only=False),
            root=root,
            created_at=created_at,
        )
        quality_report = build_candidate_quality_report(
            candidate_files,
            load_source_descriptors(root, enabled_only=False),
            root=root,
            created_at=created_at,
            promotion_report=promotion_report,
        )
    except ValueError as exc:
        print(f"candidate review-pr-body failed: {exc}", file=sys.stderr)
        return 1
    body = build_review_pr_body(
        observation_bundle,
        candidate_files,
        root=root,
        validation_output=validation_output,
        promotion_report=promotion_report,
        quality_report=quality_report,
        review_kind="source_state" if args.source_state_only else "candidate",
    )
    sys.stdout.write(body)
    return 0


def _created_at(value: str | None) -> str:
    if value:
        return value
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def cmd_candidate_readiness(args: argparse.Namespace) -> int:
    root = _root(args.root)
    candidate_dir = _path_from_root(root, args.candidates)
    try:
        report = build_promotion_readiness_report(
            read_candidate_files(candidate_dir),
            load_source_descriptors(root, enabled_only=False),
            root=root,
            created_at=_created_at(args.created_at),
        )
    except ValueError as exc:
        print(f"candidate readiness failed: {exc}", file=sys.stderr)
        return 1
    output = write_json_text(report)
    if args.output:
        output_path = _output_path(root, args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output, encoding="utf-8")
    else:
        sys.stdout.write(output)
    return 0


def cmd_candidate_quality(args: argparse.Namespace) -> int:
    root = _root(args.root)
    candidate_dir = _path_from_root(root, args.candidates)
    created_at = _created_at(args.created_at)
    candidate_files = read_candidate_files(candidate_dir)
    sources = load_source_descriptors(root, enabled_only=False)
    try:
        promotion_report = build_promotion_readiness_report(
            candidate_files,
            sources,
            root=root,
            created_at=created_at,
        )
        report = build_candidate_quality_report(
            candidate_files,
            sources,
            root=root,
            created_at=created_at,
            promotion_report=promotion_report,
        )
    except ValueError as exc:
        print(f"candidate quality failed: {exc}", file=sys.stderr)
        return 1
    output = write_json_text(report)
    if args.output:
        output_path = _output_path(root, args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output, encoding="utf-8")
    else:
        sys.stdout.write(output)
    return 0


def cmd_candidate_queue(args: argparse.Namespace) -> int:
    root = _root(args.root)
    candidate_dir = _path_from_root(root, args.candidates)
    created_at = _created_at(args.created_at)
    candidate_files = read_candidate_files(candidate_dir)
    sources = load_source_descriptors(root, enabled_only=False)
    try:
        promotion_report = build_promotion_readiness_report(
            candidate_files,
            sources,
            root=root,
            created_at=created_at,
        )
        quality_report = build_candidate_quality_report(
            candidate_files,
            sources,
            root=root,
            created_at=created_at,
            promotion_report=promotion_report,
        )
        queue = build_candidate_action_queue(
            candidate_files,
            created_at=created_at,
            promotion_report=promotion_report,
            quality_report=quality_report,
        )
    except ValueError as exc:
        print(f"candidate queue failed: {exc}", file=sys.stderr)
        return 1
    output = (
        render_candidate_action_queue_markdown(queue, limit_per_group=args.limit_per_group)
        if args.markdown
        else write_json_text(queue)
    )
    if args.output:
        output_path = _output_path(root, args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output, encoding="utf-8")
    else:
        sys.stdout.write(output)
    return 0


def cmd_candidate_scaffold_event(args: argparse.Namespace) -> int:
    root = _root(args.root)
    candidate_dir = _path_from_root(root, args.candidates)
    try:
        scaffold = build_candidate_event_scaffold(
            read_candidate_files(candidate_dir),
            candidate_id=args.candidate_id,
            event_date=args.event_date,
            provider=args.provider,
            event_kind=args.kind,
            title=args.title,
            summary=args.summary,
            scope_type=args.scope_type,
            scope_ref=args.scope_ref,
            impact_kind=args.impact_kind,
            direction=args.direction,
            severity=args.severity,
            confidence=args.confidence,
            observed_at=args.observed_at,
            lifecycle_status=args.lifecycle_status,
            detail_kind=args.detail_kind,
            model_refs=args.model_ref,
            replacement_refs=args.replacement_ref,
            lifecycle_action=args.lifecycle_action,
            migration_notes=args.migration_notes,
            new_default=args.new_default,
            old_default=args.old_default,
            status=args.status,
            components=args.component,
            subscription_impact=args.subscription_impact,
            api_usage_impact=args.api_usage_impact,
            recommended_action=args.recommended_action,
            limitations=args.limitation,
        )
    except (CandidateScaffoldError, ValueError) as exc:
        print(f"candidate scaffold-event failed: {exc}", file=sys.stderr)
        return 1
    if args.format == "command":
        rendered = render_candidate_event_scaffold_command(scaffold, output=args.event_output)
        if args.output:
            output_path = _output_path(root, args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(f"{rendered}\n", encoding="utf-8")
        else:
            sys.stdout.write(f"{rendered}\n")
        return 0
    _write_or_print(root, scaffold.event, args.output)
    return 0


def cmd_candidate_packet(args: argparse.Namespace) -> int:
    root = _root(args.root)
    candidate_dir = _path_from_root(root, args.candidates)
    created_at = _created_at(args.created_at)
    candidate_files = read_candidate_files(candidate_dir)
    sources = load_source_descriptors(root, enabled_only=False)
    try:
        promotion_report = build_promotion_readiness_report(
            candidate_files,
            sources,
            root=root,
            created_at=created_at,
        )
        quality_report = build_candidate_quality_report(
            candidate_files,
            sources,
            root=root,
            created_at=created_at,
            promotion_report=promotion_report,
        )
        packet = build_source_owner_packet(
            candidate_files,
            sources,
            root=root,
            created_at=created_at,
            promotion_report=promotion_report,
            quality_report=quality_report,
            recommended_actions=set(args.recommended_action or ["promote"]),
        )
    except ValueError as exc:
        print(f"candidate packet failed: {exc}", file=sys.stderr)
        return 1
    output = write_json_text(packet)
    if args.output:
        output_path = _output_path(root, args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output, encoding="utf-8")
    else:
        sys.stdout.write(output)
    return 0


def cmd_candidate_event_packet(args: argparse.Namespace) -> int:
    root = _root(args.root)
    candidate_dir = _path_from_root(root, args.candidates)
    created_at = _created_at(args.created_at)
    candidate_files = read_candidate_files(candidate_dir)
    sources = load_source_descriptors(root, enabled_only=False)
    event_draft_paths = [_path_from_root(root, item) for item in args.event_draft]
    try:
        promotion_report = build_promotion_readiness_report(
            candidate_files,
            sources,
            root=root,
            created_at=created_at,
        )
        quality_report = build_candidate_quality_report(
            candidate_files,
            sources,
            root=root,
            created_at=created_at,
            promotion_report=promotion_report,
        )
        packet = build_candidate_to_event_packet(
            candidate_files,
            event_draft_paths,
            sources,
            root=root,
            created_at=created_at,
            candidate_id=args.candidate_id,
            source_owner=args.source_owner,
            source_owner_approval_ref=args.source_owner_approval_ref,
            promotion_report=promotion_report,
            quality_report=quality_report,
        )
    except (OSError, ValueError) as exc:
        print(f"candidate event-packet failed: {exc}", file=sys.stderr)
        return 1
    _write_or_print(root, packet, args.output)
    if not packet["verified"] and not args.allow_blockers:
        print(
            "candidate event-packet failed: packet has blockers; rerun with --allow-blockers to accept advisory output",
            file=sys.stderr,
        )
        return 1
    return 0


def cmd_review_request(args: argparse.Namespace) -> int:
    root = _root(args.root)
    candidate_dir = _path_from_root(root, args.candidates)
    created_at = _created_at(args.created_at)
    candidate_files = read_candidate_files(candidate_dir)
    try:
        sources = load_source_descriptors(root, enabled_only=False)
        promotion_report = build_promotion_readiness_report(
            candidate_files,
            sources,
            root=root,
            created_at=created_at,
        )
        quality_report = build_candidate_quality_report(
            candidate_files,
            sources,
            root=root,
            created_at=created_at,
            promotion_report=promotion_report,
        )
        request = build_review_request(
            candidate_files,
            root=root,
            created_at=created_at,
            reviewer=args.reviewer,
            model=args.model,
            promotion_report=promotion_report,
            quality_report=quality_report,
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
    expected_decisions: dict[str, str] | None = None
    if args.expected_decision:
        expected_decisions = {}
        for item in args.expected_decision:
            if "=" not in item:
                print("review eval failed: expected decision must use candidate_id=decision", file=sys.stderr)
                return 1
            candidate_id, decision = item.split("=", 1)
            if decision not in REVIEW_DECISIONS:
                allowed = ", ".join(REVIEW_DECISIONS)
                print(f"review eval failed: expected decision must be one of: {allowed}", file=sys.stderr)
                return 1
            expected_decisions[candidate_id] = decision
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
        expected_candidate_ids=set(args.expected_candidate_id or []) or set(expected_decisions or {}),
        expected_decisions=expected_decisions,
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


def cmd_dashboard_agent(args: argparse.Namespace) -> int:
    root = _root(args.root)
    try:
        payload = build_agent_dashboard(
            root,
            since=args.since,
            risk=args.risk,
            provider=args.provider,
            kind=args.kind,
            event_id=args.event_id,
            agent_app=args.agent_app,
            limit=args.limit,
            created_at=args.created_at,
            source_url=args.source_url,
        )
    except ValueError as exc:
        print(f"dashboard agent failed: {exc}", file=sys.stderr)
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


def cmd_release_packet(args: argparse.Namespace) -> int:
    root = _root(args.root)
    if not _require_checkout_root(args, root, "release packet"):
        return 1
    try:
        packet = build_release_publication_packet(
            root,
            dry_run_report_path=_path_from_root(root, args.dry_run_report),
            release_manager=args.release_manager,
            source_owner=args.source_owner,
            source_owner_approval_ref=args.source_owner_approval_ref,
            release_manager_approval_ref=args.release_manager_approval_ref,
            branch_protection_ref=args.branch_protection_ref,
            ci_ref=args.ci_ref,
            codeql_workflow_ref=args.codeql_workflow_ref,
            code_scanning_ref=args.code_scanning_ref,
            dependency_review_ref=args.dependency_review_ref,
            scorecard_ref=args.scorecard_ref,
            attestation_ref=args.attestation_ref,
            checksum_review_ref=args.checksum_review_ref,
            reviewed_event_ids=args.reviewed_event,
            allow_no_reviewed_events=args.allow_no_reviewed_events,
            no_reviewed_events_reason=args.skip_reason,
        )
    except ValueError as exc:
        print(f"release packet failed: {exc}", file=sys.stderr)
        return 1
    _write_or_print(root, packet, args.output)
    return 0


def cmd_release_verify(args: argparse.Namespace) -> int:
    root = _root(args.root)
    result = verify_release_artifacts(
        root,
        dry_run_report_path=_path_from_root(root, args.dry_run_report),
        publication_packet_path=_path_from_root(root, args.publication_packet)
        if args.publication_packet
        else None,
        artifacts_root=_path_from_root(root, args.artifacts_root) if args.artifacts_root else None,
        expected_release_id=args.release_id,
        expected_source_commit=args.source_commit,
        require_publish_packet=args.require_publish_packet,
    )
    _write_or_print(root, result.report, args.output)
    return 0 if not result.failed_checks else 1


def cmd_release_evidence_index(args: argparse.Namespace) -> int:
    root = _root(args.root)
    try:
        index = build_release_evidence_index(
            root,
            release_id=args.release_id,
            source_commit=args.source_commit,
            created_at=args.created_at,
        )
    except ValueError as exc:
        print(f"release evidence-index failed: {exc}", file=sys.stderr)
        return 1
    _write_or_print(root, index, args.output)
    return 0


def cmd_release_automation_readiness(args: argparse.Namespace) -> int:
    root = _root(args.root)
    if not _require_checkout_root(args, root, "release automation-readiness"):
        return 1
    try:
        report = build_release_automation_readiness(root, created_at=args.created_at)
    except ValueError as exc:
        print(f"release automation-readiness failed: {exc}", file=sys.stderr)
        return 1
    if args.summary:
        summary = report["summary"]
        print(f"status: {report['status']}")
        print(f"current_mode: {summary['current_mode']}")
        print(f"publisher_mode: {summary['publisher_mode']}")
        print(f"target_mode: {summary['target_mode']}")
        print(f"blocking_decision: {summary['blocking_decision'] or 'none'}")
        print(f"pass_count: {summary['pass_count']}")
        print(f"fail_count: {summary['fail_count']}")
        print(f"decision_blocker_count: {summary['decision_blocker_count']}")
        for blocker in report["decision_blockers"]:
            print(f"{blocker['id']}: {blocker['status']}")
    else:
        _write_or_print(root, report, args.output)
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
    freshness_parser = subparsers.add_parser("freshness", help="print feed freshness and provenance metadata")
    freshness_parser.add_argument("--summary", action="store_true", help="print a concise text summary instead of JSON")
    freshness_parser.set_defaults(func=cmd_freshness)
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

    event_parser = subparsers.add_parser("event", help="event authoring utilities")
    event_subparsers = event_parser.add_subparsers(dest="event_command", required=True)
    event_scaffold_parser = event_subparsers.add_parser(
        "scaffold",
        help="write a schema-shaped ProviderEvent draft from reviewed official-source facts",
    )
    event_kind_choices = sorted(DETAIL_KIND_TO_EVENT_KINDS["generic_change"])
    detail_kind_choices = ["auto", *sorted(DETAIL_KIND_TO_EVENT_KINDS)]
    event_scaffold_parser.add_argument("--event-id", help="explicit ProviderEvent id; default is date/provider/title slug")
    event_scaffold_parser.add_argument("--event-date", required=True, help="provider announcement date, YYYY-MM-DD")
    event_scaffold_parser.add_argument("--provider", required=True, help="provider slug or provider:<slug>")
    event_scaffold_parser.add_argument("--kind", required=True, choices=event_kind_choices, help="ProviderEvent event_kind")
    event_scaffold_parser.add_argument("--title", required=True)
    event_scaffold_parser.add_argument("--summary", required=True)
    event_scaffold_parser.add_argument("--source-url", required=True, help="official public evidence URL")
    event_scaffold_parser.add_argument("--source-key", required=True, help="source registry key")
    event_scaffold_parser.add_argument(
        "--source-authority",
        required=True,
        choices=[
            "official_pricing",
            "official_docs",
            "official_status",
            "official_repo",
            "official_blog",
            "official_staff_social",
            "community_hint",
            "third_party_catalog",
            "manual",
        ],
    )
    content_group = event_scaffold_parser.add_mutually_exclusive_group(required=True)
    content_group.add_argument("--content-sha256", help="bounded source snapshot SHA-256")
    content_group.add_argument("--content-text-file", help="local source snapshot file to hash without copying into the event")
    event_scaffold_parser.add_argument("--scope-type", default="provider_surface", choices=[
        "provider",
        "provider_surface",
        "model",
        "model_alias",
        "agent_app",
        "subscription_plan",
        "api_endpoint",
        "sdk",
        "gateway",
        "cloud_region",
        "account_type",
        "unknown",
    ])
    event_scaffold_parser.add_argument("--scope-ref", required=True, help="affected provider surface, model, app, endpoint, or other APW ref")
    event_scaffold_parser.add_argument("--impact-kind", required=True, choices=[
        "cost",
        "quota",
        "rate_limit",
        "availability",
        "migration",
        "behavior",
        "quality",
        "security",
        "compliance",
        "unknown",
    ])
    event_scaffold_parser.add_argument("--direction", required=True, choices=["increase", "decrease", "added", "removed", "changed", "unknown"])
    event_scaffold_parser.add_argument("--severity", default="medium", choices=sorted(SEVERITY_RANK))
    event_scaffold_parser.add_argument("--confidence", default="confirmed", choices=["low", "medium", "high", "confirmed"])
    event_scaffold_parser.add_argument("--observed-at", help="RFC3339 source review timestamp; default is now")
    event_scaffold_parser.add_argument("--lifecycle-status", default="reviewed", choices=["candidate", "reviewed", "published", "superseded", "retracted", "rejected"])
    event_scaffold_parser.add_argument("--date-confidence", default="exact", choices=["exact", "approximate", "unknown"])
    event_scaffold_parser.add_argument("--announced-at")
    event_scaffold_parser.add_argument("--effective-at")
    event_scaffold_parser.add_argument("--expires-at")
    event_scaffold_parser.add_argument("--migration-deadline")
    event_scaffold_parser.add_argument("--detail-kind", default="auto", choices=detail_kind_choices)
    event_scaffold_parser.add_argument("--model-ref", action="append", help="model slug/ref for model lifecycle details")
    event_scaffold_parser.add_argument("--replacement-ref", action="append", help="replacement model slug/ref")
    event_scaffold_parser.add_argument("--lifecycle-action", choices=["launch", "deprecation", "retirement", "replacement", "correction"])
    event_scaffold_parser.add_argument("--migration-notes")
    event_scaffold_parser.add_argument("--new-default")
    event_scaffold_parser.add_argument("--old-default")
    event_scaffold_parser.add_argument("--status", choices=["investigating", "identified", "monitoring", "resolved", "unknown"])
    event_scaffold_parser.add_argument("--component", action="append")
    event_scaffold_parser.add_argument("--subscription-impact", default="unknown", choices=["none", "possible", "direct", "unknown"])
    event_scaffold_parser.add_argument("--api-usage-impact", default="direct", choices=["none", "possible", "direct", "unknown"])
    event_scaffold_parser.add_argument("--who", action="append", choices=[
        "platform_engineers",
        "finops",
        "coding_agent_users",
        "sdk_maintainers",
        "product_engineers",
        "reliability_engineers",
        "security_engineers",
    ])
    event_scaffold_parser.add_argument("--recommended-action")
    event_scaffold_parser.add_argument("--selector")
    event_scaffold_parser.add_argument("--snapshot-ref")
    event_scaffold_parser.add_argument("--license-note")
    event_scaffold_parser.add_argument("--tag", action="append")
    event_scaffold_parser.add_argument("--limitation", action="append")
    event_scaffold_parser.add_argument("--output", help="write event draft JSON to this path instead of stdout")
    event_scaffold_parser.set_defaults(func=cmd_event_scaffold)

    issue_triage_parser = event_subparsers.add_parser(
        "issue-triage",
        help="render review-only triage for a Missing provider event issue body",
    )
    issue_triage_parser.add_argument("--issue-body", required=True, help="local Markdown file containing the GitHub issue body")
    issue_triage_parser.add_argument("--format", default="markdown", choices=["markdown", "json"])
    issue_triage_parser.add_argument("--output", help="write triage output to this path instead of stdout")
    issue_triage_parser.set_defaults(func=cmd_event_issue_triage)

    remote_parser = subparsers.add_parser("remote", help="read live GitHub feed artifacts without a checkout")
    remote_subparsers = remote_parser.add_subparsers(dest="remote_command", required=True)
    remote_latest_parser = remote_subparsers.add_parser("latest", help="print latest events from a remote APW feed")
    remote_latest_parser.add_argument("--ref", default="main", help="Git ref to read, such as main or data-YYYY.MM.DD")
    remote_latest_parser.add_argument("--risk", choices=sorted(SEVERITY_RANK))
    remote_latest_parser.add_argument("--provider")
    remote_latest_parser.add_argument("--limit", type=int, default=20)
    remote_latest_parser.add_argument("--timeout", type=float, default=20.0)
    remote_latest_parser.add_argument("--limit-bytes", type=int, default=5_000_000)
    remote_latest_parser.set_defaults(func=cmd_remote_latest)
    remote_freshness_parser = remote_subparsers.add_parser("freshness", help="print remote feed freshness metadata")
    remote_freshness_parser.add_argument("--ref", default="main", help="Git ref to read, such as main or data-YYYY.MM.DD")
    remote_freshness_parser.add_argument("--summary", action="store_true")
    remote_freshness_parser.add_argument("--timeout", type=float, default=20.0)
    remote_freshness_parser.add_argument("--limit-bytes", type=int, default=5_000_000)
    remote_freshness_parser.set_defaults(func=cmd_remote_freshness)
    remote_feed_parser = remote_subparsers.add_parser("feed", help="print one remote feed artifact")
    remote_feed_parser.add_argument("name", choices=sorted(REMOTE_ARTIFACTS))
    remote_feed_parser.add_argument("--ref", default="main", help="Git ref to read, such as main or data-YYYY.MM.DD")
    remote_feed_parser.add_argument("--timeout", type=float, default=20.0)
    remote_feed_parser.add_argument("--limit-bytes", type=int, default=5_000_000)
    remote_feed_parser.add_argument("--output", help="write remote feed artifact to this path instead of stdout")
    remote_feed_parser.set_defaults(func=cmd_remote_feed)

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
    source_fetch_parser.add_argument(
        "--include-disabled",
        action="store_true",
        help="maintainer smoke: allow --source to fetch disabled descriptors without writing source state",
    )
    source_fetch_parser.add_argument("--timeout", type=float, default=20.0)
    source_fetch_parser.add_argument("--limit-bytes", type=int, default=3_000_000)
    source_fetch_parser.set_defaults(func=cmd_source_fetch)
    source_coverage_parser = source_subparsers.add_parser(
        "coverage",
        help="print source coverage, freshness, and review backlog metadata",
    )
    source_coverage_parser.add_argument("--created-at", help="RFC3339 timestamp for deterministic reports")
    source_coverage_parser.add_argument("--summary", action="store_true", help="print a concise text summary instead of JSON")
    source_coverage_parser.add_argument("--output", help="write JSON report to this path instead of stdout")
    source_coverage_parser.set_defaults(func=cmd_source_coverage)
    source_review_needed_parser = source_subparsers.add_parser(
        "review-needed",
        help="decide whether source refresh output needs a candidate-review PR",
    )
    source_review_needed_parser.add_argument("--observations", required=True)
    source_review_needed_parser.add_argument("--candidate-generation", required=True)
    source_review_needed_parser.add_argument("--summary", action="store_true", help="print a concise text summary instead of JSON")
    source_review_needed_parser.add_argument("--output", help="write JSON report to this path instead of stdout")
    source_review_needed_parser.add_argument(
        "--github-output",
        help="append GitHub Actions output variables to this file, usually $GITHUB_OUTPUT",
    )
    source_review_needed_parser.set_defaults(func=cmd_source_review_needed)

    operations_parser = subparsers.add_parser(
        "operations",
        help="public operations and data-quality report commands",
    )
    operations_subparsers = operations_parser.add_subparsers(dest="operations_command", required=True)
    operations_report_parser = operations_subparsers.add_parser(
        "report",
        help="render public SLO, source freshness, backlog, and governance visibility",
    )
    operations_report_parser.add_argument("--created-at", help="RFC3339 timestamp for deterministic reports")
    operations_report_parser.add_argument("--summary", action="store_true", help="print a concise text summary instead of JSON")
    operations_report_parser.add_argument("--output", help="write JSON report to this path instead of stdout")
    operations_report_parser.set_defaults(func=cmd_operations_report)
    operations_launch_gate_parser = operations_subparsers.add_parser(
        "launch-gate",
        help="render the v1 external-user launch gate and smoke commands",
    )
    operations_launch_gate_parser.add_argument("--created-at", help="RFC3339 timestamp for deterministic reports")
    operations_launch_gate_parser.add_argument("--package-version", help="expected PyPI package version for smoke commands")
    operations_launch_gate_parser.add_argument("--summary", action="store_true", help="print a concise text summary instead of JSON")
    operations_launch_gate_parser.add_argument("--output", help="write JSON report to this path instead of stdout")
    operations_launch_gate_parser.set_defaults(func=cmd_operations_launch_gate)

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
    candidate_generate_parser.add_argument(
        "--skip-reviewed-duplicates",
        action="store_true",
        help="do not write candidates whose evidence is already covered by reviewed ProviderEvents",
    )
    candidate_generate_parser.set_defaults(func=cmd_candidate_generate)
    candidate_review_body_parser = candidate_subparsers.add_parser(
        "review-pr-body",
        help="render a draft candidate-review PR body",
    )
    candidate_review_body_parser.add_argument("--observations", required=True)
    candidate_review_body_parser.add_argument("--candidates", default="data/candidates/review")
    candidate_review_body_parser.add_argument("--validation-output")
    candidate_review_body_parser.add_argument(
        "--source-state-only",
        action="store_true",
        help="render copy for a source-fingerprint-only refresh with no candidate promotion request",
    )
    candidate_review_body_parser.set_defaults(func=cmd_candidate_review_pr_body)
    candidate_readiness_parser = candidate_subparsers.add_parser(
        "readiness",
        help="render advisory promotion-readiness context for review candidates",
    )
    candidate_readiness_parser.add_argument("--candidates", default="data/candidates/review")
    candidate_readiness_parser.add_argument(
        "--created-at",
        help="RFC3339 timestamp for deterministic readiness reports; defaults to now in UTC",
    )
    candidate_readiness_parser.add_argument("--output", help="write JSON report to this path instead of stdout")
    candidate_readiness_parser.set_defaults(func=cmd_candidate_readiness)
    candidate_quality_parser = candidate_subparsers.add_parser(
        "quality",
        help="render advisory interestingness and source-owner decision quality for review candidates",
    )
    candidate_quality_parser.add_argument("--candidates", default="data/candidates/review")
    candidate_quality_parser.add_argument(
        "--created-at",
        help="RFC3339 timestamp for deterministic quality reports; defaults to now in UTC",
    )
    candidate_quality_parser.add_argument("--output", help="write JSON report to this path instead of stdout")
    candidate_quality_parser.set_defaults(func=cmd_candidate_quality)
    candidate_queue_parser = candidate_subparsers.add_parser(
        "queue",
        help="group review candidates into promote, duplicate, reject, and human-review queues",
    )
    candidate_queue_parser.add_argument("--candidates", default="data/candidates/review")
    candidate_queue_parser.add_argument(
        "--created-at",
        help="RFC3339 timestamp for deterministic queue reports; defaults to now in UTC",
    )
    candidate_queue_parser.add_argument("--markdown", action="store_true", help="render a compact Markdown queue instead of JSON")
    candidate_queue_parser.add_argument(
        "--limit-per-group",
        type=int,
        default=12,
        help="maximum rows per action group when rendering Markdown",
    )
    candidate_queue_parser.add_argument("--output", help="write queue report to this path instead of stdout")
    candidate_queue_parser.set_defaults(func=cmd_candidate_queue)
    candidate_scaffold_event_parser = candidate_subparsers.add_parser(
        "scaffold-event",
        help="draft a ProviderEvent scaffold from one review candidate",
    )
    candidate_scaffold_event_parser.add_argument("--candidates", default="data/candidates/review")
    candidate_scaffold_event_parser.add_argument("--candidate-id", required=True)
    candidate_scaffold_event_parser.add_argument(
        "--event-date",
        help="provider announcement/effective date, YYYY-MM-DD; defaults to evidence retrieval date with unknown date confidence",
    )
    candidate_scaffold_event_parser.add_argument("--provider", help="provider slug/ref override; defaults to the candidate provider")
    candidate_scaffold_event_parser.add_argument("--kind", choices=event_kind_choices, help="ProviderEvent kind override; defaults to candidate_kind")
    candidate_scaffold_event_parser.add_argument("--title", help="reviewed event title; defaults to a neutral candidate title")
    candidate_scaffold_event_parser.add_argument("--summary", help="reviewed summary; defaults to bounded candidate claim text")
    candidate_scaffold_event_parser.add_argument("--scope-type", choices=[
        "provider",
        "provider_surface",
        "model",
        "model_alias",
        "agent_app",
        "subscription_plan",
        "api_endpoint",
        "sdk",
        "gateway",
        "cloud_region",
        "account_type",
        "unknown",
    ])
    candidate_scaffold_event_parser.add_argument("--scope-ref", help="affected provider surface, model, app, endpoint, or other APW ref; defaults to provider ref")
    candidate_scaffold_event_parser.add_argument("--impact-kind", choices=[
        "cost",
        "quota",
        "rate_limit",
        "availability",
        "migration",
        "behavior",
        "quality",
        "security",
        "compliance",
        "unknown",
    ])
    candidate_scaffold_event_parser.add_argument("--direction", choices=["increase", "decrease", "added", "removed", "changed", "unknown"])
    candidate_scaffold_event_parser.add_argument("--severity", default="medium", choices=sorted(SEVERITY_RANK))
    candidate_scaffold_event_parser.add_argument("--confidence", default="confirmed", choices=["low", "medium", "high", "confirmed"])
    candidate_scaffold_event_parser.add_argument("--observed-at", help="RFC3339 source review timestamp; defaults to candidate evidence retrieval time")
    candidate_scaffold_event_parser.add_argument("--lifecycle-status", default="reviewed", choices=["candidate", "reviewed", "published", "superseded", "retracted", "rejected"])
    candidate_scaffold_event_parser.add_argument("--detail-kind", default="generic_change", choices=detail_kind_choices)
    candidate_scaffold_event_parser.add_argument("--model-ref", action="append", help="model slug/ref for typed model lifecycle details")
    candidate_scaffold_event_parser.add_argument("--replacement-ref", action="append", help="replacement model slug/ref")
    candidate_scaffold_event_parser.add_argument("--lifecycle-action", choices=["launch", "deprecation", "retirement", "replacement", "correction"])
    candidate_scaffold_event_parser.add_argument("--migration-notes")
    candidate_scaffold_event_parser.add_argument("--new-default")
    candidate_scaffold_event_parser.add_argument("--old-default")
    candidate_scaffold_event_parser.add_argument("--status", choices=["investigating", "identified", "monitoring", "resolved", "unknown"])
    candidate_scaffold_event_parser.add_argument("--component", action="append")
    candidate_scaffold_event_parser.add_argument("--subscription-impact", default="unknown", choices=["none", "possible", "direct", "unknown"])
    candidate_scaffold_event_parser.add_argument("--api-usage-impact", default="direct", choices=["none", "possible", "direct", "unknown"])
    candidate_scaffold_event_parser.add_argument("--recommended-action")
    candidate_scaffold_event_parser.add_argument("--limitation", action="append")
    candidate_scaffold_event_parser.add_argument("--format", default="json", choices=["json", "command"])
    candidate_scaffold_event_parser.add_argument("--event-output", help="event file path to include when rendering --format command")
    candidate_scaffold_event_parser.add_argument("--output", help="write JSON draft or command text to this path instead of stdout")
    candidate_scaffold_event_parser.set_defaults(func=cmd_candidate_scaffold_event)
    candidate_packet_parser = candidate_subparsers.add_parser(
        "packet",
        help="render a source-owner event-drafting packet for high-value review candidates",
    )
    candidate_packet_parser.add_argument("--candidates", default="data/candidates/review")
    candidate_packet_parser.add_argument(
        "--created-at",
        help="RFC3339 timestamp for deterministic source-owner packets; defaults to now in UTC",
    )
    candidate_packet_parser.add_argument(
        "--recommended-action",
        action="append",
        choices=["promote", "needs_human_review", "duplicate", "reject"],
        help="candidate-quality recommended action to include; repeat to include more actions",
    )
    candidate_packet_parser.add_argument("--output", help="write JSON packet to this path instead of stdout")
    candidate_packet_parser.set_defaults(func=cmd_candidate_packet)
    candidate_event_packet_parser = candidate_subparsers.add_parser(
        "event-packet",
        help="verify source-owner-authored ProviderEvent drafts against one review candidate",
    )
    candidate_event_packet_parser.add_argument("--candidates", default="data/candidates/review")
    candidate_event_packet_parser.add_argument("--candidate-id", required=True)
    candidate_event_packet_parser.add_argument(
        "--event-draft",
        action="append",
        required=True,
        help="ProviderEvent draft JSON path; repeat for split candidates",
    )
    candidate_event_packet_parser.add_argument("--source-owner", required=True)
    candidate_event_packet_parser.add_argument("--source-owner-approval-ref", required=True)
    candidate_event_packet_parser.add_argument(
        "--created-at",
        help="RFC3339 timestamp for deterministic candidate-to-event packets; defaults to now in UTC",
    )
    candidate_event_packet_parser.add_argument(
        "--allow-blockers",
        action="store_true",
        help="write an advisory packet even when verification blockers remain",
    )
    candidate_event_packet_parser.add_argument("--output", help="write JSON packet to this path instead of stdout")
    candidate_event_packet_parser.set_defaults(func=cmd_candidate_event_packet)

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
    review_eval_parser.add_argument(
        "--expected-decision",
        action="append",
        help="expected advisory curation decision as candidate_id=promote|reject|duplicate|split|needs_human_review",
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

    dashboard_parser = subparsers.add_parser("dashboard", help="render local dashboard payloads")
    dashboard_subparsers = dashboard_parser.add_subparsers(dest="dashboard_command", required=True)
    dashboard_agent_parser = dashboard_subparsers.add_parser(
        "agent",
        help="render coding-agent provider-impact cards as local JSON",
    )
    dashboard_agent_parser.add_argument("--since", default="30d", help="event date cutoff or day window")
    dashboard_agent_parser.add_argument(
        "--risk",
        choices=sorted(SEVERITY_RANK),
        default="medium",
        help="minimum event severity",
    )
    dashboard_agent_parser.add_argument("--provider", help="provider id or provider: ref")
    dashboard_agent_parser.add_argument("--kind", help="event kind filter")
    dashboard_agent_parser.add_argument("--event-id", help="single event id filter")
    dashboard_agent_parser.add_argument(
        "--agent-app",
        help="agent app id or app: ref, for example codex or app:claude-code",
    )
    dashboard_agent_parser.add_argument("--limit", type=int, default=20, help="maximum cards to include")
    dashboard_agent_parser.add_argument("--created-at", help="RFC3339 timestamp for deterministic payloads")
    dashboard_agent_parser.add_argument(
        "--source-url",
        default="https://github.com/ottto-ai/ai-provider-watch",
        help="source URL to include in the payload",
    )
    dashboard_agent_parser.add_argument("--output", help="write JSON payload to this path instead of stdout")
    dashboard_agent_parser.set_defaults(func=cmd_dashboard_agent)

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
    release_packet_parser = release_subparsers.add_parser(
        "packet",
        help="render a reviewed data-release publication packet without publishing",
    )
    release_packet_parser.add_argument("--dry-run-report", required=True)
    release_packet_parser.add_argument("--release-manager", required=True)
    release_packet_parser.add_argument("--source-owner", required=True)
    release_packet_parser.add_argument("--source-owner-approval-ref", required=True)
    release_packet_parser.add_argument("--release-manager-approval-ref", required=True)
    release_packet_parser.add_argument("--branch-protection-ref", required=True)
    release_packet_parser.add_argument("--ci-ref", required=True)
    release_packet_parser.add_argument("--codeql-workflow-ref", required=True)
    release_packet_parser.add_argument("--code-scanning-ref", required=True)
    release_packet_parser.add_argument("--dependency-review-ref", required=True)
    release_packet_parser.add_argument("--scorecard-ref", required=True)
    release_packet_parser.add_argument("--attestation-ref", required=True)
    release_packet_parser.add_argument("--checksum-review-ref", required=True)
    release_packet_parser.add_argument("--reviewed-event", action="append", default=[])
    release_packet_parser.add_argument(
        "--allow-no-reviewed-events",
        action="store_true",
        help="allow a skip packet for a release date with no reviewed event changes",
    )
    release_packet_parser.add_argument("--skip-reason")
    release_packet_parser.add_argument("--output", help="write JSON payload to this path instead of stdout")
    release_packet_parser.set_defaults(func=cmd_release_packet)
    release_verify_parser = release_subparsers.add_parser(
        "verify",
        help="verify a release dry-run artifact set and optional publication packet without publishing",
    )
    release_verify_parser.add_argument("--dry-run-report", required=True)
    release_verify_parser.add_argument("--publication-packet")
    release_verify_parser.add_argument(
        "--artifacts-root",
        help="release artifacts root; defaults to the dry-run report sibling artifacts directory",
    )
    release_verify_parser.add_argument("--release-id", help="expected data-YYYY.MM.DD release id")
    release_verify_parser.add_argument("--source-commit", help="expected 40-character source commit SHA")
    release_verify_parser.add_argument(
        "--require-publish-packet",
        action="store_true",
        help="fail unless --publication-packet is a publish packet with reviewed events",
    )
    release_verify_parser.add_argument("--output", help="write JSON verification report to this path instead of stdout")
    release_verify_parser.set_defaults(func=cmd_release_verify)
    release_evidence_parser = release_subparsers.add_parser(
        "evidence-index",
        help="render the machine-readable release evidence contract",
    )
    release_evidence_parser.add_argument(
        "--release-id",
        default="dev",
        help="release id to describe; use dev or data-YYYY.MM.DD",
    )
    release_evidence_parser.add_argument("--source-commit", help="40-character source commit SHA")
    release_evidence_parser.add_argument("--created-at", help="RFC3339 timestamp for deterministic output")
    release_evidence_parser.add_argument("--output", help="write JSON evidence index to this path instead of stdout")
    release_evidence_parser.set_defaults(func=cmd_release_evidence_index)
    release_automation_readiness_parser = release_subparsers.add_parser(
        "automation-readiness",
        help="render the data-release automation graduation decision report",
    )
    release_automation_readiness_parser.add_argument(
        "--created-at",
        help="RFC3339 timestamp for deterministic output",
    )
    release_automation_readiness_parser.add_argument("--summary", action="store_true", help="print a concise text summary instead of JSON")
    release_automation_readiness_parser.add_argument("--output", help="write JSON report to this path instead of stdout")
    release_automation_readiness_parser.set_defaults(func=cmd_release_automation_readiness)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)
