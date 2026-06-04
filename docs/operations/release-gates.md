# Release Gates

APW data-release automation stays dry-run only until maintainers record every
gate in this runbook. The release dry-run report is necessary evidence, not a
publishing approval.

The scheduled data-release workflow is also dry-run only. It creates attested
release-shaped evidence for the current `main` commit, but it must not create
tags, GitHub releases, or canonical provider events.

## Deterministic Local Gates

Run from a clean checkout of the intended release commit:

```bash
uv lock --check
uv run ruff check .
uv run pytest
uv run apw source test
uv run apw validate
uv run apw index --check
actionlint .github/workflows/*.yml
uv run apw release dry-run --output .apw/release-dry-run --require-clean
```

The dry-run report checks schema validation, source fixtures, generated feed
freshness, CalVer manifest schema, checksums, license layout, dependency lock
presence, CodeQL workflow posture, Dependency Review posture, release workflow
attestation guardrails, the source-refresh token boundary, source ownership,
and maintainer release docs.

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

gh attestation verify .apw/apw-release-dry-run.tgz --repo "$REPO"
```

Release is blocked if branch protection is absent, CI is not green, CodeQL
workflow or code-scanning analysis is missing for the release commit, Dependency
Review fails or cannot run because dependency graph support is not enabled, or
the dry-run manifest/checksums do not match the downloaded artifact. The release
manager must also verify the dry-run evidence bundle attestation, repository
security settings, and signed tag plan.

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

## Maintainer Release Approval

A release manager listed in [MAINTAINERS.md](../../MAINTAINERS.md) must approve:

- the source commit;
- passing local and GitHub checks;
- branch protection or ruleset state;
- Dependency Review result;
- artifact checksums and manifest contents;
- `gh attestation verify` output for the dry-run bundle;
- release notes and signed `data-YYYY.MM.DD` tag plan.

Source owner approval is required when the release includes new source
descriptors, source graduation, parser changes, reviewed events, or generated
feed changes.

For the v0.1 launch window, `@RonShub` is the sole release manager, source
owner, schema maintainer, and security contact. The first public data tag may be
approved by `@RonShub` after the release evidence packet records the checks
above. This single-maintainer posture must be revisited before v1.0 or before
granting non-Ron publishing authority.
