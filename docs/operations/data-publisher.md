# Guarded Data Publisher

The guarded data publisher is a protected-environment workflow for future
`data-YYYY.MM.DD` publication. It is intentionally no-op only in v0.1: it runs
release gates from a trusted `main` commit and records that no data tag or
GitHub data release was created.

## Threat Model

Source refresh, candidate generation, LLM review, issue bodies, PR comments,
MCP text, and provider pages are untrusted input lanes. Those lanes must never
receive release secrets, OIDC publishing authority, tag creation authority, or
GitHub release upload authority.

The publisher is separate from those lanes. It can only be started manually from
`main`, requires the protected `data-release` environment, and currently keeps
`contents: read` with no secrets and no OIDC token. The no-op workflow is a
staging contract for the eventual publisher, not publication approval.

## Protected Environment

Create a GitHub environment named `data-release` before using the workflow as a
release gate:

1. Require reviewer approval from `@RonShub` during the v0.1 single-maintainer
   period.
2. Do not add environment secrets while the workflow is no-op only.
3. Keep the workflow restricted to `main`.
4. Record the workflow run URL, source commit, release date, and dry-run report
   in release evidence.

If the environment cannot require the release manager review, the publisher is
not a release gate and real publication remains manual.

## No-Op Mode

Run the no-op publisher only after CI, CodeQL, generated feeds, source fixtures,
and the scheduled data-release dry run are green:

```bash
gh workflow run data-publisher.yml \
  --repo ottto-ai/ai-provider-watch \
  --ref main \
  -f release_date="$(date -u +%F)" \
  -f publish_mode=no-op
```

The workflow checks:

- source ref is `refs/heads/main`;
- `publish_mode` is exactly `no-op`;
- `uv lock --check`;
- `uv run ruff check .`;
- `uv run pytest`;
- `uv run apw source test`;
- `uv run apw validate`;
- `uv run apw index --check`;
- `uv run apw release dry-run --require-clean`.

It does not create tags, upload releases, read secrets, request OIDC, or process
provider/source/candidate text beyond the reviewed repository checkout.

## Real Publishing Gate

Do not add real `data-YYYY.MM.DD` publishing until a release manager approves a
signed-tag mechanism and a follow-up PR changes this workflow deliberately.

Before enabling real publication, the follow-up PR must add tests proving:

- the publisher runs only from trusted `main` commits;
- the `data-release` environment requires release-manager review;
- source-refresh, candidate, LLM review, issue, PR-comment, and MCP lanes still
  have no release authority;
- release dry-run artifact checksums match the downloaded artifact;
- `gh attestation verify` succeeds for the dry-run evidence bundle;
- Dependency Review, CI, CodeQL workflow, and code-scanning analysis are green
  for the release commit;
- the selected tag mechanism signs or otherwise provides the approved signature
  posture.

Until those tests and the signed-tag decision land, public data publication
stays manual and release-manager approved.
