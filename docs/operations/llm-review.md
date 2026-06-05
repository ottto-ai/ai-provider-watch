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

## Safety Contract

The review packet:

- omits candidate `claim_text` and includes only its length, SHA-256, and
  prompt-like marker flag;
- includes candidate file paths, IDs, kinds, source keys, provider refs, and
  evidence URLs after bounded rendering;
- includes a prompt that tells the reviewer to treat provider/source/candidate
  text as untrusted data;
- requires `review_decisions` as advisory curation notes. Decisions do not
  publish events; they only help humans compare `promote`, `reject`,
  `duplicate`, `split`, and `needs_human_review` recommendations against known
  fixture outcomes;
- lists allowed actions: summarize metadata, flag evidence/schema risks, suggest
  patches, and recommend human follow-up;
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
uv run pytest tests/test_prompt_injection_redteam.py tests/test_llm_review.py
uv run apw validate
uv run apw index --check
```
