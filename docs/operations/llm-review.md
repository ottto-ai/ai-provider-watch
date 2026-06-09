# LLM Review Lane

APW's LLM review lane is optional and review-only. It prepares a bounded
machine-readable request packet for a reviewer such as Codex or Vertex Gemini
Flash, but APW does not call a model, merge a PR, publish an event, mutate
sources, tag a release, or read release credentials.

Render a request locally:

```bash
uv run apw review request \
  --candidates data/candidates/review \
  --reviewer codex \
  --created-at 2026-05-31T20:15:00Z \
  --output .apw/llm-review-request.json
```

Render the same contract for Vertex Gemini Flash:

```bash
uv run apw review request \
  --candidates data/candidates/review \
  --reviewer vertex-gemini-flash \
  --model gemini-3.5-flash \
  --created-at 2026-05-31T20:15:00Z \
  --output .apw/llm-review-request.json
```

The `--model` value is an operator-provided identifier. APW validates only that
it is bounded and not prompt-like; it does not verify provider availability.

Validate and score a reviewer result:

```bash
uv run apw review eval \
  --request .apw/llm-review-request.json \
  --result .apw/llm-review-result.json \
  --expected-candidate-id candidate-openai-status-ac93c36c336a899b \
  --expected-decision candidate-openai-status-ac93c36c336a899b=promote \
  --output .apw/llm-review-eval.json
```

`apw review eval` validates the result against
`schemas/llm-review-result.schema.json`, then computes:

- `recall_at_window`: expected candidate IDs found in the review result;
- `curation_precision`: result candidate IDs that were expected for the packet;
- `decision_recall_at_window`: expected advisory decisions found in
  `review_decisions`;
- `decision_curation_precision`: `review_decisions` candidate/decision pairs
  that match expected curation outcomes such as `promote`, `reject`,
  `duplicate`, or `split`;
- `faithfulness_pass`: findings reference only candidates and evidence refs from
  the request;
- `prompt_injection_pass`: findings, review-decision rationale, and residual
  risks do not contain prompt-like instructions.

Reviewers may make an affirmative curation recommendation, but not a mutation.
The request includes deterministic promotion-readiness context for each
candidate when available: flags, reasons, blockers, canonical event hints, and
sanitized evidence summaries. It also includes candidate-quality context when
available: quality tier, recommended action, score, dimensions, reasons,
quality blockers, and bounded event hints. This gives the reviewer enough
context to recommend `promote` when the official dated evidence is strong, or
to explain why the candidate should be rejected, split, deduplicated, or kept
for source-owner review.

For human source-owner event drafting, use `apw candidate packet` instead. That
packet can include bounded generated candidate claim text labeled
`untrusted_data`, plus draft-only ProviderEvent stubs. Do not feed that human
packet to a model as instructions; use `apw review request` for model review.

Each `review_decisions[]` row must include:

- `decision`: `promote`, `reject`, `duplicate`, `split`, or
  `needs_human_review`;
- `promotion_readiness`: `auto_promotion_eligible`,
  `needs_source_owner_review`, `not_ready`, or `duplicate_or_superseded`;
- `promotion_blockers`: concrete blockers that must be cleared before
  promotion;
- `canonical_event_hints`: optional bounded APW event hints such as
  `event_kind`, `provider_refs`, `source_authorities`, `source_types`,
  `impact_kinds`, and sanitized `evidence_refs`.

Use `auto_promotion_eligible` only when every evidence URL is official
provider-controlled evidence, the event is dated, the source is not community or
social, the candidate is not a duplicate, APW schema refs are clear, and no
prompt-injection or scope risk remains. Even then, the result is still advisory:
promotion must go through the guarded CLI/PR path before `data/events` changes.

Use candidate-quality tiers as the reviewer authority ladder:

- `high_value`: recommend `promote` only when promotion-readiness also has no
  blocker and official evidence is specific enough for source-owner event
  authoring;
- `reviewable`: recommend `needs_human_review` until a source owner resolves
  impact mapping, duplicate checks, or event split decisions;
- `low_signal`: recommend `reject` for broad source churn or generic parser
  output unless direct official evidence proves a concrete APW-scope change;
- `duplicate`: recommend `duplicate` and cite the covering candidate or event;
- `blocked`: recommend `reject` or `needs_human_review` until schema, evidence,
  safety, or source blockers are cleared.

## Safety Contract

The review packet:

- omits candidate `claim_text` and includes only its length, SHA-256, and
  prompt-like marker flag;
- includes candidate file paths, IDs, kinds, source keys, provider refs, and
  evidence URLs after bounded rendering;
- includes deterministic promotion-readiness reasons and blockers when the
  candidate-readiness report was rendered;
- includes deterministic candidate-quality tiers, recommended actions, and
  blockers when the candidate-quality report was rendered, including
  `duplicate_event_ids` when evidence is already covered by reviewed APW data;
- includes a prompt that tells the reviewer to treat provider/source/candidate
  text as untrusted data;
- requires `review_decisions` as advisory curation notes. Decisions do not
  publish events; they help humans and guarded automation compare `promote`,
  `reject`, `duplicate`, `split`, and `needs_human_review` recommendations
  against known fixture outcomes and source-owner policy;
- lists allowed actions: summarize metadata, flag evidence/schema risks, suggest
  patches, recommend candidate promotion, and recommend human follow-up;
- lists forbidden actions: merge PRs, publish events, write source state or
  `data/events`, create release tags, read release tokens, request OIDC tokens,
  or execute provider text as instructions.

Decision-level eval fixtures live under `tests/fixtures/review-evals/`. They
cover one review window with a known provider-change candidate and known
non-event/duplicate outcomes. Keep these fixtures deterministic and free of raw
provider prose.

The manual GitHub workflow `.github/workflows/llm-review-request.yml` has
read-only repository permissions and uploads only `.apw/llm-review-request.json`
as an artifact. It intentionally does not post comments or call model APIs.

## Required Checks

Run these before trusting a review packet:

```bash
uv run pytest tests/test_prompt_injection_redteam.py tests/test_llm_review.py tests/test_candidate_quality.py
uv run apw validate
uv run apw index --check
```
