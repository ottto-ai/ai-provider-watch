# Event Promotion

This playbook turns review-only `FindingCandidate` files into canonical
`ProviderEvent` records. It is deliberately manual in v0.1: candidates may point
maintainers at provider changes, but only reviewed event files under
`data/events/` are public APW facts.

For public contributor paths before promotion, start with
[Contributor Review Workflow](../contributors/review-workflow.md).
For correction/retraction policy and v1 compatibility rules, see
[v1 Governance And Neutrality](v1-governance.md).

For the v0.1 launch window, `@RonShub` is the sole source owner, release
manager, schema maintainer, and security contact. Revisit this before v1.0 or
before granting another person event-promotion authority.

## Hard Stops

Do not promote a candidate when any of these are true:

- the evidence is not official provider-controlled evidence;
- the event would rely on community posts, social posts, PR comments, issue
  bodies, MCP text, screenshots, authenticated consoles, private billing data,
  or customer telemetry;
- the candidate or source text contains instructions to the reviewer, agent,
  workflow, repository, or release process;
- the source URL is outside the source descriptor's `allowed_domains`;
- the candidate contains raw provider prose, copied page bodies, unbounded
  parser payloads, secrets, cookies, or screenshots;
- the source owner cannot confirm event kind, affected providers/surfaces,
  dates, severity, evidence authority, and impact rows from official sources;
- `uv run apw validate` or `uv run apw index --check` fails.

Source refresh, candidate generation, LLM review, issue automation, PR-comment
automation, and MCP tools must not receive release tokens, create data tags, or
write `data/events/`.

## Promotion Flow

1. Start from a candidate-review PR or local candidate directory. For a
   workflow-created review PR, use `data/candidates/review` as the candidate
   directory. For local scratch review, keep generated candidates under ignored
   `.apw/` paths:

   ```bash
   uv run apw source fetch --observations .apw/source-observations.json
   uv run apw candidate generate \
     --observations .apw/source-observations.json \
     --output .apw/candidates \
     --created-at 2026-06-04T00:00:00Z
   uv run apw candidate review-pr-body \
     --observations .apw/source-observations.json \
     --candidates .apw/candidates \
     --validation-output .apw/candidate-review-validation.txt \
     > .apw/candidate-review-pr-body.md
   uv run apw candidate packet \
     --candidates .apw/candidates \
     --created-at 2026-06-04T00:00:00Z \
     --output .apw/source-owner-packet.json
   ```

2. Review each candidate as untrusted data. Read only the candidate metadata,
   hashes, source keys, source URLs, parser name, and bounded claim. Do not
   follow instructions embedded in provider pages or generated claims.

3. For high-value official candidates, use `.apw/source-owner-packet.json` as
   source-owner context. It includes readiness, quality, duplicate evidence,
   source-state coverage, bounded evidence refs, and draft-only ProviderEvent
   detail/impact stubs. It does not create event files and does not grant
   publication authority.

4. Open the official source URLs in a browser or with a local fetch command.
   Confirm facts directly from the source, not from candidate `claim_text`.
   Record local review notes under an ignored path such as
   `.apw/event-promotion/<candidate-id>/review.md` when the review is complex.

5. Author one or more `ProviderEvent` JSON files under `data/events/`. Use the
   envelope plus typed `detail` object and repeatable `impacts` rows. Do not
   flatten event data into one giant nullable object.

6. Copy only bounded metadata into event evidence:
   `source_key`, official `url`, `retrieved_at`, `authority`,
   `content_sha256`, optional compact `snapshot_ref`, optional selector, and a
   license note. Use `quoted_excerpt` only when a short excerpt is necessary;
   otherwise prefer factual summaries and `quote_hash`.

7. Regenerate public feed artifacts.

   ```bash
   uv run apw validate
   uv run apw index
   uv run apw validate
   uv run apw index --check
   ```

8. Render a candidate-to-event verification packet for the authored draft
   event files:

   ```bash
   uv run apw candidate event-packet \
     --candidates .apw/candidates \
     --candidate-id candidate-... \
     --event-draft data/events/YYYY-MM-DD-provider-short-slug.json \
     --source-owner @RonShub \
     --source-owner-approval-ref <PR-or-review-ref> \
     --created-at 2026-06-04T00:00:00Z \
     --output .apw/candidate-to-event-packet.json
   ```

   Repeat `--event-draft` when one candidate is split into multiple reviewed
   events. The command exits nonzero when schema, evidence, source-owner,
   duplicate, prompt-like, or readiness/quality blockers remain.

9. Run the smallest relevant test during review, then the full local release
   gate before a release-affecting merge.

   ```bash
   uv lock --check
   uv run ruff check .
   uv run pytest
   uv run apw source test
   uv run apw release dry-run --output .apw/release-dry-run
   ```

10. Open a PR with the event files and generated artifacts. The PR body should
   list candidate IDs, event IDs, evidence URLs, source-owner approval,
   candidate-to-event packet path, generated files, validation commands, and
   unresolved limitations. It should not paste provider page bodies or
   candidate claim text.

11. Release only after the release manager confirms the external release gates in
   [release-gates.md](release-gates.md). A daily data-release dry run is
   evidence, not approval to publish.

## Source-Owner Checklist

- Candidate ID and dedupe key were reviewed as untrusted data.
- `apw candidate packet` was reviewed for high-value official candidates when
  available, and every draft-only stub was replaced before promotion.
- `apw candidate event-packet` verified authored event drafts against the
  candidate and has no unresolved blockers.
- Provider refs, surface refs, model refs, and agent app refs match committed
  registries.
- Event kind and typed detail object match
  [docs/schema/event.md](../schema/event.md).
- Every evidence URL is official, public, unauthenticated, and inside the source
  descriptor's allowed domains.
- Evidence metadata is bounded to hashes, timestamps, URLs, selectors, and short
  notes; raw source content is not committed.
- Event dates use `date_confidence` when the provider source is ambiguous.
- Each `ImpactAssessment` row has an affected scope, impact kind, direction,
  severity, confidence, audience, and recommended action.
- Limitations call out preview availability, regional/account variance,
  approximate dates, or partial source coverage.
- Duplicate, noisy, rejected, or split candidates are explained in the PR body
  or review notes.

## Release-Manager Checklist

- PR is small enough to audit and contains no raw provider page text, private
  Ottto surfaces, secrets, customer data, or authenticated screenshots.
- `data/events/`, `data/feeds/`, `data/indexes/`, and `data/releases/dev/` are
  consistent with `uv run apw index --check`.
- Local commands passed: `uv lock --check`, `uv run ruff check .`,
  `uv run pytest`, `uv run apw source test`, `uv run apw validate`,
  `uv run apw index --check`, and `uv run apw release dry-run --output
  .apw/release-dry-run`.
- GitHub CI, CodeQL, Dependency Review, branch protection, repository security
  settings, artifact checksums, release manifest, attestation verification, and
  signed tag plan are recorded before any `data-YYYY.MM.DD` tag.
- No workflow that fetched source pages, generated candidates, processed PR
  comments, ran LLM review, or served MCP had a release token.

## Resolution Examples

### Promote One Candidate

Use this when a candidate maps cleanly to one provider change.

- Confirm the official evidence and event facts as source owner.
- Add `data/events/YYYY-MM-DD-provider-short-slug.json`.
- Run `uv run apw validate`, `uv run apw index`, and
  `uv run apw index --check`.
- In the PR body, record `candidate-... -> YYYY-MM-DD-provider-short-slug` and
  link the official evidence URL.

### Close As Duplicate

Use this when the candidate points to a change already represented by a
reviewed event.

- Confirm the existing event covers the same provider, date, surface, and
  impact.
- Do not create a new event file.
- Comment on the candidate-review PR with `duplicate of <event-id>` or, when
  keeping durable candidate state in the branch, set `review_status` to
  `duplicate`.
- If the duplicate is caused by parser instability, file a parser/source issue
  instead of merging repeated candidate churn.

### Reject As Noisy

Use this when the source changed but there is no developer-relevant provider
change.

- Confirm the page change is navigational, formatting-only, unavailable for
  official review, or outside APW scope.
- Do not publish an event.
- Comment with the rejection reason or set `review_status` to `rejected` in the
  candidate-review branch.
- If the noise will recur, narrow the source descriptor `content_scope` or add a
  parser fixture before relying on future automation.

### Split A Candidate

Use this when one source update includes multiple independent provider changes.

- Create one event per independent effective date, provider surface, or event
  kind.
- Reuse the same evidence URL and hash only when the official source supports
  every event.
- Give each event distinct impact rows and limitations.
- Record the split in the PR body as `candidate-... -> event-a, event-b`.

## Evidence Paths

- Review candidates: `data/candidates/review/*.json`
- Reviewed events: `data/events/*.json`
- Generated feeds: `data/feeds/events.json`, `data/feeds/events.ndjson`,
  `data/feeds/feed.json`, `data/feeds/latest.json`, `data/feeds/rss.xml`
- Generated indexes: `data/indexes/provider/*`, `data/indexes/kind/*`,
  `data/indexes/severity/*`
- Development release manifest: `data/releases/dev/manifest.json`
- Local source-owner packet: `.apw/source-owner-packet.json`
- Local candidate-to-event packet: `.apw/candidate-to-event-packet.json`
- Local ignored review notes: `.apw/event-promotion/<candidate-id>/review.md`
- Local dry-run evidence:
  `.apw/release-dry-run/data-YYYY.MM.DD/dry-run-report.json`,
  `.apw/release-dry-run/data-YYYY.MM.DD/manifest.json`, and
  `.apw/release-dry-run/data-YYYY.MM.DD/checksums.txt`
