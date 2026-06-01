# Roadmap

AI Provider Watch is pre-release. The roadmap is ordered by public safety and
reuse value rather than by private Ottto product needs.

## v0.1 Release Readiness

Goal: publish a trusted reviewed feed, CLI, read-only MCP surface, GitHub
Action, notification payloads, ecosystem mapping payloads, and installable Codex
plugin with no private Ottto dependency.

Required before the first public data tag:

- branch protection or repository ruleset on `main`;
- required status checks for CI and CodeQL;
- Dependency Review support through GitHub dependency graph;
- source owner and release manager roles configured;
- signed `data-YYYY.MM.DD` tag or protected publisher path;
- attested release evidence bundle verified with `gh attestation verify`;
- maintainer release approval recorded with checksum review;
- release-token separation from source refresh and candidate workflows.

The daily CalVer data release cadence remains dry-run only until these release
gates pass.

These release gates are the v0.1 quality bar, not optional follow-up work.

## v0.2 Source Depth

Goal: broaden deterministic official-source coverage without publishing raw
provider text.

Planned work:

- graduate blocked lifecycle sources only after live heading scopes and parser
  fixtures are stable;
- add richer bounded pricing, quota, model lifecycle, and incident candidates;
- add recall windows for source changes that should create review candidates;
- keep community and social sources review-only.

## v0.3 Downstream Operations

Goal: make APW easy for external maintainers and downstream projects to consume.

Planned work:

- publish package artifacts after v0.1 schema/feed compatibility is stable;
- harden downstream GitHub Action examples across common repo layouts;
- add webhook receiver examples without making APW own delivery retries;
- keep MCP read-only until publication gates and source mutation tests are
  stronger.

## v1.0 Stability

Goal: make the schema/feed contract dependable for production consumers.

Planned work:

- versioned schema compatibility policy;
- migration notes for breaking feed or CLI changes;
- release cadence backed by passing branch rules, attestations, and dependency
  checks;
- documented maintainer rotation for source owners and release managers.

## Non-Goals

- No Ottto account requirement.
- No private Ottto UI, Advisor, telemetry, SQLAlchemy, Alembic, AWS infra, Slack,
  or credential-loading code.
- No unattended publication from community, social, issue, PR, or MCP text.
