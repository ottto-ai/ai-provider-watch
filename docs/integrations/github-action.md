# Downstream GitHub Action

Downstream repositories can use the root APW composite action to scan their code
for AI provider, model, and agent-app refs and compare those refs with reviewed
APW events.

Copy-paste workflow for pull requests and manual checks:

```yaml
name: AI Provider Watch

on:
  pull_request:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  apw:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: ottto-ai/ai-provider-watch@main
        with:
          repo-path: .
          since: 3650d
          risk: low
          fail-on-severity: high
```

The action installs APW from the action checkout, runs `apw repo check`, writes a
JSON report to `.apw/impact-report.json`, and appends a job summary. It does not
post PR comments by default and does not need write permissions.

Scheduled copy-paste workflow for repositories that want a daily passive scan:

```yaml
name: AI Provider Watch Daily Scan

on:
  schedule:
    - cron: "17 8 * * *"
  workflow_dispatch:

permissions:
  contents: read

jobs:
  apw:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: ottto-ai/ai-provider-watch@main
        with:
          repo-path: .
          since: 30d
          risk: medium
          output: .apw/impact-report.json
      - uses: actions/upload-artifact@v7
        with:
          name: apw-impact-report
          path: .apw/impact-report.json
          if-no-files-found: error
```

For a stable production repository, pin the action to a release tag or audited
commit SHA once the first non-alpha APW package/action release exists.

## No-Checkout Live Feed Workflow

If a downstream repository only needs public APW feed artifacts from GitHub, use
the published package and `apw remote` instead of checking out APW as an action:

```yaml
name: AI Provider Watch Live Feed

on:
  workflow_dispatch:
  schedule:
    - cron: "23 8 * * *"

permissions:
  contents: read

jobs:
  apw:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: astral-sh/setup-uv@v7
      - run: |
          mkdir -p .apw
          uvx --from ai-provider-watch apw remote latest --ref main --risk medium --limit 20 > .apw/apw-latest.json
          uvx --from ai-provider-watch apw repo check --repo . --since 3650d --risk medium --output .apw/apw-impact-report.json
```

See [Live Feed Consumption](live-feed-consumption.md) for the full workflow
file, Python API example, agent preflight, and MCP sidecar pattern.

## Local Equivalent

```bash
uv run apw repo check \
  --repo /path/to/downstream/repo \
  --since 3650d \
  --risk low \
  --output .apw/impact-report.json
```

The report contains matched refs and reviewed event summaries. It does not copy
source lines from the downstream repository; repo text is untrusted data.

The report conforms to `schemas/repo-impact.schema.json`. A checked smoke
fixture lives at `tests/fixtures/smoke/repo-impact-openai.json`; tests normalize
the absolute repo path so the fixture remains portable.

## Security Boundary

- No Ottto account is required.
- No GitHub token, release token, or write permission is required.
- Do not run this action with `pull_request_target`.
- Do not add `contents: write`, `pull-requests: write`, or secret-bearing steps
  unless a downstream repository independently owns and reviews that workflow.
- Treat downstream repository text as untrusted data. APW reports refs, file
  paths, and event IDs; it does not execute repo text as instructions.
