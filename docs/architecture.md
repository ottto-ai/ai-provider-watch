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
```

LLM or agent curation is optional and must be fenced by validation, source
allowlists, and human review.

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
- `ReleaseManifest`: published artifact manifest with checksums.

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

## Candidate Pipeline

`FindingCandidate` records are review packets, not facts. The deterministic
candidate contract consumes observation metadata and parser-produced
`candidate_claims`; it does not execute source text or treat provider prose as
instructions. Candidate claims are deliberately narrow: bounded claim text plus
an optional kind. Arbitrary nested parser output is not persisted. Candidate IDs
are stable over source key, fingerprint, and claim text so refresh PRs can
dedupe noisy source changes. Duplicate candidate IDs fail generation instead of
overwriting review files, and default writes refuse to clobber existing
candidate files. Evidence URLs must use `https` and match the source descriptor's
`allowed_domains`; off-domain observation URLs are rejected instead of being
labeled with official authority.
Fingerprints are persisted only as SHA-256 values, and snapshot references are
bounded identifiers rather than raw source payloads.

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

## MCP Posture

The MCP package is read-only by default. Publishing, source mutation, release
signing, and event promotion stay outside MCP until explicit local CLI/PR
workflows authorize them.
