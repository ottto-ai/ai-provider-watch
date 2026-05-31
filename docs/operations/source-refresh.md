# Source Refresh

Phase 2 introduces deterministic official-source fingerprints.

Run locally:

```bash
uv run apw source test
uv run apw source fetch --observations .apw/source-observations.json
```

To update committed source state:

```bash
uv run apw source fetch --write-state --observations .apw/source-observations.json
```

The scheduled workflow runs daily and opens a draft PR only when
`data/source-state/fingerprints.json` changes. Raw provider content is fetched,
hashed, and discarded. Event promotion remains a separate maintainer-reviewed
workflow.

## Review Candidate Contract

APW-2.02 adds deterministic candidate generation from observation bundles:

```bash
uv run apw candidate generate \
  --observations .apw/source-observations.json \
  --output .apw/candidates \
  --created-at 2026-05-31T20:15:00Z
```

Candidate output is review input only. The daily workflow must not publish
events from candidates without maintainer review, and workflows that process
source content must not receive release tokens.
