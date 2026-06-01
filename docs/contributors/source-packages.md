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

Phase 2 source refresh uses fingerprints plus sanitized parser output. Raw
source bodies are fetched, parsed into bounded metadata, hashed, and discarded.
The scheduled workflow commits only `data/source-state/fingerprints.json` and
generated review candidates when an enabled source changes.

## Candidate Fixtures

Candidate parsers emit review-only `FindingCandidate` JSON from observation
metadata and parser-produced `candidate_claims`. They must not copy provider
pages or execute source text. `candidate_claims` may carry only bounded
`claim_text` plus an optional `candidate_kind`; raw excerpts, screenshots, HTML,
JSON payloads, and arbitrary nested parser output are rejected by schema.

The first parser layer is deliberately conservative. It emits a generic review
claim when an official source fingerprint changes; for Atom and
Statuspage-style status sources it stores hashes/timestamps rather than copied
incident text; for model docs it stores bounded model identifiers; and for
pricing pages it stores bounded pricing/model signals rather than copied
pricing-table prose. Provider-specific parsers should add richer factual
extraction only when fixtures prove the output is deterministic, bounded,
source-linked, and free of raw provider prose.

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

`source.json` may also declare executable parser fixtures:

```json
{
  "parser_fixtures": [
    {
      "source_key": "google.ai_docs",
      "input": "fixtures/ai-docs-models.html",
      "expected": "fixtures/ai-docs-models.expected.json",
      "changed": true
    }
  ]
}
```

`apw source test` runs those fixtures and compares the full sanitized parser
payload exactly. Fixture inputs must be synthetic or minimal excerpts created
for APW tests; do not commit real provider pages. Expected payloads may include
bounded factual identifiers such as model IDs, pricing signal enums, hashes,
RFC3339 timestamps, and templated candidate claims. They must not include copied
provider headings, descriptions, incident titles, pricing-table prose, PR
comments, issue bodies, or prompt-like text.

## Candidate Review Automation

The daily workflow uses the same contract to create draft candidate-review PRs
when official-source fingerprints change. A source package should therefore keep
candidate output deterministic: stable IDs, stable `candidate_kind`, stable
source/provider refs, and no raw provider content. The generated PR body lists
observation counts, source keys, candidate file paths, validation output, and the
review checklist, but it does not quote source page text or candidate claim text.
