# Data Release

Data releases use CalVer tags such as `data-2026.06.01`.

Each release should include generated feeds, provider/kind/severity indexes,
manifest with artifact hashes, source commit, schema version, and a short
release summary.

Before a release:

```bash
uv run pytest
uv run apw validate
uv run apw index --check
```

Release automation starts in dry-run mode until branch protection, maintainer
review, and artifact attestation are configured.
