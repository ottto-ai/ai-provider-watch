# Python Package Release

APW publishes the `ai-provider-watch` Python package with PyPI Trusted
Publishing. The package exposes the `apw` CLI.

## v0.1 Authority

For the v0.1 launch window, `@RonShub` is the sole package release manager and
PyPI source owner. Revisit this before v1.0 or before adding another PyPI
publisher.

## First Non-Alpha Target

The first non-alpha Python package target is `v0.1.0`. It should be a stable
consumer release of the existing alpha surfaces, not a promise that APW has
reached a `1.0` API contract.

`v0.1.0` is blocked until maintainers record all of these:

- install smoke from PyPI in a fresh environment;
- CLI smoke against checkout data;
- CLI smoke against installed package data without `--root`;
- schema/feed compatibility statement for downstream users;
- package rollback/yank policy;
- GitHub release asset policy.

## Compatibility Promise

For `0.1.x` package releases, APW maintainers should preserve these contracts:

- package name: `ai-provider-watch`;
- CLI command: `apw`;
- core read commands: `validate`, `index --check`, `freshness`,
  `source coverage`, `latest`, `diff`, `explain`;
- event schema version: `apw.provider_event.v0`;
- feed artifact names: `data/feeds/events.json`,
  `data/feeds/events.ndjson`, `data/feeds/coverage.json`,
  `data/feeds/feed.json`, `data/feeds/freshness.json`,
  `data/feeds/latest.json`, and `data/feeds/rss.xml`;
- source/candidate workflows stay review-only and do not publish events without
  maintainer review;
- MCP stays read-only by default.

Pre-1.0 caveats:

- new event kinds, detail fields, impact fields, source descriptors, and
  registry refs may be added in `0.1.x`;
- candidate, observation, LLM-review, MCP, and plugin contracts may still
  evolve before `1.0`;
- event data may grow, be superseded, or be retracted when provider evidence
  changes;
- a breaking CLI/schema/feed change requires a new minor line such as `0.2.0`
  unless it fixes a security issue or invalid published data.

## Bundled Data Snapshot Policy

GitHub CalVer data releases, such as `data-2026.06.08`, are the canonical
immutable feed snapshots. PyPI package releases are installable CLI snapshots
that bundle reviewed public data for no-checkout and offline use.

Do not publish a Python package for every daily data tag. Publish a `0.1.x`
patch package when one of these is true:

- bundled data freshness materially improves install-only users;
- README examples or docs depend on the newer bundled event IDs;
- package, CLI, MCP, schema, or bundled-data loading behavior changed;
- the previous package contains invalid public data or a packaging bug.

If reviewed events land after a same-day data tag has already been signed, do
not move or recreate that data tag. Ship the next immutable data release under
the next approved data-release identity, and publish a package patch only when
the bundled-data snapshot itself is worth updating.

Decision for `0.1.1`: publish the package patch. PR #89 promoted the June 8
official-source review window into sixteen additional reviewed ProviderEvents
and raised the bundled feed from twelve to twenty-eight events. Install-only
users of `0.1.0` otherwise miss the higher-value AWS Bedrock, Google Gemini API,
and Azure OpenAI changes until they fetch repository data directly.

Decision for `0.1.10`: publish the package patch and do not recreate the
already-signed `data-2026.06.10` tag. PR #124 promoted four high-signal
Anthropic release-note ProviderEvents after the same-day data tag already
existed. A package snapshot keeps install-only users current without weakening
the one-tag-per-release-identity policy; the next immutable data release should
use the next approved `data-YYYY.MM.DD` identity.

Decision for `0.1.11`: publish the package patch and do not create a data tag.
PR #130 changed CLI/package behavior by making candidate split/dedupe packet
ergonomics selector-aware for Anthropic multi-entry official sources. Reviewed
event data did not change, so the existing signed `data-2026.06.10` identity
remains the latest immutable data release.

Decision for `0.1.12`: publish the package patch after the signed
`data-2026.06.11` release. PR #134 promoted a high-signal official AWS Bedrock
ProviderEvent for OpenAI GPT-5.4 and GPT-5.5 availability in US East
(N. Virginia), raising the reviewed feed to forty events. A package snapshot
keeps install-only users aligned with the latest immutable data release without
requiring a checkout or live remote read.

Decision for `0.1.13`: publish the package patch and do not create a new data
tag. PR #137 added `apw event issue-triage` for safe missing-event issue triage,
and this release adds `apw source review-needed` so source-refresh automation
opens candidate-review PRs only for changed source fingerprints or review
candidates. Reviewed event data did not change, so the signed
`data-2026.06.11` identity remains the immutable feed snapshot.

## Trusted Publisher Configuration

Configure PyPI with a pending Trusted Publisher before the first package upload.
No PyPI API token is needed.

| Field | Value |
| --- | --- |
| PyPI project | `ai-provider-watch` |
| GitHub owner | `ottto-ai` |
| GitHub repository | `ai-provider-watch` |
| Workflow filename | `publish-python.yml` |
| Environment | `pypi` |

The GitHub repository must also have an environment named `pypi`. Keep it
protected by a required reviewer during v0.1, with `@RonShub` as the reviewer.
Do not add PyPI credentials, API tokens, or repository secrets for package
publishing.

Official setup references:

- <https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/>
- <https://docs.pypi.org/trusted-publishers/using-a-publisher/>
- <https://docs.pypi.org/attestations/producing-attestations/>
- <https://docs.github.com/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-pypi>

## Workflow Security

`.github/workflows/publish-python.yml` separates build and publish authority:

- `build` runs tests, validation, source fixtures, generated-index checks, and
  package build without `id-token: write`;
- `publish` runs only for refs matching `refs/tags/v*`;
- `publish` uses the protected `pypi` environment;
- only `publish` receives `id-token: write`;
- no workflow runs on `pull_request_target`;
- no release or PyPI token is available to source-refresh, candidate-review,
  LLM-review, or PR-comment workflows.

## First Alpha Publish Checklist

1. Verify the package name still returns 404 from
   `https://pypi.org/pypi/ai-provider-watch/json`.
2. Confirm the PyPI pending publisher fields match this document exactly.
3. Confirm GitHub environment `pypi` requires `@RonShub` review.
4. Land the release commit through PR.
5. Create and push a signed package tag such as `v0.1.0a0`.
6. Approve the `pypi` environment deployment.
7. Verify the PyPI project page and file attestations.
8. Run an install smoke in a fresh environment:

```bash
python -m venv /tmp/apw-pypi-smoke
. /tmp/apw-pypi-smoke/bin/activate
python -m pip install --upgrade pip
python -m pip install ai-provider-watch==0.1.0a0
apw --root /path/to/ai-provider-watch validate
```

Keep package release evidence with the tag, workflow run, PyPI file hashes, and
install-smoke output.

## Non-Alpha Release Checklist

Run this checklist before `v0.1.0` or any later non-alpha package release.

1. Land the release commit through PR with green CI, CodeQL, dependency lock,
   schema validation, source fixtures, generated-index checks, and release docs.
2. Confirm the compatibility promise above still matches the code and CLI.
3. Confirm the `pypi` environment still requires `@RonShub` review during v0.1.
4. Build and publish only through PyPI Trusted Publishing; do not add PyPI API
   tokens or release secrets.
5. Create and push a signed package tag such as `v0.1.0`.
6. Approve the protected `pypi` environment deployment.
7. Verify PyPI project metadata, file hashes, and attestations.
8. Attach the exact wheel and sdist artifacts to the matching GitHub release.
   Do not rebuild artifacts for GitHub; checksums must match PyPI.
9. Run the install and CLI smokes below.
10. Record release evidence with tag, workflow run, PyPI hashes, GitHub release
    asset hashes, smoke output, known caveats, and rollback/yank decision.

## Non-Alpha Smoke Commands

Use a fresh environment and an explicit version under test:

```bash
export APW_VERSION=0.1.0
export APW_CHECKOUT=/path/to/ai-provider-watch

python -m venv /tmp/apw-pypi-smoke
. /tmp/apw-pypi-smoke/bin/activate
python -m pip install --upgrade pip
python -m pip install "ai-provider-watch==$APW_VERSION"
python -m pip show ai-provider-watch
apw --root "$APW_CHECKOUT" validate
apw --root "$APW_CHECKOUT" index --check
apw --root "$APW_CHECKOUT" freshness --summary
apw --root "$APW_CHECKOUT" source coverage --summary
apw --root "$APW_CHECKOUT" operations report --summary
apw --root "$APW_CHECKOUT" operations launch-gate --summary
apw --root "$APW_CHECKOUT" latest --limit 3
apw --root "$APW_CHECKOUT" diff --since 30d
apw --root "$APW_CHECKOUT" explain 2026-06-01-google-vertex-gemini-2-0-flash-retirement
```

Installed package data must also be tested before `v0.1.0`. Run these commands
from a directory that is not inside an APW checkout:

```bash
mkdir -p /tmp/apw-installed-data-smoke
cd /tmp/apw-installed-data-smoke
apw validate
apw index --check
apw freshness --summary
apw source coverage --summary
apw operations report --summary
apw operations launch-gate --summary
apw latest --limit 3
apw diff --since 30d
apw explain 2026-06-01-google-vertex-gemini-2-0-flash-retirement
```

These read commands use bundled package data. Source refresh, candidate
generation, event promotion, index writes, and release dry runs still require an
explicit checkout root because they mutate repository-shaped files or require
Git state.

## Rollback And Yank Policy

PyPI files and Git tags are immutable for practical release purposes. Never
delete and recreate a version or tag.

Prefer a patch release when a published package has ordinary bugs. Yank a PyPI
release only when one of these is true:

- the package cannot install or the CLI cannot start on supported Python
  versions;
- the package contains private data, credentials, raw provider page bodies, or
  other content that should not be distributed;
- the package points users at materially wrong data and a patch release cannot
  mitigate the harm quickly enough;
- the package or workflow has a security issue that makes continued installation
  unsafe.

When yanking:

1. keep the GitHub release visible and add a clear yanked notice;
2. set the PyPI yanked reason with the affected version and replacement version
   when known;
3. open a public issue with impact, mitigation, and next release target;
4. publish a fixed patch as soon as practical;
5. record the incident in release evidence.
