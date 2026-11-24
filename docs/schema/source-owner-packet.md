# Source Owner Packet

`schemas/source-owner-packet.schema.json` describes the review-only packet
produced by `apw candidate packet`.

The packet is for human source owners who need to decide whether high-value
official-source candidates should become reviewed `ProviderEvent` files. It is
not a publisher and is not an event file.

## Command

```bash
uv run apw candidate packet \
  --candidates data/candidates/review \
  --created-at 2026-06-09T00:00:00Z \
  --output .apw/source-owner-packet.json
```

By default, the packet includes only candidate-quality rows whose
`recommended_action` is `promote`. Repeat `--recommended-action` to include
other advisory outcomes for a wider review packet:

```bash
uv run apw candidate packet \
  --candidates data/candidates/review \
  --recommended-action promote \
  --recommended-action needs_human_review \
  --created-at 2026-06-09T00:00:00Z \
  --output .apw/source-owner-packet.json
```

## Contents

Each candidate row includes:

- candidate ID, file path, kind, source keys, provider refs, review status, and
  dedupe key;
- candidate-quality tier, recommended action, score, reasons, blockers, and
  duplicate reviewed-event IDs;
- promotion-readiness flags, reasons, blockers, and recommendation;
- source descriptor context plus bounded source-state metadata when available;
- evidence refs limited to source key, URL, authority, timestamps, hashes,
  optional selector, and optional snapshot ref;
- a bounded generated candidate claim labeled as `untrusted_data`;
- draft-only ProviderEvent envelope hints, detail stub, impact stubs, required
  source-owner fields, and the promotion checklist.

The detail and impact stubs are intentionally incomplete. A source owner must
replace them before any reviewed event can pass `apw validate`.

## Safety Contract

`apw candidate packet` writes only the requested output path or stdout. It does
not write `data/events`, mutate candidates, update source state, create PRs,
merge, tag, publish releases, request OIDC, or read release tokens.

The packet may include generated candidate claim text because its audience is a
human source owner. That text is bounded and explicitly marked
`untrusted_data`. Do not pass this packet directly as an LLM instruction prompt.
For model reviewers, use `apw review request`, which omits candidate claim text
and carries only hashes, lengths, prompt-like flags, evidence refs, readiness,
and quality context.

## Promotion Rule

A `promote` row means the deterministic readiness and quality gates found
official, dated, high-value evidence suitable for source-owner review. It still
does not mean "publish automatically." Source owners must verify official
evidence directly, author a reviewed event, regenerate feeds, and pass the
release checks described in [Event Promotion](../operations/event-promotion.md).
