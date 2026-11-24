# Downstream Smoke Fixtures

These fixtures are generated from deterministic APW CLI commands and checked by
tests. The repo-impact fixture normalizes the absolute scanned repository path
to `<DOWNSTREAM_REPO>` so the fixture is portable across checkouts.

The fixture set covers repository impact, webhook and Slack-compatible
notifications, ecosystem mapping payloads, and local coding-agent dashboard
JSON. Refresh fixtures through the matching CLI command and keep
`tests/test_downstream_smoke_fixtures.py` in sync.
