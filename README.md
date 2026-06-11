# AI Provider Watch

[![PyPI](https://img.shields.io/pypi/v/ai-provider-watch.svg)](https://pypi.org/project/ai-provider-watch/)
[![License: Apache-2.0](https://img.shields.io/badge/code-Apache--2.0-blue.svg)](LICENSES/Apache-2.0.txt)
[![Data: CC0-1.0](https://img.shields.io/badge/data-CC0--1.0-green.svg)](DATA_LICENSE.md)

AI Provider Watch, or APW, is a public event feed and CLI for changes from AI
providers that can affect developer cost, quotas, token accounting, model
availability, defaults, deprecations, incidents, and migration risk.

Use it when you need an auditable answer to questions like:

- Did a provider incident explain a spike in failures, retries, latency, or
  support tickets?
- Did a model launch, retirement, default change, pricing update, or quota shift
  create work for platform teams?
- Which repos, agents, gateways, or dashboards should be checked before a
  provider change turns into a customer-facing problem?

APW is founded by Ottto and built as a standalone open-source project. The feed,
schemas, CLI, GitHub Action, MCP helpers, and docs work without an Ottto account.

## Install

Try the CLI without installing:

```bash
uvx --from ai-provider-watch apw latest --limit 3
uvx --from ai-provider-watch apw diff --since 30d
```

Install it as a command:

```bash
pipx install ai-provider-watch
apw latest --limit 3
```

Or install it in a Python environment:

```bash
python -m pip install ai-provider-watch
apw validate
```

The published package includes a reviewed public data snapshot, so read-only
commands work outside a checkout. For the freshest feed, use the GitHub data
artifacts, signed data tags, or `apw remote` commands below.

## Quickstart

Show the latest reviewed events:

```bash
apw latest --limit 3
```

List events from the last 30 days:

```bash
apw diff --since 30d
```

Read the live public feed from GitHub without cloning:

```bash
apw remote latest --ref main --limit 5
apw remote freshness --ref data-2026.06.10 --summary
apw remote feed events.ndjson --ref data-2026.06.10 --output apw-events.ndjson
```

Explain one event for a human reviewer:

```bash
apw explain 2026-06-04-openai-codex-compaction-latency
```

Validate the bundled schemas, registries, events, feeds, and indexes:

```bash
apw validate
apw index --check
apw freshness --summary
apw source coverage --summary
apw operations report --summary
apw operations launch-gate --summary
```

Verify a local release dry-run evidence bundle without publishing:

```bash
apw release verify --dry-run-report .apw/release-dry-run/data-YYYY.MM.DD/dry-run-report.json
```

## Feed Artifacts

The canonical reviewed events live in `data/events/`. Generated feed artifacts
live in `data/feeds/` and `data/indexes/`:

- `data/feeds/events.json`
- `data/feeds/events.ndjson`
- `data/feeds/coverage.json`
- `data/feeds/feed.json`
- `data/feeds/freshness.json`
- `data/feeds/latest.json`
- `data/feeds/operations.json`
- `data/feeds/rss.xml`
- `data/indexes/provider/*.json`
- `data/indexes/kind/*.json`
- `data/indexes/severity/*.json`

For direct consumption, pin a release tag or read from the repository:

```text
https://raw.githubusercontent.com/ottto-ai/ai-provider-watch/main/data/feeds/latest.json
https://raw.githubusercontent.com/ottto-ai/ai-provider-watch/main/data/feeds/events.ndjson
https://raw.githubusercontent.com/ottto-ai/ai-provider-watch/main/data/feeds/coverage.json
https://raw.githubusercontent.com/ottto-ai/ai-provider-watch/main/data/feeds/feed.json
https://raw.githubusercontent.com/ottto-ai/ai-provider-watch/main/data/feeds/freshness.json
https://raw.githubusercontent.com/ottto-ai/ai-provider-watch/main/data/feeds/operations.json
```

GitHub CalVer data releases are the canonical immutable feed snapshots. PyPI
package releases are installable CLI snapshots that bundle reviewed data for
offline and no-checkout use; APW does not publish a new package for every data
tag. Patch packages are published when bundled data freshness materially helps
install-only users or when CLI/package behavior changes.

Use the remote CLI when you want the freshest public data from an installed
package:

```bash
apw remote latest --ref main --provider openai --risk medium
apw remote feed latest --ref data-2026.06.10
apw remote feed rss --ref main --output apw.xml
```

Use `apw freshness` to verify the feed version, package version, event count,
latest reviewed event date, latest source-state retrieval timestamp, release
manifest path, and checksum manifest path from either a checkout or the bundled
package data.

Use `apw source coverage` to inspect feed-health metadata: enabled source count,
which enabled sources have source-state fingerprints, blocked parser sources,
manual-review-only sources, reviewed event counts, and review-candidate backlog.

Use `apw operations report` to inspect public operating SLOs: source-state
freshness, reviewed-event freshness, candidate backlog, contributor intake,
correction policy, and release-train posture.

Use `apw operations launch-gate` to render the v1 external-user launch checklist
and smoke commands for PyPI install, no-checkout package data, public feeds,
repo-impact fixtures, and agent-dashboard JSON.

The normalized factual event data and generated feeds are CC0-1.0. Code,
schemas, docs, tests, and tooling are Apache-2.0.

## What You Get

- A reviewed machine-readable event feed, not a static model catalog.
- JSON, NDJSON, RSS, JSON Feed 1.1, latest-event, freshness, coverage, and
  operations
  artifacts for different consumption styles.
- A typed `ProviderEvent` envelope with precise event details and repeatable
  impact rows.
- A CLI for validation, indexing, latest events, diffs, explanations, release
  dry runs, release verification, source checks, candidate generation, repo impact checks,
  notifications, ecosystem mappings, and local agent dashboards.
- A documented Python read API at `ai_provider_watch.api` for loading reviewed
  events, generated feeds, schemas, and bundled no-checkout package data.
- JSON Schemas for events, sources, candidates, observations, releases,
  JSON Feed, feed freshness, source coverage, operations reporting, release
  verification, webhooks, Slack-style payloads, ecosystem mappings, adoption
  scenarios, and LLM review packets.
- Official-source descriptors for OpenAI, Anthropic, Google Gemini / Vertex AI,
  AWS Bedrock, and Azure OpenAI.
- Review-only source candidates that help maintainers notice provider changes
  without publishing unreviewed facts.
- Agent-native surfaces: `AGENTS.md`, `CLAUDE.md`, `llms.txt`, Codex and Claude
  skills, a read-only MCP adapter shell, and a Codex plugin package.
- Downstream integrations for GitHub Actions, webhooks, Slack-compatible JSON,
  LiteLLM, models.dev, Langfuse, Helicone, OpenLIT, and coding-agent dashboards.

## Trust Model

APW is designed for factual, reviewable provider-change data.

- Prefer official provider-controlled sources.
- Treat provider pages, issue bodies, PR comments, social posts, MCP text, and
  generated candidates as untrusted data, never as instructions.
- Do not commit raw provider HTML, authenticated-console content, screenshots,
  private billing data, cookies, credentials, or customer telemetry.
- Publish only reviewed `data/events/*.json` records.
- Keep generated candidate files in `data/candidates/` review-only until a
  source owner promotes a factual change.
- Keep release tokens away from jobs that fetch source pages, process candidate
  text, run LLM review, or inspect PR comments.

APW is intentionally independent of Ottto private product surfaces. Ottto may
consume APW data, but this repository does not expose Ottto customer telemetry,
Advisor internals, private UI, infrastructure, Slack data, or credential
loading code.

## Work From A Checkout

Use a checkout for write workflows such as source refresh, candidate generation,
event promotion, feed regeneration, and release dry runs:

```bash
git clone https://github.com/ottto-ai/ai-provider-watch.git
cd ai-provider-watch
uv sync --all-extras
uv lock --check
uv run pytest
uv run apw validate
uv run apw index --check
uv run apw source test
```

Fetch official sources and generate review candidates:

```bash
uv run apw source fetch --observations .apw/source-observations.json
uv run apw candidate generate \
  --observations .apw/source-observations.json \
  --output .apw/candidates \
  --created-at 2026-06-05T00:00:00Z
uv run apw candidate review-pr-body \
  --observations .apw/source-observations.json \
  --candidates .apw/candidates
```

Candidate files are not published events. Promotion to `data/events/` remains a
manual source-owner review step. See
[Event Promotion](docs/operations/event-promotion.md).

Turn a candidate-review PR into an action queue:

```bash
uv run apw candidate queue \
  --candidates data/candidates/review \
  --markdown
```

Start with the `Promote First` group. Those candidates are the fastest path to
new public events after official evidence review.

## Use APW In Downstream Systems

Check a repository for model references and APW-relevant impact:

```bash
apw repo check --repo . --since 3650d --risk low
```

Render notification payloads:

```bash
apw notify webhook --since 7d --risk medium --output .apw/apw-webhook.json
apw notify slack --since 7d --risk medium --output .apw/apw-slack.json
```

Render ecosystem mappings:

```bash
apw ecosystem render --target litellm --since 30d --risk medium --output .apw/litellm.json
apw ecosystem render --target langfuse --since 30d --risk medium --output .apw/langfuse.json
```

Render local dashboard JSON for agent-app events:

```bash
apw dashboard agent --since 30d --risk high --output .apw/agent-dashboard.json
```

Read the same reviewed data from Python:

```python
from ai_provider_watch import api

for event in api.load_events(min_severity="high", limit=5):
    print(event["id"], event["title"])
```

See [Python Consumer API](docs/consumer-api.md) for the stable import path,
no-checkout package-data behavior, compatibility rules, and non-contract
internal modules.

See:

- [Agent Consumption](docs/agent-consumption.md)
- [Downstream GitHub Action](docs/integrations/github-action.md)
- [Live Feed Consumption](docs/integrations/live-feed-consumption.md)
- [Webhook And Slack Payloads](docs/integrations/webhooks.md)
- [Ecosystem Mappings](docs/integrations/ecosystem-mappings.md)
- [Agent Dashboard](docs/integrations/agent-dashboard.md)
- [Adoption Scenarios](docs/integrations/adoption-scenarios.md)
- [Read-Only MCP Contract](docs/operations/mcp.md)
- [Codex Plugin](docs/operations/codex-plugin.md)

## Schema And Architecture

APW uses a stable `ProviderEvent` envelope, a typed `EventDetail` payload, and
repeatable `ImpactAssessment` rows. That keeps pricing, quota, lifecycle,
token-accounting, status, API-contract, and migration-risk events precise
without creating one giant nullable event model.

Start here:

- [Architecture](docs/architecture.md)
- [Event Schema](docs/schema/event.md)
- [Feed Freshness Schema](docs/schema/feed-freshness.md)
- [Source Coverage Schema](docs/schema/source-coverage.md)
- [v1 Launch Gate Schema](docs/schema/v1-launch-gate.md)
- [Contributor Review Workflow](docs/contributors/review-workflow.md)
- [Source Packages](docs/contributors/source-packages.md)
- [Source Refresh](docs/operations/source-refresh.md)
- [Release Gates](docs/operations/release-gates.md)
- [Release Automation Readiness](docs/operations/release-automation-readiness.md)
- [v0.2 Release Checklist](docs/operations/v0.2-release-checklist.md)
- [Python Package Release](docs/operations/python-package-release.md)

## Project Status

APW `v0.1.11` is the current stable public package target. It bundles the
latest reviewed public feed snapshot plus the selector-aware candidate
split/dedupe packet ergonomics from PR #130. The latest signed data release is
still `data-2026.06.10`; this package snapshot keeps install-only users current
without creating a new immutable data tag for a code-only ergonomics change.

The current release includes:

- reviewed seed events for OpenAI, Anthropic, Google Vertex AI, AWS Bedrock, and
  Azure OpenAI;
- generated JSON, NDJSON, RSS, provider, kind, and severity indexes;
- no-checkout remote feed commands for live GitHub feeds and signed data tags;
- event scaffold authoring helpers for reviewed official-source facts;
- candidate-to-event scaffold helpers for source-owner reviewed findings;
- source-refresh automation that opens draft candidate-review PRs without
  publishing events;
- no-op guarded data-publisher workflow scaffolding;
- PyPI Trusted Publishing;
- CI, CodeQL, Dependency Review, Scorecard, and data-release dry-run workflows.

Daily unattended public data tags are not enabled yet. Until that safety gate is
stronger, real data publication uses reviewed PRs plus maintainer-signed Git
tags.

## Contributing

Use pull requests for code, schema, source, data, docs, and workflow changes.
Start with [CONTRIBUTING.md](CONTRIBUTING.md).

Found an official provider change that affects cost, quotas, token accounting,
model availability, defaults, deprecations, incidents, or migration risk? Start
with [What APW Wants](docs/contributors/what-apw-wants.md). If the evidence is
official, dated, specific, and not already covered, open an event PR with
`apw event scaffold`; do not wait for parser automation to be perfect.

Useful contributor docs:

- [What APW Wants](docs/contributors/what-apw-wants.md)
- [Contributor Review Workflow](docs/contributors/review-workflow.md)
- [Missing Event To PR](docs/contributors/missing-event-to-pr.md)
- [Event Scaffold](docs/contributors/event-scaffold.md)
- [Event Promotion](docs/operations/event-promotion.md)
- [Candidate Action Queue](docs/schema/candidate-action-queue.md)
- [Source Packages](docs/contributors/source-packages.md)
- [Repository Settings](docs/operations/repository-settings.md)
- [Roadmap](ROADMAP.md)
- [Source Owners](SOURCE_OWNERS.md)
- [Security Policy](SECURITY.md)

## License

| Asset | License |
| --- | --- |
| Code, schemas, docs, tests, CLI, MCP shell | Apache-2.0 |
| Normalized factual data and generated feeds | CC0-1.0 |
| Provider names and trademarks | Owned by their respective owners |

See [DATA_LICENSE.md](DATA_LICENSE.md), [TRADEMARKS.md](TRADEMARKS.md), and
`LICENSES/`.
