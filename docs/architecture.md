# Architecture

AI Provider Watch is a file-first, deterministic event intelligence project.

APW owns public provider facts, schemas, source descriptors, generated feeds, and
validation. It does not own private Ottto staff UI, Advisor behavior, customer
telemetry, billing credentials, or internal deployment infrastructure.

```text
SourceDescriptor -> Observation -> FindingCandidate -> ProviderEvent
                                             |
                                             v
                           feeds, indexes, release manifests, CLI, MCP
```

The deterministic path must work without an LLM key:

```bash
apw validate
apw index
apw latest
apw diff --since 7d
apw explain <event-id>
apw release dry-run
```

LLM or agent curation is optional. Audited repository `ProviderEvent` promotion
must be fenced by validation, source allowlists, and maintainer review.
Provisional live-feed publication may run autonomously from official
source-controlled evidence when it is schema-valid, provenance-labeled, and
correctable.

## Core Entities

- `Provider`: stable provider identity.
- `ProviderSurface`: concrete API, status page, docs, subscription, marketplace,
  or agent surface.
- `ModelRef`: provider-native model or alias.
- `AgentApp`: consumer app or coding-agent surface.
- `SourceDescriptor`: maintainer-owned source contract.
- `Observation`: raw fetch output, not a published event.
- `FindingCandidate`: reviewable claim derived from observations.
- `ProviderEvent`: reviewed canonical event envelope.
- `EventDetail`: typed payload for the event kind.
- `ImpactAssessment`: affected scope row.
- `EvidenceRef`: source-backed proof pointer.
- `LiveItem`: provisional news item produced from official observations,
  parser deltas, and live publication policy. Live items can be automated,
  agent-reviewed, needs-followup, promoted, superseded, or retracted.
- `LiveFeed`: high-frequency JSON/RSS/Atom view of `LiveItem` records for users
  who need current provider-change news before audited repository snapshots are
  updated.
- `FeedFreshness`: generated provenance summary for feed version, package
  version, latest event date, source-state timestamp, release manifest path,
  checksum manifest path, and feed/index artifact hashes.
- `JsonFeed`: JSON Feed 1.1 view over reviewed ProviderEvents for downstream
  feed readers, static sites, and agent dashboards.
- `SourceCoverageReport`: generated feed-health summary for enabled source
  coverage, source-state freshness, blocked parser sources, manual-review-only
  sources, reviewed event counts, and review-candidate backlog.
- `ReleaseManifest`: published artifact manifest with checksums.
- `ReleaseDryRunReport`: local pre-release evidence bundle with checks,
  generated CalVer artifacts, and required external gates.

Use a stable `ProviderEvent` envelope plus typed `EventDetail` union and
repeatable `ImpactAssessment` rows. Unknown extensions belong under explicitly
named `x_*` fields in future schema versions, not arbitrary top-level fields.

## Registries

Registries are separate from events:

- `registries/providers.json`
- `registries/provider-surfaces.json`
- `registries/models.json`
- `registries/agent-apps.json`

Events reference registries by stable refs such as `provider:openai`,
`surface:openai/api`, `model:openai/gpt-4.1`, or `app:codex`.

## Source Policy

Official provider-controlled sources can support reviewed publication after
deterministic validation. Social, community, and third-party sources can create
review candidates, but they do not publish canonical events unattended.

The high-frequency live publisher has a different bias from the audited
repository path. It may publish provisional automated or agent-reviewed live
items from official source-controlled evidence, including `needs_followup`
items, when the item carries source authority, parser confidence, publication
lane, reason codes, and correction state. Community-only, social-only, issue,
PR, and MCP text remain candidate-only.

## Candidate Pipeline

`FindingCandidate` records are review packets, not facts. The deterministic
candidate contract consumes observation metadata and parser-produced
`candidate_claims`; it does not execute source text or treat provider prose as
instructions. Candidate claims are deliberately narrow: bounded claim text plus
an optional kind. Prompt-like claim text is rejected. Arbitrary nested parser
output is not persisted. Candidate IDs are stable over source key, fingerprint,
and claim text so refresh PRs can dedupe noisy source changes. Duplicate
candidate IDs fail generation instead of overwriting review files, and default
writes refuse to clobber existing candidate files. Evidence URLs must use
`https` and match the source descriptor's `allowed_domains`; off-domain
observation URLs are rejected instead of being labeled with official authority.
Fingerprints are persisted only as SHA-256 values, and snapshot references are
bounded identifiers rather than raw source payloads.
When a source descriptor declares `content_scope`, APW computes the fingerprint
from the scoped content while keeping `content_sha256` as the full response
hash.
Pricing parsers may additionally persist bounded `pricing_rows` facts in source
state so later refreshes can compare model, billing dimension, numeric price,
unit, and pricing-signal enums. This row state is not provider prose and is not
a published event. Row-level pricing/token-accounting deltas produce
selector-scoped review candidates; they still require source-owner review before
promotion because pricing pages generally lack an independent dated change
signal.
Model and pricing parsers may also persist bounded `operational_rows` facts for
quota/rate-limit and default-model signals. That state is limited to model IDs,
default scopes, limit dimensions, numeric limit values, units, row keys, and row
hashes. Operational row deltas produce selector-scoped review candidates for
quota, rate-limit, and default-model changes, but they stay out of promotion
readiness unless a separate dated official source supports the change.

Candidate files carry:

- source keys and provider refs;
- normalized claim text;
- candidate kind;
- evidence refs with source URL, retrieval timestamp, authority, content hash,
  and fingerprint;
- parser name and contract version;
- review status and dedupe key;
- an explicit untrusted-input policy.

Promotion from candidate to `ProviderEvent` remains a maintainer-reviewed PR
step.

## Live Publisher Posture

The live publisher is the current-news surface, not the signed data-release
surface. It should publish compact JSON/RSS/Atom artifacts every 15 minutes to a
stable public URL without creating repository commits, Python package releases,
or signed Git tags for each run.

The first live lane should optimize for recall and speed:

- auto-publish official status incidents and dated official changelog, release
  note, or news entries;
- publish scoped official docs, pricing, quota, default-model, and lifecycle
  parser deltas as `needs_followup` when the parser names concrete subjects;
- run cheap agent review over sanitized extracted facts to improve
  classification and summaries without treating source text as instructions;
- keep public health, provenance, confidence labels, and correction/retraction
  state so imperfect early items can be fixed quickly;
- run a daily improvement loop that deduplicates live items, promotes clear
  events through audited PRs, adds parser fixtures, and reports misses or false
  positives.

GitHub Actions on a 15-minute schedule is acceptable for a low-cost v0 or
dry-run lane, but it is a best-effort scheduler. A durable public feed should
publish to object storage or CDN-backed static hosting, and should move the
scheduler off GitHub if missed runs become a freshness problem.

Prompt-injection regressions live in
`tests/fixtures/redteam/untrusted-input-cases.json` and are exercised by
`tests/test_prompt_injection_redteam.py`. New agent-facing surfaces must pass
those cases before they can process provider/source/candidate text.

## MCP Posture

The MCP package is read-only by default. Publishing, source mutation, release
signing, and event promotion stay outside MCP until explicit local CLI/PR
workflows authorize them.
