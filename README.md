# AI Provider Watch

AI Provider Watch is an open, factual provider-change event feed for AI platform
teams, coding-agent maintainers, and FinOps dashboards.

It tracks provider changes that can affect developer cost, quotas, token
accounting, model availability, default models, deprecations, incidents, API
contracts, and migration risk. The project is founded by Ottto, but the feed,
schemas, CLI, and docs are usable without an Ottto account.

## What This Is

- A reviewed machine-readable event feed, not a static model catalog.
- A CLI and Python package for validating, indexing, diffing, and explaining
  provider-change events.
- A source registry for official provider docs, status pages, pricing pages,
  blogs, and repositories.
- Agent-readable contracts for Codex, Claude Code, MCP clients, GitHub Actions,
  and downstream repo impact checks.

## What This Is Not

- Not an Ottto customer telemetry product.
- Not a scraper of authenticated provider consoles or billing dashboards.
- Not legal, purchasing, tax, or migration advice.
- Not a replacement for LiteLLM, models.dev, Langfuse, Helicone, or OpenLIT.

## Current Status

This repository is in pre-release foundation work. Current merged work
establishes:

- community, governance, security, and mixed-license files;
- root/path-scoped agent instructions;
- event/source/observation/release JSON Schemas;
- provider, surface, model, and agent-app registries;
- deterministic `apw validate`, `apw index`, `apw latest`, `apw diff`, and
  `apw explain` commands;
- deterministic `apw candidate generate` command for review-only findings
  derived from source observations;
- deterministic candidate-review PR body generation for daily source changes;
- optional model-pluggable LLM review request packets for candidate PRs;
- downstream repository impact reports through `apw repo check` and a composite
  GitHub Action;
- schema-backed generic webhook and Slack-compatible notification payloads
  through `apw notify`;
- ecosystem mapping payloads for LiteLLM, models.dev, Langfuse, Helicone, and
  OpenLIT through `apw ecosystem render`;
- a repo-root Codex plugin package with APW skills and read-only MCP config;
- public maintainer roles, source-owner mapping, release-manager gates, and a
  roadmap for v0.1 through v1.0;
- a first reviewed canonical event seed set for OpenAI, Anthropic, Google
  Vertex AI, AWS Bedrock, and Azure OpenAI;
- synthetic parser fixtures for status feeds, Statuspage-style status pages,
  model-doc identifiers, pricing signals, and AWS Bedrock model-card display
  refs;
- tested read-only MCP adapter helpers;
- CI and scheduled schema-backed data-release dry-run verification.

## Install From Checkout

```bash
uv sync --all-extras
uv lock --check
uv run apw validate
uv run apw index --check
uv run apw source test
uv run apw release dry-run --output .apw/release-dry-run
uv run apw candidate generate --observations tests/fixtures/observations/candidate-observations.json --output .apw/candidates --created-at 2026-05-31T20:15:00Z
uv run apw candidate review-pr-body --observations tests/fixtures/observations/candidate-observations.json --candidates .apw/candidates
uv run apw review request --candidates .apw/candidates --reviewer codex --created-at 2026-05-31T20:15:00Z
uv run apw repo check --repo . --since 3650d --risk low
uv run apw notify webhook --since 7d --risk medium --output .apw/apw-webhook.json
uv run apw notify slack --since 7d --risk medium --output .apw/apw-slack.json
uv run apw ecosystem render --target litellm --since 30d --risk medium --output .apw/litellm-mapping.json
uv run apw latest
```

Python package publication uses PyPI Trusted Publishing through the protected
`pypi` environment. See
[docs/operations/python-package-release.md](docs/operations/python-package-release.md).
The npm package remains deferred until the schema/feed contract is stable enough
to justify a JavaScript distribution.

## Feed Artifacts

Generated artifacts live under `data/`:

- `data/events/*.json`
- `data/feeds/events.json`
- `data/feeds/events.ndjson`
- `data/feeds/latest.json`
- `data/feeds/rss.xml`
- `data/indexes/provider/*.json`
- `data/indexes/kind/*.json`
- `data/releases/dev/manifest.json`

Release dry runs use CalVer IDs such as `data-2026.06.01`, build
release-shaped artifacts under ignored `.apw/`, verify manifest checksums,
license layout, dependency lock presence, workflow token boundaries, source
ownership, maintainer release docs, and required GitHub CI,
CodeQL/code-scanning, Dependency Review, branch-protection, artifact-review,
and attestation gates without publishing a tag.

The normalized factual event data and generated feed artifacts are dedicated to
the public domain under CC0-1.0. Code, schemas, docs, tests, and tooling are
Apache-2.0.

## Source Refresh

Official source packages can be checked locally:

```bash
uv run apw source test
uv run apw source fetch --source openai.status
```

The scheduled source-refresh workflow fetches enabled official sources, stores
only fingerprints, generates review candidates when parser claims exist, and
opens a draft candidate-review PR when source state or candidate files change.
It does not publish provider events or commit raw source content.

Source descriptors declare explicit graduation posture. `enabled_deterministic`
sources are fetched by automation; `blocked_pending_parser` sources need parser
fixtures before unattended refresh; `manual_review_only` sources can support
reviewed events but remain maintainer-triggered.
Broad lifecycle pages can additionally declare `content_scope` so APW hashes and
parses only a maintainer-owned HTML heading range.

Review candidates are separate from published events:

```bash
uv run apw candidate generate \
  --observations .apw/source-observations.json \
  --output .apw/candidates \
  --created-at 2026-05-31T20:15:00Z
```

Candidate files are maintainer-review input. Promotion to `data/events/` remains
manual. The initial seed events are reviewed by maintainers from official
provider-controlled sources and do not copy raw provider page prose.

Current parser output is conservative by design: changed official sources create
generic maintainer-review claims; Atom and Statuspage-style status sources
expose hashes/timestamps instead of copied incident text; model-doc parsers
extract only bounded model identifiers; lifecycle-doc parsers extract bounded
model identifiers and dates; and pricing parsers emit bounded pricing/model
signals such as input/output, cached input, batch, priority, regional, and
provisioned-throughput markers. Surrounding headings,
descriptions, issue bodies, PR comments, social text, and page prose remain
untrusted and are not copied.

Render the same draft PR body used by automation:

```bash
uv run apw candidate review-pr-body \
  --observations .apw/source-observations.json \
  --candidates data/candidates/review \
  --validation-output .apw/candidate-review-validation.txt
```

Render a bounded optional LLM review request for Codex or Vertex Gemini Flash:

```bash
uv run apw review request \
  --candidates data/candidates/review \
  --reviewer codex \
  --created-at 2026-05-31T20:15:00Z \
  --output .apw/llm-review-request.json
```

The review request omits candidate claim text, treats all source/candidate text
as untrusted data, and gives the reviewer no merge, publish, source-write, tag,
release-token, or OIDC authority. Reviewer outputs can be checked with
`apw review eval`, which validates the result schema and scores recall,
curation precision, faithfulness to request evidence refs, and prompt-injection
safety.

## First Providers

The initial official-source registry covers:

- OpenAI
- Anthropic
- Google Gemini / Vertex AI
- AWS Bedrock
- Azure OpenAI

Community, social, and third-party sources can create review candidates, but
they do not publish canonical events without maintainer review.

## Core Model

APW uses a stable `ProviderEvent` envelope plus a typed `EventDetail` payload and
repeatable `ImpactAssessment` rows. This avoids one giant nullable event model
and keeps pricing, quota, model lifecycle, token accounting, status, and API
contract changes precise.

See:

- [Architecture](docs/architecture.md)
- [Event Schema](docs/schema/event.md)
- [Agent Consumption](docs/agent-consumption.md)
- [Plugin Contract](docs/plugin-contract.md)
- [Read-Only MCP Contract](docs/operations/mcp.md)
- [Downstream GitHub Action](docs/integrations/github-action.md)
- [Webhook And Slack Payloads](docs/integrations/webhooks.md)
- [Ecosystem Mappings](docs/integrations/ecosystem-mappings.md)
- [Codex Plugin](docs/operations/codex-plugin.md)

## Contributing

Use pull requests for every code, schema, source, data, docs, and workflow
change. Start with [CONTRIBUTING.md](CONTRIBUTING.md).

For source packages, see
[docs/contributors/source-packages.md](docs/contributors/source-packages.md).
Source ownership is tracked in [SOURCE_OWNERS.md](SOURCE_OWNERS.md), release
settings are tracked in
[docs/operations/repository-settings.md](docs/operations/repository-settings.md),
and roadmap priorities are tracked in [ROADMAP.md](ROADMAP.md).

## License

| Asset | License |
| --- | --- |
| Code, schemas, docs, tests, CLI, MCP shell | Apache-2.0 |
| Normalized factual data and generated feeds | CC0-1.0 |
| Provider names and trademarks | Owned by their respective owners |

See [DATA_LICENSE.md](DATA_LICENSE.md), [TRADEMARKS.md](TRADEMARKS.md), and
`LICENSES/`.
