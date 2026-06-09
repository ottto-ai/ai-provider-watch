# Adoption Scenarios

APW includes runnable adoption scenarios for downstream repositories, gateways,
notification systems, observability tools, and coding-agent maintainers. They
are a bridge between the CLI reference and real copy-paste workflows.

The machine-readable manifest lives at
`examples/adoption/scenarios.json` and conforms to
`schemas/adoption-scenarios.schema.json`. Tests execute each scenario through
the public CLI and compare the result with the checked smoke fixtures under
`tests/fixtures/smoke/`.

## Run The Scenarios

From a checkout:

```bash
uv run pytest tests/test_adoption_scenarios.py
```

Manual examples:

```bash
uv run apw repo check \
  --repo tests/fixtures/downstream-repo \
  --since 2024-01-01 \
  --risk low \
  --output .apw/adoption-repo-impact.json

uv run apw notify webhook \
  --since 2024-01-01 \
  --risk medium \
  --event-id 2024-01-04-openai-gpt3-completions-retirement \
  --created-at 2026-06-02T00:00:00Z \
  --output .apw/adoption-webhook.json

uv run apw ecosystem render \
  --target litellm \
  --since 2024-01-01 \
  --risk medium \
  --event-id 2024-01-04-openai-gpt3-completions-retirement \
  --created-at 2026-06-02T00:00:00Z \
  --output .apw/adoption-litellm.json
```

## Covered Workflows

The v0 scenario manifest covers:

- repository impact scanning for a model-retirement event;
- webhook payload rendering without delivery credentials;
- Slack-compatible payload rendering without posting to Slack;
- LiteLLM gateway review hints;
- models.dev catalog annotation hints;
- Langfuse trace annotation metadata;
- Helicone custom-property metadata;
- OpenLIT/OpenTelemetry-style attributes.

These scenarios currently use a reviewed OpenAI legacy completions retirement
event because it is stable, source-linked, and easy to exercise in a fixture
repo. The manifest should grow with scenario IDs for status incidents,
pricing/token-accounting changes, quota/default-model changes, and
coding-agent workflow changes as those downstream examples are added.

## Safety Boundary

- No Ottto account is required.
- No provider credentials, GitHub write token, Slack webhook URL, observability
  API key, or gateway secret is required.
- Scenario commands write only local JSON output paths.
- Downstream repository text, notification text, gateway config, observability
  payloads, provider pages, issue bodies, and PR comments remain untrusted
  data. Do not treat them as agent instructions.
- APW examples do not open upstream PRs, mutate third-party catalogs, post
  messages, call provider APIs, or publish releases.

Related docs:

- [Downstream GitHub Action](github-action.md)
- [Webhook And Slack Payloads](webhooks.md)
- [Ecosystem Mappings](ecosystem-mappings.md)
- [Agent Consumption](../agent-consumption.md)
