# Source Packages

Each provider source package is a small, reviewable contract.

Example:

```text
sources/openai/
  source.json
  README.md
  fixtures/
    pricing-docs.html
  parsers/
    pricing.py
```

Acceptance rules:

- descriptor has a stable `key`;
- source authority is declared;
- allowed domains are explicit;
- fixture inputs are included;
- parser output has expected observations or candidates;
- no credentials are required by default;
- no raw provider pages are published as data;
- generated facts keep source URLs and retrieval timestamps.

Run:

```bash
uv run apw source test
uv run apw validate
```

Phase 2 source refresh uses fingerprints only. Raw source bodies are fetched,
hashed, and discarded; the scheduled workflow commits only
`data/source-state/fingerprints.json` when an enabled source changes.
