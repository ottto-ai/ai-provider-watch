# v1 Launch Gate Schema

`schemas/v1-launch-gate.schema.json` describes the report produced by:

```bash
apw operations launch-gate
```

The report is an external-user readiness contract. It combines deterministic
local checks with required manual smoke commands for fresh PyPI install,
installed package-data reads, checkout reads, downstream repo-impact fixtures,
agent-dashboard JSON, and public feed parsing.

Important fields:

- `status`: `fail` when local deterministic checks fail, otherwise
  `manual_required` until the release manager records external smoke evidence.
- `required_feed_artifacts`: feed paths that must be present and listed in
  freshness and release-manifest metadata.
- `local_checks`: deterministic checks run from the current checkout.
- `external_smoke_steps`: commands and pass criteria for fresh-environment
  verification.
- `policy`: read-only/no-private-Ottto/no-credential boundaries.

The schema is bundled in the Python package data so installed clients can
validate saved launch-gate evidence without cloning the repository.
