# Downstream GitHub Action

Downstream repositories can use the root APW composite action to scan their code
for AI provider, model, and agent-app refs and compare those refs with reviewed
APW events.

Example workflow:

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
