# Release Gates

APW data-release automation stays dry-run only until maintainers deliberately
approve and test a real publisher. The release dry-run report is necessary
evidence, not a publishing approval.

The scheduled data-release workflow is also dry-run only. It creates attested
release-shaped evidence for the current `main` commit, but it must not create
tags, GitHub releases, or canonical provider events. The separate data publisher
workflow is protected and no-op only in v0.1.

## v0.1 Signed Tag Policy

The approved v0.1 publishing mechanism is manual release-manager publication
with Ron-signed Git tags:

```bash
git tag -s data-YYYY.MM.DD
git tag -v data-YYYY.MM.DD
git push origin data-YYYY.MM.DD
```

GitHub artifact attestations are provenance evidence for release dry-run
artifacts. They do not replace the release manager's signed Git tag. Do not
store signing keys in GitHub Actions, repository secrets, environment secrets,
or jobs that process provider/source/candidate text.

Future daily tag automation requires a separate PR with explicit release-manager
approval, tests for the chosen signature posture, and evidence that source
refresh, candidate generation, LLM review, issue, PR-comment, social, and MCP
lanes still have no release authority.

## Deterministic Local Gates

Run from a clean checkout of the intended release commit:

```bash
uv lock --check
uv run ruff check .
uv run pytest
uv run apw source test
uv run apw source coverage --summary
uv run apw operations report --summary
uv run apw validate
uv run apw index --check
uv run apw freshness --summary
actionlint .github/workflows/*.yml
uv run apw release evidence-index --release-id data-YYYY.MM.DD --source-commit "$(git rev-parse HEAD)" --output .apw/release-dry-run/data-YYYY.MM.DD/evidence-index.json
uv run apw release dry-run --output .apw/release-dry-run --require-clean
uv run apw release packet --dry-run-report .apw/release-dry-run/data-YYYY.MM.DD/dry-run-report.json ...
uv run apw release verify --dry-run-report .apw/release-dry-run/data-YYYY.MM.DD/dry-run-report.json --publication-packet .apw/release-dry-run/data-YYYY.MM.DD/publication-packet.json --release-id data-YYYY.MM.DD --source-commit "$(git rev-parse HEAD)"
```

The dry-run report checks schema validation, source fixtures, source coverage,
the operations report, generated feed freshness, CalVer manifest schema,
checksums, license layout, dependency lock presence, CodeQL workflow posture,
Dependency Review posture, release workflow attestation guardrails, the
source-refresh token boundary, OpenSSF Scorecard workflow posture, source
ownership, and maintainer release docs.

`apw release evidence-index` renders the same release-evidence contract that is
packaged at `data/releases/<release-id>/evidence-index.json`. It is the
machine-readable map for downstream users and agents: release artifacts, local
commands, external GitHub/PyPI/attestation gates, workflow authority, token
boundaries, and raw-provider-content policy.

`apw release verify` rechecks the dry-run report, local release artifacts,
manifest/checksum integrity, optional publication packet linkage, reviewed event
IDs, signing tag, release ID, and source commit before a release manager signs.
It is local and read-only; external GitHub, PyPI, and attestation verification
commands remain separate required gates.

## Required External Gates

Use these checks before creating any `data-YYYY.MM.DD` tag:

```bash
export REPO=ottto-ai/ai-provider-watch
export SHA="$(git rev-parse HEAD)"

gh api "repos/$REPO/branches/main/protection" \
  --jq '{required_status_checks, required_pull_request_reviews, enforce_admins}'

gh run list --repo "$REPO" --branch main --commit "$SHA" \
  --workflow CI --json status,conclusion,url,headSha

gh run list --repo "$REPO" --branch main --commit "$SHA" \
  --workflow CodeQL --json status,conclusion,url,headSha

gh api "repos/$REPO/code-scanning/analyses?ref=refs/heads/main&per_page=20" \
  --jq '.[] | select(.commit_sha == env.SHA) | {id, commit_sha, created_at, category}'

gh workflow run dependency-review.yml --repo "$REPO" --ref main \
  -f base_ref="<previous-release-tag-or-sha>" \
  -f head_ref="$SHA"

gh run list --repo "$REPO" --workflow "Dependency Review" \
  --json status,conclusion,url,headSha

gh run list --repo "$REPO" --workflow Scorecard --branch main \
  --json status,conclusion,url,headSha

gh attestation verify .apw/apw-release-dry-run.tgz --repo "$REPO"

uv run apw release packet \
  --dry-run-report .apw/release-dry-run/data-YYYY.MM.DD/dry-run-report.json \
  --reviewed-event "<event-id>" \
  --release-manager @RonShub \
  --source-owner @RonShub \
  --source-owner-approval-ref "<approval-url>" \
  --release-manager-approval-ref "<approval-url>" \
  --branch-protection-ref "<branch-protection-ref>" \
  --ci-ref "<ci-run-url>" \
  --codeql-workflow-ref "<codeql-run-url>" \
  --code-scanning-ref "<analysis-ref>" \
  --dependency-review-ref "<dependency-review-run-url>" \
  --scorecard-ref "<scorecard-run-url>" \
  --attestation-ref "<attestation-verify-ref>" \
  --checksum-review-ref "<checksum-review-ref>"
```

Release is blocked if branch protection is absent, CI is not green, CodeQL
workflow or code-scanning analysis is missing for the release commit, Dependency
Review fails or cannot run because dependency graph support is not enabled,
OpenSSF Scorecard has not completed for the release commit, or the dry-run
manifest/checksums do not match the downloaded artifact. The release manager
must also verify the dry-run evidence bundle attestation, PyPI Trusted
Publishing posture, repository security settings, and signed tag plan.

The Dependency Review path is manual until repository dependency graph support
is enabled and maintainers decide to make it a required PR check. It uses the
official action's `base-ref` and `head-ref` inputs for non-pull-request events;
see
<https://github.com/actions/dependency-review-action>.

## Token Boundary

No release token may be present in jobs that fetch provider pages, parse
observations, generate candidates, read contributed files, or process PR
comments. Source refresh may write a branch and open a draft review PR with the
default `GITHUB_TOKEN`; it must not tag, publish releases, request OIDC, or read
repository secrets.

The release dry-run workflow has `contents: read`, `id-token: write`, and
`attestations: write` so it can attest `.apw/apw-release-dry-run.tgz`. It
performs no tag or release operation and uploads only ignored dry-run artifacts.
A future real publisher must be a separate protected-environment job that
consumes reviewed artifacts from a trusted release commit.

The current publisher contract lives in
[data-publisher.md](data-publisher.md). It requires the `data-release`
environment and `main`, runs release dry-run checks, can upload a
`publication-packet.json` evidence artifact in packet mode, and does not
request write, secret, OIDC, tag, or release-upload authority.

Use [v0.2-release-checklist.md](v0.2-release-checklist.md) as the consolidated
release-manager closeout packet before declaring v0.2 operations ready or
cutting a v0.2 package/data release.

## Maintainer Release Approval

A release manager listed in [MAINTAINERS.md](../../MAINTAINERS.md) must approve:

- the source commit;
- passing local and GitHub checks;
- branch protection or ruleset state;
- Dependency Review result;
- OpenSSF Scorecard run URL;
- artifact checksums and manifest contents;
- packaged `data/releases/<release-id>/evidence-index.json`;
- `apw freshness --summary` output for feed/package/source-state provenance;
- `apw source coverage --summary` output for enabled source-state coverage,
  blocked parser sources, and review backlog;
- `apw operations report --summary` output for operating SLOs, source-state
  freshness, contributor intake, correction policy, and release-train posture;
- `gh attestation verify` output for the dry-run bundle;
- `apw release packet` output for reviewed event IDs or explicit skip reason;
- release notes and manual Ron-signed `data-YYYY.MM.DD` tag plan.
- protected `data-release` environment approval for any publisher run.

Source owner approval is required when the release includes new source
descriptors, source graduation, parser changes, reviewed events, or generated
feed changes.

For the v0.1 launch window, `@RonShub` is the sole release manager, source
owner, schema maintainer, and security contact. The first public data tag may be
approved by `@RonShub` after the release evidence packet records the checks
above. This single-maintainer posture must be revisited before v1.0 or before
granting non-Ron publishing authority.
