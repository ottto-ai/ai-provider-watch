# Finding Candidates

Finding candidates are review-only JSON records derived from source
observations. They are not published provider events and must not be consumed as
canonical provider facts.

Generate candidates from an observation bundle:

```bash
uv run apw candidate generate \
  --observations .apw/source-observations.json \
  --output .apw/candidates \
  --created-at 2026-05-31T20:15:00Z
```

Maintainers may copy reviewed candidates into a PR when they need durable review
context. Promotion to `data/events/` requires explicit human review and
`uv run apw validate`.

The scheduled source-refresh workflow writes deterministic generated review
output to `data/candidates/review` when changed official sources produce
candidate claims. That directory is cleaned on each workflow run so stale
candidate files are removed through the next draft review PR. These PRs are not
data releases and must not be merged as event publication without separate
maintainer promotion.

Candidate files must not include raw source bodies, quoted provider prose,
screenshots, or arbitrary nested parser payloads. Keep source material in
external evidence and commit only hashes, URLs, timestamps, and bounded factual
claims. Generation fails on duplicate candidate IDs instead of overwriting
review files. Reruns also fail when a target candidate file already exists; use
`--clean` only for disposable generated directories, not for reviewed candidate
state. Evidence URLs must use `https` and stay inside each source descriptor's
`allowed_domains`; browser-ambiguous URLs with backslashes or control
characters and URLs with embedded userinfo are rejected, and evidence authority
must match the referenced source descriptor. Candidate `provider_refs`,
`source_keys`, and evidence source keys must refer to the same descriptor set.
Evidence metadata is bounded to hashes, compact snapshot references, timestamps,
and URLs.

Render a draft review PR body from observations and candidate files:

```bash
uv run apw candidate review-pr-body \
  --observations .apw/source-observations.json \
  --candidates data/candidates/review \
  --validation-output .apw/candidate-review-validation.txt
```
