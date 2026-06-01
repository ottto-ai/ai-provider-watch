# Maintainers

Initial maintainer:

- Ron Shub / Ottto

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

Until those teams exist, `@RonShub` is the release manager, source owner,
schema maintainer, and security contact for public repository operations.
