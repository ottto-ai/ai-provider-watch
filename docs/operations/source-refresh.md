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
3. run `apw validate` and `apw index --check`;
4. render a PR body with observation counts, changed source keys, candidate
   file paths, validation output, and a maintainer checklist;
5. commit only `data/source-state/fingerprints.json` plus sanitized candidate
   JSON.

The PR body intentionally omits provider page bodies and candidate claim text.
Candidate JSON can include bounded factual `claim_text`, but those files are not
published events and require maintainer review before promotion to `data/events`.
Because `data/candidates/review` is generated workflow output, each run replaces
its JSON files instead of preserving stale candidates.

Parser output is intentionally narrow at this stage. Changed official sources
produce generic maintainer-review claims, and Atom status feeds expose hashed
entry metadata instead of copied titles or feed bodies.
