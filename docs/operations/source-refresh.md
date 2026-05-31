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
