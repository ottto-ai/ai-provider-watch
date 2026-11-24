# Guarded Data Publisher

The guarded data publisher is a protected-environment workflow for future
`data-YYYY.MM.DD` or `data-YYYY.MM.DD.N` publication. In v0.x it is evidence-only: it runs release
gates from a trusted `main` commit, can render a reviewed publication packet,
and records that no data tag or GitHub data release was created.

## Approved v0.1 Publishing Mechanism

For v0.1, real public data publication is manual release-manager work:

1. run the release gates from a clean checkout of the intended `main` commit;
2. verify CI, CodeQL, Dependency Review, release dry-run checksums, and artifact
   attestation evidence;
3. create a manual Ron-signed Git tag with `git tag -s data-YYYY.MM.DD`;
4. verify the signed tag with `git tag -v data-YYYY.MM.DD`;
5. publish the matching GitHub data release with the release evidence packet.

If the same UTC date already has a signed data tag and reviewed event data
changed again, use the next revision tag such as `data-YYYY.MM.DD.1` instead of
moving the existing tag. Revision tags follow the same gates and are equally
immutable.

Do not store signing keys in Actions, repository secrets, environment secrets,
or OIDC-backed jobs. GitHub artifact attestations are provenance evidence for
the dry-run artifact bundle; they are not a replacement for the release
manager's signed Git tag.

The protected `data-publisher.yml` workflow remains non-publishing in v0.x. It
may be used as an approval/evidence gate and packet generator, but not as the
actor that creates data tags or GitHub releases.

## Threat Model

Source refresh, candidate generation, LLM review, issue bodies, PR comments,
MCP text, and provider pages are untrusted input lanes. Those lanes must never
receive release secrets, OIDC publishing authority, tag creation authority, or
GitHub release upload authority.

The publisher is separate from those lanes. It can only be started manually from
`main`, requires the protected `data-release` environment, and currently keeps
`contents: read` with no secrets and no OIDC token. The no-op and packet modes
are staging contracts for the eventual publisher, not publication approval.

## Protected Environment

Create a GitHub environment named `data-release` before using the workflow as a
release gate:

1. Require reviewer approval from `@RonShub` during the v0.1 single-maintainer
   period.
2. Do not add environment secrets while the workflow is evidence-only.
3. Keep the workflow restricted to `main`.
4. Record the workflow run URL, source commit, release date, and dry-run report
   in release evidence.

If the environment cannot require the release manager review, the publisher is
not a release gate and real publication remains manual.

## No-Op Mode

Run the no-op publisher only after CI, CodeQL, generated feeds, source fixtures,
and the scheduled data-release dry run are green:

```bash
gh workflow run data-publisher.yml \
  --repo ottto-ai/ai-provider-watch \
  --ref main \
  -f release_date="$(date -u +%F)" \
  -f release_id="data-$(date -u +%Y.%m.%d)" \
  -f publish_mode=no-op
```

The workflow checks:

- source ref is `refs/heads/main`;
- `publish_mode` is exactly `no-op` or `packet`;
- `uv lock --check`;
- `uv run ruff check .`;
- `uv run pytest`;
- `uv run apw source test`;
- `uv run apw source coverage --summary`;
- `uv run apw operations report --summary`;
- `uv run apw validate`;
- `uv run apw index --check`;
- `uv run apw release dry-run --require-clean`;
- `uv run apw release verify` against the generated dry-run report, release
  ID, source commit, artifact manifest, and checksums.

It does not create tags, upload releases, read secrets, request OIDC, or process
provider/source/candidate text beyond the reviewed repository checkout.

## Packet Mode

Use packet mode when the release manager wants the protected workflow to render
and upload a `publication-packet.json` artifact after the same no-op dry-run
checks pass:

```bash
gh workflow run data-publisher.yml \
  --repo ottto-ai/ai-provider-watch \
  --ref main \
  -f release_date="$(date -u +%F)" \
  -f release_id="data-$(date -u +%Y.%m.%d)" \
  -f publish_mode=packet \
  -f source_owner_approval_ref="<issue-or-pr-comment-url>" \
  -f release_manager_approval_ref="<issue-or-pr-comment-url>" \
  -f branch_protection_ref="<branch-protection-evidence-ref>" \
  -f ci_ref="<successful-CI-run-url>" \
  -f codeql_workflow_ref="<successful-CodeQL-run-url>" \
  -f code_scanning_ref="<code-scanning-analysis-url-or-id>" \
  -f dependency_review_ref="<successful-Dependency-Review-run-url>" \
  -f scorecard_ref="<successful-Scorecard-run-url>" \
  -f attestation_ref="<gh-attestation-verify-ref>" \
  -f allow_no_reviewed_events=true \
  -f skip_reason="No source-owner-reviewed ProviderEvent changes landed for this release date."
```

For a publish packet, pass `reviewed_event_ids` instead of
`allow_no_reviewed_events` and `skip_reason`. The input accepts newline- or
comma-separated ProviderEvent IDs, and the CLI verifies that each ID exists in
`data/events`.

Packet mode verifies the packet against the dry-run report before uploading
review evidence. It uploads the dry-run report, `publication-packet.json`, and
`release-verification.json` as the `apw-data-publication-packet` artifact. It
still keeps `contents: read`, does not request OIDC, does not use secrets, does
not create a tag, and does not create or upload a GitHub Release. If
`checksum_review_ref` is omitted, the workflow records the dry-run report
SHA-256 from the protected run.

For a same-day revision packet, pass the exact revision identity:

```bash
gh workflow run data-publisher.yml \
  --repo ottto-ai/ai-provider-watch \
  --ref main \
  -f release_date=2026-06-11 \
  -f release_id=data-2026.06.11.1 \
  -f publish_mode=packet \
  ...
```

## Publication Packet Contract

Before any real `data-YYYY.MM.DD` or `data-YYYY.MM.DD.N` tag, render
`apw release packet` from the successful dry-run report. The packet conforms to
`schemas/release-publication-packet.schema.json` and records:

- reviewed `data/events/*.json` IDs, or an explicit no-reviewed-events skip
  reason;
- source-owner approval and release-manager approval refs;
- branch protection, CI, CodeQL workflow, code-scanning, Dependency Review,
  OpenSSF Scorecard, checksum review, and attestation refs;
- manual release-manager signed-tag commands;
- proof that source refresh, candidate generation, LLM review, PR-comment
  processing, MCP, provider-page fetch, and social/community lanes remain
  forbidden release-token lanes.

The packet supports daily skip behavior without creating empty tags blindly. A
skip packet says why no public data tag should be created for that date. A
publish packet lists the reviewed event IDs that justify the tag.

## Future Automated Publishing Gate

Do not add automated `data-YYYY.MM.DD` or `data-YYYY.MM.DD.N` publishing until a release manager
approves a new mechanism and a follow-up PR changes this workflow deliberately.
That future PR must treat the v0.1 manual signed-tag policy as the baseline and
explain why automation is worth the additional key-management and release-token
risk.

Before enabling real publication, the follow-up PR must add tests proving:

- the publisher runs only from trusted `main` commits;
- the `data-release` environment requires release-manager review;
- source-refresh, candidate, LLM review, issue, PR-comment, and MCP lanes still
  have no release authority;
- release dry-run artifact checksums match the downloaded artifact;
- `gh attestation verify` succeeds for the dry-run evidence bundle;
- Dependency Review, CI, CodeQL workflow, and code-scanning analysis are green
  for the release commit;
- the selected tag mechanism signs or otherwise provides the approved signature
  posture;
- signing keys are never available to workflows that process provider pages,
  source observations, generated candidates, issue bodies, PR comments, social
  posts, or MCP resource text.

Until those tests and a new automation decision land, public data publication
stays manual, Ron-signed, and release-manager approved.
