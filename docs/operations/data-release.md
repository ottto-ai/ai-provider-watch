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
`.apw/release-dry-run/data-YYYY.MM.DD/`. The GitHub workflow also packages that
bundle as `.apw/apw-release-dry-run.tgz` and creates an artifact attestation for
it. The bundle includes release-shaped feed artifacts,
`data/releases/data-YYYY.MM.DD/manifest.json`, checksums, and a schema-backed
`dry-run-report.json`.

The dry run does not publish a tag, upload a release, or require a release
token. A public data tag still requires maintainer review, green GitHub CI,
CodeQL workflow completion, a matching GitHub code-scanning analysis for the
release commit, `uv lock --check`, Dependency Review, branch protection,
repository security settings, artifact checksum review, attestation
verification, release manager approval, and a signed tag plan. Release
automation stays dry-run only until the [release gates](release-gates.md) and
[repository settings](repository-settings.md) are recorded.

Dependency Review is currently a manual gate with explicit `base_ref` and
`head_ref` inputs. If GitHub dependency graph or Dependency Review support is
unavailable, the release is blocked until maintainers enable support and record
the concrete resolution.

## Evidence Packets

- [2026-06-01 `data-2026.06.01` dry run](release-evidence/2026-06-01-data-2026.06.01-dry-run.md):
  first successful manual workflow dry run on public `main`, with 15 passing
  report checks and release-shaped artifact checksums. No tag was created.
