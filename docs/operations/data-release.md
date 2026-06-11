# Data Release

Data releases use CalVer tags such as `data-2026.06.01`.

Each release should include generated feeds, `data/feeds/feed.json`,
`data/feeds/freshness.json`, `data/feeds/coverage.json`,
`data/feeds/operations.json`,
provider/kind/severity indexes, manifest with artifact hashes, source commit,
schema version, and a short release summary.

Before a release:

```bash
uv run ruff check .
uv lock --check
uv run pytest
uv run apw source test
uv run apw source coverage --summary
uv run apw operations report --summary
uv run apw release automation-readiness --summary
uv run apw validate
uv run apw index --check
uv run apw release dry-run --output .apw/release-dry-run --require-clean
```

The dry run writes an ignored evidence bundle under
`.apw/release-dry-run/data-YYYY.MM.DD/`. The GitHub workflow also packages that
bundle as `.apw/apw-release-dry-run.tgz` and creates an artifact attestation for
it. The bundle includes release-shaped feed artifacts,
`data/feeds/freshness.json`,
`data/feeds/coverage.json`,
`data/feeds/operations.json`,
`data/feeds/feed.json`,
`data/releases/data-YYYY.MM.DD/manifest.json`,
`data/releases/data-YYYY.MM.DD/evidence-index.json`, checksums, and a
schema-backed `dry-run-report.json`.

The evidence index is the stable machine-readable release contract for humans,
agents, package consumers, and downstream automation:

```bash
uv run apw release evidence-index \
  --release-id data-YYYY.MM.DD \
  --source-commit "$(git rev-parse HEAD)" \
  --output .apw/release-dry-run/data-YYYY.MM.DD/evidence-index.json
```

It lists release artifacts, local validation commands, external GitHub/PyPI
evidence, OpenSSF Scorecard, artifact attestation verification, workflow
authority, token boundaries, and the policy that raw provider content is not
part of release artifacts.

Use `apw freshness --summary` before publishing to record package version,
release ID, latest event date, latest source-state retrieval timestamp, and the
checksum manifest path in release evidence.

Use `apw source coverage --summary` before publishing to record enabled source
coverage, missing source-state fingerprints, blocked parser sources, and review
candidate backlog. Coverage warnings are visibility signals, not automatic
publication approval.

Use `apw operations report --summary` before publishing to record operating
SLOs, source-state freshness, candidate backlog, contributor intake, correction
policy, and release-train posture. Operations failures are disclosures unless a
release manager has explicitly promoted that SLO to a release gate.

Use `apw release automation-readiness --summary` to record the release
automation decision. In v0.x, `status: blocked` is expected because unattended
publication still lacks an approved signing-equivalent mechanism; `status:
fail` means a local release workflow, token boundary, or policy document
regressed.

Generate a schema-backed publication packet before creating any real data tag:

```bash
uv run apw release packet \
  --dry-run-report .apw/release-dry-run/data-YYYY.MM.DD/dry-run-report.json \
  --release-manager @RonShub \
  --source-owner @RonShub \
  --source-owner-approval-ref "<PR-or-issue-source-owner-approval-url>" \
  --release-manager-approval-ref "<release-manager-approval-url>" \
  --branch-protection-ref "<branch-protection-api-output-or-runbook-ref>" \
  --ci-ref "<successful-CI-run-url>" \
  --codeql-workflow-ref "<successful-CodeQL-run-url>" \
  --code-scanning-ref "<code-scanning-analysis-id-or-url>" \
  --dependency-review-ref "<successful-Dependency-Review-run-url>" \
  --scorecard-ref "<successful-Scorecard-run-url>" \
  --attestation-ref "<gh-attestation-verify-output-ref>" \
  --checksum-review-ref "<checksum-review-ref>" \
  --reviewed-event "<event-id>" \
  --output .apw/release-dry-run/data-YYYY.MM.DD/publication-packet.json
```

The packet is not a publisher. It records the exact reviewed inputs required
for a tag: reviewed event IDs or an explicit skip reason, source-owner approval,
release-manager approval, CI, CodeQL, code-scanning, Dependency Review, branch
protection, checksum review, attestation verification, and the manual signed-tag
commands. If no source-owner-reviewed events landed for the date, render a skip
packet instead:

```bash
uv run apw release packet \
  --dry-run-report .apw/release-dry-run/data-YYYY.MM.DD/dry-run-report.json \
  --release-manager @RonShub \
  --source-owner @RonShub \
  --source-owner-approval-ref "<source-owner-skip-approval-url>" \
  --release-manager-approval-ref "<release-manager-skip-approval-url>" \
  --branch-protection-ref "<branch-protection-api-output-or-runbook-ref>" \
  --ci-ref "<successful-CI-run-url>" \
  --codeql-workflow-ref "<successful-CodeQL-run-url>" \
  --code-scanning-ref "<code-scanning-analysis-id-or-url>" \
  --dependency-review-ref "<successful-Dependency-Review-run-url>" \
  --scorecard-ref "<successful-Scorecard-run-url>" \
  --attestation-ref "<gh-attestation-verify-output-ref>" \
  --checksum-review-ref "<checksum-review-ref>" \
  --allow-no-reviewed-events \
  --skip-reason "No source-owner-reviewed ProviderEvent changes landed for this release date." \
  --output .apw/release-dry-run/data-YYYY.MM.DD/publication-packet.json
```

Verify the local dry-run artifact set and optional publication packet before
signing:

```bash
uv run apw release verify \
  --dry-run-report .apw/release-dry-run/data-YYYY.MM.DD/dry-run-report.json \
  --publication-packet .apw/release-dry-run/data-YYYY.MM.DD/publication-packet.json \
  --release-id data-YYYY.MM.DD \
  --source-commit "<40-char-source-commit>"
```

For a publish packet, add `--require-publish-packet`. The verifier is local and
read-only: it checks schemas, dry-run checks, artifact SHA-256/byte counts,
manifest/checksum consistency, packet linkage, reviewed event IDs, signing tag,
and source commit. It does not create tags, upload releases, call provider
sources, or verify external GitHub/PyPI/attestation state over the network.

The GitHub data-release workflow runs daily and on manual dispatch. Scheduled
runs are dry-run evidence only: they do not tag, upload a release, update source
state, or process provider page content. The job keeps `contents: read`, uses
OIDC only for artifact attestation, and serializes runs with workflow
concurrency so a slow dry run does not overlap the next one.

The dry run does not publish a tag, upload a release, or require a release
token. A public data tag still requires maintainer review, green GitHub CI,
CodeQL workflow completion, a matching GitHub code-scanning analysis for the
release commit, `uv lock --check`, Dependency Review, branch protection,
OpenSSF Scorecard, repository security settings, artifact checksum review,
attestation verification, release manager approval, and a signed tag plan.
Release automation stays dry-run only until the [release gates](release-gates.md),
[repository settings](repository-settings.md),
[release automation readiness](release-automation-readiness.md), and
[guarded data publisher](data-publisher.md) controls are recorded.

Dependency Review is currently a manual gate with explicit `base_ref` and
`head_ref` inputs. If GitHub dependency graph or Dependency Review support is
unavailable, the release is blocked until maintainers enable support and record
the concrete resolution.

## Evidence Packets

- [2026-06-01 `data-2026.06.01` dry run](release-evidence/2026-06-01-data-2026.06.01-dry-run.md):
  first successful manual workflow dry run on public `main`, with 15 passing
  report checks and release-shaped artifact checksums. No tag was created.
- [2026-06-10 `v0.1.8` Python package](release-evidence/2026-06-10-v0.1.8-python-package.md):
  successful PyPI Trusted Publishing run, matching GitHub release assets,
  artifact hashes, and fresh-install smoke coverage.
- [2026-06-10 `v0.1.9` Python package](release-evidence/2026-06-10-v0.1.9-python-package.md):
  successful PyPI Trusted Publishing run for stable remote-feed helpers,
  matching GitHub release assets, artifact hashes, and fresh-install smoke
  coverage.
- [2026-06-10 `v0.1.10` Python package](release-evidence/2026-06-10-v0.1.10-python-package.md):
  successful PyPI Trusted Publishing run for the high-signal Anthropic
  release-note event snapshot, matching GitHub release assets, artifact hashes,
  and fresh-install smoke coverage.
- [2026-06-11 `v0.1.11` Python package](release-evidence/2026-06-11-v0.1.11-python-package.md):
  successful PyPI Trusted Publishing run for selector-aware candidate
  split/dedupe packet ergonomics, matching GitHub release assets, artifact
  hashes, PyPI provenance, and fresh-install smoke coverage.
- [2026-06-11 `data-2026.06.11` data release](release-evidence/2026-06-11-data-2026.06.11.md):
  Ron-signed data tag and GitHub release for the June 11 AWS Bedrock OpenAI GPT
  availability event, with CI, CodeQL, Dependency Review, Scorecard, protected
  dry-run attestation, packet evidence, and pinned remote-feed smoke.
- [2026-06-11 `v0.1.12` Python package](release-evidence/2026-06-11-v0.1.12-python-package.md):
  successful PyPI Trusted Publishing run for the `data-2026.06.11` bundled
  package snapshot, matching GitHub release assets, artifact hashes, PyPI
  provenance, and fresh-install smoke coverage.
- [2026-06-11 `v0.1.13` Python package](release-evidence/2026-06-11-v0.1.13-python-package.md):
  successful PyPI Trusted Publishing run for issue-triage and source-refresh
  review-gate CLI surfaces, matching GitHub release assets, artifact hashes,
  PyPI provenance, and fresh-install smoke coverage.
