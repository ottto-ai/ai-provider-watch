# Maintainers

Initial maintainer:

- Ron Shub / Ottto

## v0.1 Single-Maintainer Authority

For the v0.1 launch window, `@RonShub` is the sole release manager, source
owner, schema maintainer, and security contact for public APW repository
operations. This is an explicit single-maintainer launch posture, not a missing
team configuration.

`@RonShub` may approve the first public `data-YYYY.MM.DD` tag after the release
evidence packet records the required checks, checksums, attestation verification,
token-boundary review, and signed-tag plan.

This single-maintainer posture must be revisited before v1.0, before granting
non-Ron publishing authority, or before enabling team-only CODEOWNERS gates that
could lock out the current maintainer.

The source-owner onboarding checklist and neutrality checkpoints are documented
in [docs/operations/v1-governance.md](docs/operations/v1-governance.md).

## Role Keys

APW uses stable role keys in source descriptors and docs. GitHub teams will be
mapped to these roles after repository access groups are configured.

| Role key | Planned GitHub team | Responsibility |
| --- | --- | --- |
| `apw-release-managers` | `ai-provider-watch-maintainers` | Release manager approval, signed data tags, artifact attestation verification, final release evidence. |
| `apw-data-maintainers` | `ai-provider-watch-data-maintainers` | Source owner review, reviewed event promotion, feed regeneration. |
| `apw-schema-maintainers` | `ai-provider-watch-schema` | Schema compatibility, migration notes, versioning policy. |
| `apw-security` | `ai-provider-watch-security` | Security response, token-boundary review, workflow hardening. |

## Planned Teams

- `ai-provider-watch-maintainers`
- `ai-provider-watch-schema`
- `ai-provider-watch-data-maintainers`
- `ai-provider-watch-security`

Until those teams exist, `@RonShub` remains the release manager, source owner,
schema maintainer, and security contact for public repository operations.
