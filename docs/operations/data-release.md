# Data Release

Data releases use CalVer tags such as `data-2026.06.01`.

Each release should include generated feeds, provider/kind/severity indexes,
manifest with artifact hashes, source commit, schema version, and a short
release summary.

Before a release:

```bash
uv run ruff check .
uv lock --check
uv run pytest
uv run apw source test
uv run apw validate
uv run apw index --check
uv run apw release dry-run --output .apw/release-dry-run --require-clean
```

The dry run writes an ignored evidence bundle under
`.apw/release-dry-run/data-YYYY.MM.DD/`. It includes release-shaped feed
artifacts, `data/releases/data-YYYY.MM.DD/manifest.json`, checksums, and a
schema-backed `dry-run-report.json`.

The dry run does not publish a tag, upload a release, or require a release
token. A public data tag still requires maintainer review plus green GitHub CI,
CodeQL, `uv lock --check`, and Dependency Review when GitHub dependency graph
support is available for the repository. Release automation stays dry-run only
until branch protection, maintainer review, and artifact attestation are
configured.

## Evidence Packets

- [2026-06-01 `data-2026.06.01` dry run](release-evidence/2026-06-01-data-2026.06.01-dry-run.md):
  first successful manual workflow dry run on public `main`, with 15 passing
  report checks and release-shaped artifact checksums. No tag was created.
