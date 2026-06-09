# Source Packages

Each provider source package is a small, reviewable contract.
For the broader contributor path around sources, fixtures, candidates,
corrections, reviewed events, and source-owner outcomes, see
[Contributor Review Workflow](review-workflow.md).

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
- every source key is listed in [SOURCE_OWNERS.md](../../SOURCE_OWNERS.md);
- source authority is declared;
- allowed domains are explicit;
- source automation posture is explicit;
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

## Source Graduation

Each source descriptor declares its publication posture:

- `enabled_deterministic`: fetched by scheduled refresh and backed by parser
  fixtures that emit only bounded metadata or review candidates.
- `blocked_pending_parser`: official evidence source that should not be
  fetched unattended until parser fixtures cover the relevant structured facts.
- `manual_review_only`: official source that can support reviewed events but
  remains maintainer-triggered because unattended source selection is too broad.

Enabled sources must not use the `manual_review` parser and must not list
graduation blockers. Disabled sources must document blockers so maintainers can
see why they are not part of deterministic refresh.

Lifecycle pages that mix multiple product families should declare
`content_scope` with `kind: html_heading_range`. APW applies that scope before
fingerprinting and parsing, so out-of-scope sections can change without creating
provider candidates for the scoped source. A scoped source still stays
`blocked_pending_parser` until fixtures and live fetch evidence prove the
heading range is stable enough for unattended refresh.

Use `apw source fetch --include-disabled --source <source-key>` for maintainer
live smokes of blocked descriptors. The flag requires an explicit source and is
rejected with `--write-state`, so smoke evidence stays under `.apw/` until a
separate PR enables deterministic refresh.

## Candidate Fixtures

Candidate parsers emit review-only `FindingCandidate` JSON from observation
metadata and parser-produced `candidate_claims`. They must not copy provider
pages or execute source text. `candidate_claims` may carry only bounded
`claim_text` plus an optional `candidate_kind`; raw excerpts, screenshots, HTML,
JSON payloads, and arbitrary nested parser output are rejected by schema.

The first parser layer is deliberately conservative. It emits a generic review
claim when an official source fingerprint changes; for Atom and
Statuspage-style status sources it stores hashes/timestamps rather than copied
incident text; for model docs it stores bounded model identifiers; for lifecycle
docs it stores bounded model identifiers and dates; and for pricing pages it
stores bounded pricing/model signals and optional `price_point` rows rather than
copied pricing-table prose. A `price_point` may include only the bounded model
ID, billing dimension, numeric USD price per 1M tokens, normalized unit, and
parser name.

Pricing sources also persist a bounded `pricing_rows` snapshot in
`data/source-state/fingerprints.json` when the parser emits unambiguous
`price_point` rows or pricing signals. That state is intentionally compact:
model ID, billing dimension, numeric price, unit, signal enum, row key, and row
hash. It must not include provider table prose, headings, raw HTML, screenshots,
or prompt-like source text. On a later refresh, APW can compare those row facts
and emit selector-scoped review candidates for price changes or token-accounting
signals. Ambiguous duplicate rows, such as multiple regions with the same model
and billing dimension, fall back to generic source-owner review.

Sources that emit `limit_signal` or `default_model_signal` items may persist a
bounded `operational_rows` snapshot. That state is limited to model ID, default
scope, limit dimension, numeric limit value, unit, signal row key, and row hash.
It must not include quota-table prose, headings, explanatory paragraphs, raw
HTML, screenshots, authenticated account limits, or prompt-like source text.
Ambiguous duplicate limit/default rows fall back to generic source-owner review.

When a source descriptor declares `content_scope`, its parser fixture should
prove that out-of-scope HTML sections are ignored.
Provider-specific parsers should add richer factual extraction only when
fixtures prove the output is deterministic, bounded, source-linked, and free of
raw provider prose.

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
bounded factual identifiers such as model IDs, pricing signal enums,
`price_point` numeric facts, hashes, RFC3339 timestamps, and templated candidate
claims. They must not include copied provider headings, descriptions, incident
titles, pricing-table prose, PR comments, issue bodies, or prompt-like text.

## Candidate Review Automation

The daily workflow uses the same contract to create draft candidate-review PRs
when official-source fingerprints change. A source package should therefore keep
candidate output deterministic: stable IDs, stable `candidate_kind`, stable
source/provider refs, and no raw provider content. The generated PR body lists
observation counts, source keys, candidate file paths, validation output, and the
review checklist, but it does not quote source page text or candidate claim text.
