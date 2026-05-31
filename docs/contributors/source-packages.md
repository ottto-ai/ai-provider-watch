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
- parser output has expected observations or review candidates;
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

## Candidate Fixtures

Candidate parsers emit review-only `FindingCandidate` JSON from observation
metadata and parser-produced `candidate_claims`. They must not copy provider
pages or execute source text. `candidate_claims` may carry only bounded
`claim_text` plus an optional `candidate_kind`; raw excerpts, screenshots, HTML,
JSON payloads, and arbitrary nested parser output are rejected by schema.

Run the contract fixture:

```bash
uv run apw candidate generate \
  --observations tests/fixtures/observations/candidate-observations.json \
  --output .apw/candidates \
  --created-at 2026-05-31T20:15:00Z
```

Provider-specific parser fixtures should cover:

- stable candidate IDs and dedupe keys;
- expected candidate kinds;
- official source authority and allowed domains;
- empty/no-change observations;
- malformed observation handling;
- prompt-injection text treated as inert data.
