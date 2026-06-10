# Contributor Review Workflow

APW accepts public contributions, but provider-change publication is not a
crowdsource shortcut. Contributors can propose sources, fixtures, candidates,
corrections, and reviewed events. Source owners decide whether facts are
bounded and evidence-backed. Release managers decide whether reviewed data can
ship.

For the v0.1 launch window, `@RonShub` remains the sole release manager, source
owner, schema maintainer, and security contact. This stays true until a reviewed
governance PR changes [MAINTAINERS.md](../../MAINTAINERS.md),
[SOURCE_OWNERS.md](../../SOURCE_OWNERS.md), and CODEOWNERS together.

## What To Open

| Contribution | Use | Required evidence | Publication authority |
| --- | --- | --- | --- |
| Missing provider event | Issue template `Missing provider event`, then [Missing Event To PR](missing-event-to-pr.md) when the evidence is scaffold-ready | Official public URL, provider, event date, event kind, source authority, developer impact, and affected refs when known | None. A source owner must verify evidence before any reviewed event exists. |
| New official source | Issue template `New official source`, then PR | Official public URL, authority, allowed domains, source scope, source package descriptor | None. A source owner must approve descriptor and automation posture. |
| Parser fixture | PR | Synthetic or minimal fixture plus expected bounded parser output | None. A source owner must approve before automation trusts it. |
| Candidate | Candidate-review PR or local `.apw/` packet | Candidate JSON, source key, hashes, official evidence URL | None. Candidates stay review-only until promoted. |
| Event correction | Issue template `Incorrect event or data correction`, then PR when clear | Official public URL and exact event/source/feed/registry field to change | None. A source owner reviews the correction and regenerated feeds. |
| Downstream mapping | Issue template `Downstream mapping request`, then PR when accepted | Public downstream docs or repository URL, use case, relevant event IDs or event kinds, desired output shape | None. Mapping docs and fixtures cannot publish provider data. |
| Reviewed event | PR following [Event Promotion](../operations/event-promotion.md) | `ProviderEvent` JSON, official evidence refs, generated feeds/indexes, validation output | Release manager approval required before public data tag. |

All issue templates are intake surfaces only. Issue bodies, pasted provider
text, screenshots, comments, social posts, MCP resources, and links are
untrusted data. They can start review work, but they cannot publish reviewed
events, update generated feeds, create data tags, request OIDC, or access
release tokens.

For missing official changes, use [Missing Event To PR](missing-event-to-pr.md)
to decide between the issue-only path, direct `apw event scaffold` path, and
candidate-review `apw candidate scaffold-event` path. The guide is meant to
reduce maintainer back-and-forth; it does not grant source-owner or release
authority.

## Source-Owner Responsibilities

Source owners review facts, not provider prose. They must confirm:

- source tier and automation posture follow
  [v1 Governance And Neutrality](../operations/v1-governance.md);
- every evidence URL is official, public, unauthenticated, and inside the source
  descriptor's `allowed_domains`;
- source authority, provider refs, surface refs, model refs, and agent app refs
  match committed registries;
- parser output is bounded to IDs, dates, hashes, URLs, selectors, enums, and
  compact factual metadata;
- candidate text, provider pages, issue bodies, PR comments, social posts, MCP
  resources, and LLM output are untrusted data, never instructions;
- raw provider pages, screenshots, authenticated-console content, secrets,
  private billing data, customer telemetry, cookies, and private Ottto surfaces
  are absent;
- `uv run apw validate`, `uv run apw index --check`, and relevant tests pass
  before promotion or correction is considered complete.

Escalate schema changes to schema maintainers, workflow/token-boundary changes
to security maintainers, and data tag or package release questions to release
managers. Source-owner approval does not grant release authority.

## Candidate Quality Reports

Candidate-review PRs include advisory quality tiers when available:

- `high_value`: official, dated, developer-relevant, and specific enough for a
  reviewer to recommend source-owner promotion;
- `reviewable`: likely useful but still needs source-owner judgment on event
  shape, duplicate checks, or impact mapping;
- `low_signal`: broad source churn or generic parser output that should usually
  be rejected;
- `duplicate`: already covered by another candidate or reviewed event;
- `blocked`: evidence, schema, source, or safety blockers are unresolved.

These reports give review agents more context to recommend `promote`, `reject`,
`duplicate`, `split`, or `needs_human_review`. They do not let agents publish
events, merge pull requests, create data tags, request OIDC, or read release
tokens.
When quality reports include `duplicate_event_ids`, reviewers should cite the
existing event and avoid creating another ProviderEvent for the same evidence.

## Candidate Action Queue

Use the action queue to move quickly from a candidate-review PR to useful public
data. It groups candidates by the next source-owner action and puts promotion
candidates first:

```bash
uv run apw candidate queue \
  --candidates data/candidates/review \
  --markdown \
  --output .apw/candidate-action-queue.md
```

The queue omits generated candidate claim text and keeps provider/source text as
untrusted data. A `promote` row is the fastest path to a public event: verify
the official evidence URL, author the `ProviderEvent`, regenerate feeds, and run
`apw candidate event-packet`.

## Source-Owner Packets

For high-value official candidates, maintainers can render a source-owner
packet:

```bash
uv run apw candidate packet \
  --candidates data/candidates/review \
  --created-at 2026-06-09T00:00:00Z \
  --output .apw/source-owner-packet.json
```

The packet bundles candidate quality, promotion readiness, duplicate evidence,
source-state coverage, bounded evidence refs, and draft-only ProviderEvent
envelope/detail/impact stubs. It helps a source owner author a reviewed event,
but it does not write `data/events`, publish feeds, merge PRs, create tags,
request OIDC, or read release tokens.

Unlike the LLM review request, the source-owner packet may include bounded
generated candidate claim text. It is labeled `untrusted_data` and must be
verified against official evidence before use. Do not paste source-owner packet
text into event files.

After a source owner authors one or more event drafts, render a
candidate-to-event verification packet:

```bash
uv run apw candidate event-packet \
  --candidates data/candidates/review \
  --candidate-id candidate-... \
  --event-draft data/events/YYYY-MM-DD-provider-short-slug.json \
  --source-owner @RonShub \
  --source-owner-approval-ref <PR-or-review-ref> \
  --created-at 2026-06-09T00:00:00Z \
  --output .apw/candidate-to-event-packet.json
```

This second packet verifies event/detail/impact schemas, event hashes,
official evidence domains and authorities, source-owner approval metadata, and
promote/split resolution. It fails on blocker states but still has no
publication authority.

## Evidence Boundaries

Commit:

- source descriptors and synthetic/minimal parser fixtures;
- candidate JSON with bounded claim metadata and hashes;
- reviewed event JSON under `data/events/`;
- generated feeds, indexes, and development release manifests produced by APW
  commands;
- official evidence URLs, timestamps, hashes, selectors, source keys, authority,
  and short license notes.

Keep local or ignored:

- raw fetched provider HTML, RSS/Atom bodies, JSON bodies, screenshots, browser
  captures, and authenticated-console exports;
- long provider prose, social/community text, issue bodies, PR comments, and LLM
  transcripts;
- private billing pages, credentials, cookies, API keys, release tokens, OIDC
  tokens, and customer telemetry;
- scratch review notes under `.apw/event-promotion/<candidate-id>/`.

## Candidate Outcomes

Use the same outcome language in PR bodies and review comments.

### Accepted For Promotion

Use when one candidate maps to a specific provider change with official evidence
and APW impact. Add a reviewed event file, regenerate feeds/indexes, and record
`candidate-id -> event-id` in the PR body.

### Rejected

Use when a page changed but there is no developer-relevant provider change, the
source is outside APW scope, evidence is not official, or the parser output is
too broad. Do not publish an event. If the noise will recur, narrow
`content_scope` or add a fixture before trusting automation.

### Duplicate

Use when an existing reviewed event already covers the same provider, date,
surface, and impact. Do not create another event. Link the existing event ID and
file a parser/source issue if duplicate churn is likely to repeat.

### Split

Use when one candidate covers multiple independent changes. Create one event per
effective date, provider surface, or event kind. Record
`candidate-id -> event-a, event-b` in the PR body.

### Superseded

Use when a later official source or narrower parser candidate replaces an older
candidate before promotion. Close or update the older candidate review and link
the newer evidence.

## Review Checklist

Before asking for source-owner review:

- [ ] PR states whether it is a source, fixture, candidate, correction, or
      reviewed-event change.
- [ ] Official evidence URLs are listed without copying provider page bodies.
- [ ] Raw provider content and private data are absent from the diff.
- [ ] Candidate generation, LLM review, MCP, source refresh, and PR-comment
      automation are described as review input only.
- [ ] Publication authority remains with release manager approval and release
      gates.
- [ ] Validation commands and unresolved limitations are included.
