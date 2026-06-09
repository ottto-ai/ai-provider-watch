# Source Refresh

Phase 2 introduces deterministic official-source fingerprints.

Run locally:

```bash
uv run apw source test
uv run apw source fetch --observations .apw/source-observations.json
```

To update committed source state:

```bash
uv run apw source fetch --write-state --observations .apw/source-observations.json
```

The scheduled workflow runs daily and opens a draft PR only when
`data/source-state/fingerprints.json` or generated review candidates change.
Raw provider content is fetched, hashed, and discarded. Event promotion remains
a separate maintainer-reviewed workflow.

## Source Graduation Posture

`sources/registry.json` separates fetch eligibility from reviewed-evidence
eligibility:

- `enabled_deterministic` sources are enabled and fixture-backed. The daily
  workflow may fetch them and generate review candidates.
- `blocked_pending_parser` sources are official evidence sources that stay
  disabled until parser fixtures cover their structured lifecycle or policy
  facts.
- `manual_review_only` sources are official but broad, such as docs without a
  dated change signal. Maintainers may cite them in reviewed events, but
  unattended refresh must not select articles or publish events from them.

`enabled: false` does not mean a source is untrusted; it means APW will not fetch
that source unattended until the descriptor's graduation blockers are resolved.
When a descriptor declares `content_scope`, APW computes its fingerprint from
the scoped HTML heading range and sends only that range to the parser. The full
response hash remains available as `content_sha256`. If the heading range is not
found, APW reports a parser error instead of parsing the broad page as
provider-specific evidence.

Maintainers can live-smoke blocked or manual-review descriptors explicitly:

```bash
uv run apw source fetch \
  --include-disabled \
  --source google.vertex_model_versions \
  --observations .apw/source-smoke.json
```

`--include-disabled` requires at least one `--source` and cannot be combined
with `--write-state`. It is for bounded graduation evidence only; scheduled
source refresh still fetches enabled deterministic sources.

## Review Candidate Contract

APW-2.02 adds deterministic candidate generation from observation bundles:

```bash
uv run apw candidate generate \
  --observations .apw/source-observations.json \
  --output .apw/candidates \
  --created-at 2026-05-31T20:15:00Z
```

Candidate output is review input only. The daily workflow must not publish
events from candidates without maintainer review, and workflows that process
source content must not receive release tokens.

## Candidate Review PRs

The daily workflow now builds a draft candidate-review PR after source refresh:

1. fetch enabled official sources, parse sanitized observation metadata, and
   update fingerprint state;
2. clean and regenerate review-only candidates in `data/candidates/review`;
3. run `apw validate`, regenerate generated metadata with `apw index`, then
   rerun `apw validate` and `apw index --check`;
4. render a PR body with observation counts, changed source keys, candidate
   file paths, advisory promotion-readiness context, candidate-quality tiers,
   validation output, and a maintainer checklist;
5. commit only `data/source-state/fingerprints.json`, sanitized candidate JSON,
   and generated feed/index/release metadata such as freshness/checksum files.

The repository-level GitHub Actions workflow permission must allow Actions to
create pull requests. The workflow still uses only the default `GITHUB_TOKEN`,
does not receive release tokens or secrets, and deletes the generated remote
branch if PR creation fails after the branch push.

The PR body intentionally omits provider page bodies and candidate claim text.
Candidate JSON can include bounded factual `claim_text`, but those files are not
published events and require maintainer review before promotion to `data/events`.
Because `data/candidates/review` is generated workflow output, each run replaces
its JSON files instead of preserving stale candidates.

The promotion-readiness section is deterministic source-owner context. It may
mark a candidate `auto_promotion_eligible` only when the candidate is official,
provider-controlled, dated by the source type or parser, high-signal,
schema-safe, prompt-safe, non-generic, and non-duplicate in the review window.
Generic "source changed" candidates remain source-owner review work. This is
not publication authority: source-refresh and candidate-review workflows still
cannot publish events, merge PRs, create tags, request OIDC, or read release
tokens.

Maintainers can render the same machine-readable report locally:

```bash
uv run apw candidate readiness \
  --candidates data/candidates/review \
  --created-at 2026-05-31T20:15:00Z \
  --output .apw/promotion-readiness.json
```

Maintainers can also render the candidate-quality report:

```bash
uv run apw candidate quality \
  --candidates data/candidates/review \
  --created-at 2026-05-31T20:15:00Z \
  --output .apw/candidate-quality.json
```

Candidate quality is the source-owner decision lens for issue triage. It scores
only review candidates, not published facts. `high_value` means the candidate is
official, dated, developer-relevant, specific, and evidence-scoped enough for a
review agent to recommend `promote`. `low_signal` means broad source churn,
generic parser output, or weak evidence specificity should normally be rejected
unless a maintainer independently confirms a concrete APW-scope fact. Quality
recommendations are advisory and have the same forbidden authority as
promotion-readiness reports: no event publication, merge, tag, OIDC, or release
token access. When `duplicate_event_ids` is present, source owners should cite
the existing reviewed event and avoid publishing a second ProviderEvent for the
same evidence.

Parser output is intentionally narrow. Dated official announcement parsers may
emit multiple candidate claims for provider-controlled news, changelog, release
note, or What's New entries, but only as bounded facts: date, candidate kind,
provider/model/API subjects, article URL when allowed by the descriptor, title
hash, link hash, selector, and snapshot ref. They must not store article bodies
or copied provider titles. Atom and Statuspage-style status sources expose
hashed refs and timestamps instead of copied titles or incident text. Provider
model-doc parsers extract only allowlisted model identifier shapes.
Lifecycle-doc parsers emit bounded model identifiers, lifecycle dates, row
hashes, and row-scoped candidate claims only when a structured row ties a model
to a lifecycle date; generic lifecycle page churn produces no review candidate.
Pricing parsers emit bounded pricing/model signals such as input/output, cached
input, cache write/hit, batch, priority, regional, and provisioned-throughput markers.
Pricing parsers may also emit `price_point` items with only model ID, billing
dimension, numeric USD price per 1M tokens, normalized unit, and parser name.
The parser fixture command is:

```bash
uv run apw source test
```

Parser fixture expected output must not contain copied provider page prose,
prompt-like source text, issue/PR bodies, or social content.

## Prompt-Injection Red Team

APW keeps explicit red-team payloads in
`tests/fixtures/redteam/untrusted-input-cases.json`. These payloads cover
provider pages, issue bodies, PR comments, social posts, MCP resource text, and
generated candidate packets.

Required behavior:

- parser output may contain bounded facts such as model identifiers, dates,
  hashes, or parser-owned candidate claims, but not source instructions;
- candidate generation rejects prompt-like `claim_text`;
- candidate review PR bodies summarize paths, IDs, kinds, counts, and validation
  output without quoting provider prose or candidate claim text;
- MCP and future LLM review surfaces must treat all source/candidate text as
  inert data and must not expose publish, merge, release-token, or source
  mutation authority.

Run the red-team gate with:

```bash
uv run pytest tests/test_prompt_injection_redteam.py
```

## Optional LLM Review Packet

After a candidate-review PR is generated, maintainers can render a bounded
review packet for Codex or Vertex Gemini Flash:

```bash
uv run apw review request \
  --candidates data/candidates/review \
  --reviewer codex \
  --created-at 2026-05-31T20:15:00Z \
  --output .apw/llm-review-request.json
```

The packet is review-only. It omits candidate claim text, records claim hashes,
declares forbidden actions, and gives the reviewer no merge, event-publish,
source-write, release-token, OIDC, or tag authority. It does include
deterministic promotion-readiness flags, reasons, blockers, canonical event
hints, sanitized evidence summaries, candidate-quality tiers, recommended
actions, and quality blockers so a reviewer can make an affirmative `promote`,
`reject`, `duplicate`, `split`, or `needs_human_review` recommendation for
source-owner review.
