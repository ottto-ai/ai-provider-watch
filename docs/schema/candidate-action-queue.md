# Candidate Action Queue

`schemas/candidate-action-queue.schema.json` describes the queue produced by
`apw candidate queue`.

The queue is a contributor and source-owner triage view over existing
candidate-quality and promotion-readiness reports. It groups review-only
candidates by the next action:

- `promote`: start here first; verify official evidence and author a reviewed
  `ProviderEvent`;
- `needs_human_review`: useful-looking evidence that needs a source-owner
  decision on event shape, split, duplicate, or rejection;
- `duplicate`: close against an existing reviewed event;
- `reject`: close or narrow parser/source scope because no APW event should be
  published from the candidate.

The queue intentionally omits generated candidate claim text. It contains
candidate IDs, paths, kinds, provider refs, source keys, evidence URLs, scores,
duplicate event IDs, and next-step instructions.

## Command

```bash
uv run apw candidate queue \
  --candidates data/candidates/review \
  --created-at 2026-06-10T00:00:00Z
```

Render a compact Markdown queue for a PR comment or source-owner handoff:

```bash
uv run apw candidate queue \
  --candidates data/candidates/review \
  --created-at 2026-06-10T00:00:00Z \
  --markdown \
  --limit-per-group 12
```

## Safety Contract

`apw candidate queue` is advisory. It does not write `data/events`, mutate
candidate files, change source state, merge PRs, create tags, request OIDC, or
read release tokens.

`promote` means "review this first and turn it into a sourced event if the
official evidence checks out." It does not mean "publish automatically."
