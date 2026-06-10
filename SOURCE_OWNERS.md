# Source Owners

Source owners keep provider source packages factual, bounded, and safe for
deterministic automation. A source owner is responsible for descriptor quality,
fixture coverage, parser drift, and review notes for promoted events. Source
owners do not gain publishing authority by being listed here; event publication
still requires a maintainer-reviewed PR and release gates.

Public contributor flow is documented in
[docs/contributors/review-workflow.md](docs/contributors/review-workflow.md).
Source tiers and the source-owner onboarding checklist are documented in
[docs/operations/v1-governance.md](docs/operations/v1-governance.md).

For v0.1, `@RonShub` is the sole source owner for every source key listed below.
The role keys remain stable so future teams can take over without changing
source descriptors or event metadata.

## Role Keys

| Role key | GitHub team to configure | Scope |
| --- | --- | --- |
| `apw-data-maintainers` | `ai-provider-watch-data-maintainers` | Provider source descriptors, parser fixtures, reviewed data events, generated feeds. |
| `apw-schema-maintainers` | `ai-provider-watch-schema` | JSON Schemas, event model compatibility, feed contracts. |
| `apw-release-managers` | `ai-provider-watch-maintainers` | Data release approval, artifact checksum review, signed tags, attestation verification. |
| `apw-security` | `ai-provider-watch-security` | Security reports, token-boundary review, workflow hardening. |

## Source Registry Map

Every source key in `sources/registry.json` must appear in this table.

| Source key | Provider | Owner role | Automation posture |
| --- | --- | --- | --- |
| `openai.pricing` | OpenAI | `apw-data-maintainers` | `enabled_deterministic` |
| `openai.status` | OpenAI | `apw-data-maintainers` | `enabled_deterministic` |
| `openai.deprecations` | OpenAI | `apw-data-maintainers` | `enabled_deterministic` |
| `openai.news` | OpenAI | `apw-data-maintainers` | `enabled_deterministic` |
| `openai.codex_docs` | OpenAI | `apw-data-maintainers` | `manual_review_only` |
| `anthropic.pricing` | Anthropic | `apw-data-maintainers` | `enabled_deterministic` |
| `anthropic.status` | Anthropic | `apw-data-maintainers` | `enabled_deterministic` |
| `anthropic.news` | Anthropic | `apw-data-maintainers` | `enabled_deterministic` |
| `anthropic.release_notes` | Anthropic | `apw-data-maintainers` | `manual_review_only` |
| `google.vertex_pricing` | Google Gemini / Vertex AI | `apw-data-maintainers` | `enabled_deterministic` |
| `google.ai_docs` | Google Gemini / Vertex AI | `apw-data-maintainers` | `enabled_deterministic` |
| `google.gemini_changelog` | Google Gemini / Vertex AI | `apw-data-maintainers` | `enabled_deterministic` |
| `google.vertex_model_versions` | Google Gemini / Vertex AI | `apw-data-maintainers` | `enabled_deterministic` |
| `aws_bedrock.pricing` | AWS Bedrock | `apw-data-maintainers` | `enabled_deterministic` |
| `aws_bedrock.docs` | AWS Bedrock | `apw-data-maintainers` | `enabled_deterministic` |
| `aws_bedrock.whats_new` | AWS Bedrock | `apw-data-maintainers` | `enabled_deterministic` |
| `azure_openai.pricing` | Azure OpenAI | `apw-data-maintainers` | `enabled_deterministic` |
| `azure_openai.docs` | Azure OpenAI | `apw-data-maintainers` | `enabled_deterministic` |
| `azure_openai.whats_new` | Azure OpenAI | `apw-data-maintainers` | `enabled_deterministic` |
| `azure_openai.legacy_models` | Azure OpenAI | `apw-data-maintainers` | `enabled_deterministic` |

## Owner Duties

- Keep allowed domains, authority, cadence, snapshot policy, and graduation
  blockers current.
- Add or update synthetic fixtures before broadening parser output.
- Keep provider page text, issue bodies, PR comments, social posts, and MCP
  resource text as untrusted data.
- Promote candidates to `data/events/` only through reviewed PRs with official
  evidence URLs and regenerated feeds.
- Escalate schema, workflow, release, or token-boundary changes to the matching
  maintainer role.
