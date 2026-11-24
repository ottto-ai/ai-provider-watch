# Candidate To Event Packet

`schemas/candidate-to-event-packet.schema.json` describes the verification
packet produced by `apw candidate event-packet`.

Use this packet after a source owner has authored one or more draft
`ProviderEvent` JSON files. It verifies that the candidate, event draft files,
schemas, evidence refs, source-owner approval, and promote/split resolution are
coherent before a promotion PR is trusted.

## Command

```bash
uv run apw candidate event-packet \
  --candidates data/candidates/review \
  --candidate-id candidate-openai-news-... \
  --event-draft data/events/2026-06-04-openai-example.json \
  --source-owner @RonShub \
  --source-owner-approval-ref https://github.com/ottto-ai/ai-provider-watch/pull/123#source-owner \
  --created-at 2026-06-09T00:00:00Z \
  --output .apw/candidate-to-event-packet.json
```

Repeat `--event-draft` for a split candidate:

```bash
uv run apw candidate event-packet \
  --candidates data/candidates/review \
  --candidate-id candidate-openai-news-... \
  --event-draft data/events/2026-06-04-openai-event-a.json \
  --event-draft data/events/2026-06-04-openai-event-b.json \
  --source-owner @RonShub \
  --source-owner-approval-ref https://github.com/ottto-ai/ai-provider-watch/pull/123#source-owner \
  --created-at 2026-06-09T00:00:00Z \
  --output .apw/candidate-to-event-packet.json
```

The command exits nonzero when blockers remain. It still writes the packet to
`--output` so reviewers can inspect the machine-readable blocker report. Use
`--allow-blockers` only when intentionally collecting advisory output.

## Checks

The packet verifies:

- candidate readiness is promotable, not `not_ready` or
  `duplicate_or_superseded`;
- candidate quality action is `promote` or `needs_human_review`, not `reject`
  or `duplicate`;
  - `duplicate` is advisory only when the reviewed duplicate event IDs include
    every event draft ID in the packet, which can happen after the source owner
    has already authored drafts into `data/events/`;
- candidate claim text is omitted and represented by hash, length, and
  prompt-like metadata;
- every event draft passes event, detail, and impact schemas;
- event lifecycle status is `reviewed`;
- event kind matches the candidate kind for this v0 packet;
- event provider refs overlap candidate provider refs;
- event evidence has at least one candidate source key;
- evidence source keys exist, authorities match source descriptors, URLs are
  inside allowed domains, and authorities are official provider-controlled;
- event draft text does not contain prompt-like instructions;
- split/promote resolution and event hashes are recorded.

## Safety Contract

The command writes only stdout or the requested output file. It does not author
events, mutate candidates, update source state, regenerate feeds, open PRs,
merge, tag, publish, request OIDC, or read release tokens.

This packet complements `apw candidate packet`:

- `apw candidate packet` helps a source owner decide what to author.
- `apw candidate event-packet` verifies already-authored event drafts before
  promotion PR review.
