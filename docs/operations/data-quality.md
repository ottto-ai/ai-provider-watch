# Data Quality And Operations Report

APW publishes a machine-readable operations report at
`data/feeds/operations.json`. It is a public health surface for source
freshness, source coverage, candidate backlog, contributor intake, correction
policy, and release-train posture.

Use `data/feeds/source-catalog.json` for the provider/source support matrix and
per-source validation metadata. Use `data/feeds/coverage.json` for compact
source-health warnings. Use `data/feeds/operations.json` for public operating
SLOs and release-train posture.

Render it locally:

```bash
uv run apw operations report
uv run apw operations report --summary
uv run apw operations report --output .apw/operations.json
```

The report is generated from committed APW data: reviewed events, source
registry descriptors, source-state fingerprints, review candidates, issue
template presence, and governance docs. It does not fetch provider pages, read
issue bodies, call GitHub, post webhooks, publish feeds, create tags, request
OIDC, or use release tokens.

## SLOs

The v0 operations report starts with conservative visibility targets:

- latest reviewed event age should stay within 14 days;
- source-state freshness should stay within 72 hours;
- at least 80% of enabled deterministic sources should have committed
  source-state fingerprints;
- candidate backlog should trend toward zero;
- missing-event, correction, source, and downstream-mapping issue templates
  should exist.

Current failures are disclosures, not automatic release blockers. Release
blockers still live in [release gates](release-gates.md). A release manager can
turn any SLO into a gate in a separate governance PR.

## Corrections And Retractions

The report points to the correction/retraction policy in
[v1 governance](v1-governance.md#correction-and-retraction-policy). APW does not
measure correction latency until public issue volume exists. Until then,
correction PRs must list corrected or retracted event IDs, evidence URLs,
generated artifacts, validation commands, and downstream action required.

## Boundaries

The operations report contains counts, timestamps, paths, warning codes, and
policy references only. It contains no raw provider content, private Ottto
surface, customer data, authenticated-console data, credentials, issue body,
PR-comment text, social text, MCP text, or LLM transcript.
