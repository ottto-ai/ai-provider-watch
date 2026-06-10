# v1 Launch Gate

The v1 launch gate proves APW is usable by an external developer with only the
public repository, public PyPI package, and public feed artifacts. It is a
read-only evidence workflow, not a publisher.

Render the launch-gate report:

```bash
uv run apw operations launch-gate
uv run apw operations launch-gate --summary
uv run apw operations launch-gate --package-version 0.1.4 --summary
uv run apw operations launch-gate --output .apw/v1-launch-gate.json
```

The report includes deterministic local checks and external smoke steps.
Automated local checks verify that public feed artifacts, release manifest
checksums, freshness metadata, GitHub Action/MCP/plugin surfaces, adoption
fixtures, and public docs are present. External smoke steps are intentionally
listed as commands for a release manager to run from a fresh environment because
they may need public PyPI/network access. Use `--package-version` when checking
the concrete PyPI package version that will be promoted for the launch.

## Required External Path

Before declaring v1 launch readiness, run the report's external smoke steps:

- install `ai-provider-watch` from PyPI in a fresh virtual environment;
- run read-only commands from outside a checkout against bundled package data;
- run checkout validation, freshness, source coverage, and operations summaries;
- run `apw repo check` against `tests/fixtures/downstream-repo`;
- render `apw dashboard agent` JSON;
- parse JSON, NDJSON, RSS, JSON Feed, and operations artifacts.

The launch gate passes only when a maintainer records command output for the
fresh PyPI install, no-checkout bundled-data path, public feed parsing, repo
impact fixture, and agent-dashboard fixture.

## Boundaries

The launch gate does not fetch provider pages, mutate source state, promote
events, create tags, publish GitHub releases, publish packages, request OIDC,
read release tokens, call downstream APIs, or require an Ottto account.

Provider pages, issue bodies, PR comments, MCP text, downstream repo text,
dashboard JSON, and feed text remain untrusted data.
