# Governance

AI Provider Watch is founded by Ottto and maintained as a public, vendor-neutral
open-source project.

Routine fixes can merge after maintainer review and passing checks. Schema,
release, workflow, and source-authority changes require explicit maintainer
approval.

APW may credit Ottto as founder and sponsor, but provider events, schemas, and
feeds should remain factual and reusable without an Ottto account.

## Review Authority

The source owner and release manager roles are documented in
[SOURCE_OWNERS.md](SOURCE_OWNERS.md) and [MAINTAINERS.md](MAINTAINERS.md).

For the v0.1 launch window, `@RonShub` is the sole release manager, source
owner, schema maintainer, and security contact. This allows the first public data
release to ship without creating team gates that can lock out a one-maintainer
repository. The repository must revisit this posture before v1.0 or before
granting non-Ron publishing authority.

- Source owner review is required for new source descriptors, parser fixtures,
  source graduation, and candidate-to-event promotion.
- Schema maintainer review is required for JSON Schema, event detail union,
  impact assessment, feed compatibility, and migration policy changes.
- Security maintainer review is required for workflow permissions, token
  boundaries, MCP capabilities, prompt-injection guardrails, and release
  credential handling.
- A release manager must approve any public `data-YYYY.MM.DD` tag after
  required status checks, branch protection or ruleset verification, checksum review,
  attestation verification, and release-token separation are recorded.

## Release Policy

Public data releases use CalVer tags and remain dry-run only until the
[release gates](docs/operations/release-gates.md) and
[repository settings](docs/operations/repository-settings.md) pass. No workflow
that fetches provider pages, parses observations, generates candidates, reads PR
comments, or processes other untrusted source content may receive release-token
authority.
