# Live Publisher

APW needs two publication modes:

- **Audited repository snapshots** for schemas, source contracts, reviewed event
  history, signed data tags, package data, release evidence, and reproducible
  downstream use.
- **Live public feeds** for fresh provider-change news that can update every
  15 minutes without waiting for a repository commit, package release, signed
  tag, or human review.

The live publisher is the second mode. It should optimize for fast, useful news
flow first, then harden precision over time with evidence scoring, parser
fixtures, agent review, correction loops, and promotion back into audited
snapshots.

## Goal

Every 15 minutes, APW should publish fresh, interesting provider-change material
from official sources to stable public URLs:

```text
https://ai-provider-watch.ottto.net/v1/
https://ai-provider-watch.ottto.net/v1/latest.json
https://ai-provider-watch.ottto.net/v1/events.ndjson
https://ai-provider-watch.ottto.net/v1/feed.json
https://ai-provider-watch.ottto.net/v1/rss.xml
https://ai-provider-watch.ottto.net/v1/atom.xml
https://ai-provider-watch.ottto.net/v1/source-catalog.json
https://ai-provider-watch.ottto.net/v1/health.json
https://ai-provider-watch.ottto.net/v1/provenance.json
```

The bare `/v1` and `/v1/` paths are browser landing pages. Machine consumers
should read the explicit artifact URLs above or use `apw live latest` and
`apw live health`.

For discoverability, the same live artifacts are also mirrored to root-level
aliases such as:

```text
https://ai-provider-watch.ottto.net/latest.json
https://ai-provider-watch.ottto.net/events.ndjson
https://ai-provider-watch.ottto.net/feed.json
https://ai-provider-watch.ottto.net/rss.xml
https://ai-provider-watch.ottto.net/source-catalog.json
https://ai-provider-watch.ottto.net/health.json
```

The `/v1/*` URLs are the canonical versioned API surface. Root aliases are
convenience links for users who naturally try the domain plus artifact name.
The domain root, `https://ai-provider-watch.ottto.net/`, is served by a
Cloudflare URL Rewrite Rule that rewrites only that root path to `/index.html`;
R2's S3-compatible API rejects zero-length object keys, so the publisher cannot
upload a literal empty root object.

Consumers that want current news should read the live URLs. Consumers that need
reproducibility should pin repository `data-*` tags or package snapshots.

## Best-Effort Fetching

The live publisher uses `apw source fetch --allow-source-errors` because a
single official source can temporarily reject, rate-limit, or time out a fetch.
In live mode, that source becomes an inert observation with no candidate claims,
the run continues with the remaining official sources, and `health.json` reports
`status: degraded` plus `source.source_error_count`.

Canonical source-state refreshes do not use this flag. `--allow-source-errors`
is rejected with `--write-state` so transient provider or network errors cannot
overwrite reviewed source fingerprints.

## Non-Goal

The live publisher is not the signed data-release process. It should not create
Git tags, publish Python packages, merge pull requests, require an Ottto account,
or expose private Ottto product surfaces.

The live publisher may publish provisional automated events. That is acceptable:
the explicit goal is high recall and fresh news. Later audited repository
snapshots can correct, supersede, or promote live items.

## Freshness Levels

| Level | Backing store | Update trigger | Consumer use |
| --- | --- | --- | --- |
| Live feed | CDN/object storage or static hosting | Every 15 minutes | Current provider-change news |
| Repository `main` feed | GitHub commits | Reviewed PR merge | Audited latest repository state |
| Data tag | Signed Git tag | Release-manager action | Immutable evidence and reproducibility |
| PyPI package data | Python package release | Package publication | Offline/no-checkout CLI snapshot |

The README and CLI make this distinction explicit. `apw latest` reads package
or checkout data. `apw remote latest --ref main` reads the repository snapshot.
`apw live latest` reads the live feed.

## Publication Bias

The live publisher should be intentionally lenient at the start:

- prefer publishing interesting official-source changes quickly;
- avoid blocking on perfect taxonomy, perfect prose, or perfect multi-source
  confirmation;
- label confidence and source authority clearly;
- keep enough provenance for later correction;
- route ambiguous items to a visible queue instead of hiding them;
- harden gates only after measuring false positives and misses.

This is different from the audited repository path, where durable
`ProviderEvent` records should stay stricter.

## Live Item States

The live feed should support at least these states:

- `automated`: published by deterministic source parser and live gate.
- `agent_reviewed`: published after an agent reviewed sanitized extracted facts.
- `needs_followup`: visible item that is likely interesting but needs later
  cleanup, confirmation, or classification.
- `superseded`: live item replaced by a cleaner later item.
- `promoted`: live item was promoted into audited `data/events/*.json`.
- `retracted`: item should not be used except as correction history.

Consumers should treat `automated`, `agent_reviewed`, and `needs_followup` as
news signals, not immutable facts. They can use confidence, source authority,
and provenance to decide how aggressively to act.

## Lenient Auto-Publish Policy

Start with broad green lanes:

| Source pattern | Default live action | Rationale |
| --- | --- | --- |
| Official status feed/status page incident | Auto-publish | Status news is time-sensitive and source-controlled. |
| Official RSS/news/changelog/release-note entry with date/link | Auto-publish | Interesting provider announcements should flow quickly. |
| Official docs page with scoped parser delta | Auto-publish as `needs_followup` when parser names concrete subjects | Better to surface likely model/API/default changes than miss them. |
| Official pricing page row delta | Auto-publish as `needs_followup` unless parser reports severe ambiguity | Pricing is high-value; later review can correct details. |
| Official model lifecycle row with model/date | Auto-publish | Concrete retirement/deprecation rows are high-signal. |
| Official staff social | Candidate only unless linked to official docs | Useful discovery signal, not primary evidence. |
| Community/social/third-party source | Candidate only | No unattended public facts from community-only evidence. |

The gate should use policy labels instead of hidden judgment:

- `source_authority`: official status, official docs, official pricing,
  official blog, official repo, official staff social, community, third-party.
- `parser_confidence`: high, medium, low.
- `publication_lane`: auto, agent_review, needs_followup, candidate_only.
- `reason_codes`: dated_official_entry, concrete_model_ref,
  pricing_row_delta, lifecycle_date_row, parser_ambiguity, community_only,
  conflicting_sources, duplicate_recent_item.

## Agent Review Lane

APW should run agents continuously, but agents should improve the live feed
rather than block all publication.

Every 15-minute live run:

1. Fetch official sources and build sanitized observations.
2. Generate live candidates.
3. Auto-publish green-lane items immediately.
4. Run a cheap agent review on sanitized extracted facts and metadata.
5. Let the agent improve title, summary, event kind, affected surfaces, and
   migration-risk notes.
6. Publish agent-improved items when schema validation passes.
7. Leave uncertain items as `needs_followup` instead of dropping them.

Daily improvement run:

1. Re-read the last 24 hours of live items.
2. Deduplicate overlapping live items.
3. Promote clear items into audited event PRs.
4. Improve source parsers and fixtures for misses or noisy rows.
5. Open a repo PR with parser/test/source-catalog improvements.
6. Write a public live-quality report with misses, false positives, promoted
   items, retractions, and parser gaps.

The daily agent loop is where APW hardens. The 15-minute loop is where APW
stays fresh.

## Hosting Options

### Option A: GitHub Actions + GitHub Pages

Use a scheduled workflow every 15 minutes, publish static JSON/RSS/Atom files to
GitHub Pages or a Pages branch. Do not commit generated live-feed changes every
15 minutes; publish generated artifacts through the Pages deployment path.

Pros:

- cheapest and fastest v0;
- stays inside the public repository;
- no new cloud account required;
- standard public GitHub-hosted runners are free for public repositories;
- GitHub schedules allow intervals as short as 5 minutes.

Cons:

- schedule events are best-effort and can be delayed or dropped under load;
- scheduled workflows only run on the default branch;
- high-frequency Pages deployments may become noisy;
- Pages has published size, bandwidth, build-time, and rate-limit constraints;
- not a strong SLA surface;
- feed serving and source execution are coupled to GitHub availability.

Use this only as the v0 live publisher if the public URL can be stable and the
health feed clearly reports missed or delayed runs.

For APW-sized compact feeds, this should withstand early load because the files
are small and standard public GitHub-hosted runners are free. It should not be
treated as an always-fresh news SLA. If the feed gets real downstream adoption,
put a CDN/object-store target in front of it or move to a dedicated scheduler.

### Option B: GitHub Actions + Cloudflare R2

Run the 15-minute workflow in GitHub Actions, but publish the output to
Cloudflare R2 behind a public custom domain.

Pros:

- still cheap;
- stable feed URLs;
- no egress fees from R2;
- object storage is a better fit for frequently replaced JSON files;
- repository commits are not needed for every live update.

Cons:

- needs Cloudflare account setup and write credentials/OIDC plan;
- GitHub schedule reliability still applies unless another scheduler triggers
  the workflow;
- secrets must stay out of source-fetch/agent lanes where possible.

This is the preferred low-cost v0 if Cloudflare setup is acceptable.

The APW live workflow also accepts `repository_dispatch` events with type
`apw-live-publish`. If GitHub's native cron proves too sparse for the desired
freshness, run a small external scheduler, such as Cloudflare Workers Cron or a
cloud scheduler, that calls GitHub's repository dispatch API every 15 minutes.
That keeps the public publisher implementation in the OSS repo while moving
timer accuracy out of GitHub's best-effort `schedule` queue.

### Option C: Cloudflare Workers Cron + R2

Run the scheduler and publisher on Cloudflare Workers, store outputs in R2.

Pros:

- purpose-built scheduled execution and public serving;
- Workers Cron is intended for periodic jobs;
- R2 storage and reads are cheap for APW-sized JSON feeds;
- no repository churn;
- can add a small API wrapper later.

Cons:

- Python parser reuse may require packaging work or calling a worker-compatible
  service;
- Workers runtime limits may not fit all source parsing if the parser set grows;
- needs infrastructure ownership and observability.

This is a better durable live service once APW knows the parser/runtime shape.

### Option D: Cloud Run, Lambda, or ECS Scheduled Job + Object Storage

Run the Python package directly in a scheduled container/function and publish to
S3/R2/GCS plus CDN.

Pros:

- best Python compatibility;
- clean separation from repository CI;
- stronger observability, retries, and runtime control;
- easiest path for optional agent-review calls.

Cons:

- higher ops surface;
- cloud billing/account setup;
- more decisions around secrets, OIDC, logs, and cost caps.

This is the best production target if APW becomes a serious public feed product.

## Cost Posture

APW feed artifacts are small. The expensive part should not be storage or
bandwidth; it is source fetching, agent review, and operational attention.

Current v0 assumptions:

- 96 runs/day for a 15-minute cadence.
- Current deterministic source refresh usually completes in under one minute.
- Standard GitHub-hosted runners are free for public repositories.
- The workflow uses standard Ubuntu runners, not larger runners.
- Cloudflare R2 has no internet egress fees and includes monthly free tiers for
  storage, Class A write/list operations, and Class B read operations.
- The workflow uploads dry-run artifacts with `retention-days: 2`.
- No AI model is called by the default live publisher.

Expected direct cost at this cadence is $0/day while APW stays within the
public-repository GitHub Actions and R2 free tiers.

Approximate R2 operation budget:

| Workload | Estimate |
| --- | ---: |
| Scheduled runs | 96/day, about 2,880/30-day month |
| Live objects written per run | 10 artifact files plus `/v1` and `/v1/` landing objects |
| Conservative Class A operations | about 20/run including sync/list overhead |
| Conservative Class A operations/month | about 57,600 |
| R2 Class A free tier | 1,000,000/month |
| Paid equivalent if no free tier applied | about $0.26/month, about $0.009/day |
| Workflow smoke reads | a few hundred Class B reads/day |
| R2 Class B free tier | 10,000,000/month |

Public read traffic is the first cost variable to watch. R2 Class B reads are
currently $0.36 per million after the free tier:

| Public traffic | Rough R2 read cost if APW is the only R2 usage |
| --- | ---: |
| 100,000 reads/day | $0/month, under 10M reads/month |
| 1,000,000 reads/day | about $7.20/month after the 10M free reads |
| 10,000,000 reads/day | about $104/month after the 10M free reads |

Storage should remain negligible because the live publisher replaces a compact
set of feed files in place. The GitHub artifact copy is capped to two days, so
even 96 runs/day should stay far below normal artifact-storage quotas for
APW-sized outputs. If the workflow begins uploading large source snapshots,
increase monitoring before increasing retention.

Future agent review cost depends on model choice and item count. The default
should be a cheap model over sanitized deltas only, with per-run cost caps and a
fallback that still publishes deterministic green-lane official items.

Cost controls:

- cap source fetch byte limits;
- split fast/medium/slow source lanes;
- keep agent review cheap by reviewing sanitized deltas, not raw pages;
- publish compact feeds plus provenance, not raw source bodies;
- alert on unusually high item counts, fetch failures, agent cost, or publish
  size.
- stagger cron schedules away from the top of the hour;
- set workflow concurrency so a slow run does not overlap indefinitely with the
  next 15-minute run;
- expose `health.json` with scheduled time, start time, finish time, run ID,
  source counts, item counts, and last successful publish time.

## Recommended v0 Path

The local dry-run surface now exists:

```bash
apw live build --output .apw/live
apw live gate --input .apw/live --summary
apw live latest --input .apw/live/latest.json --limit 10
apw live health --input .apw/live/health.json --summary
```

The read-only `Live Publisher Dry Run` workflow runs every 15 minutes, builds
`.apw/live`, gates the output, and uploads artifacts. It uses `contents: read`
and does not commit, tag, publish a package, or read release secrets.

The public v0 endpoint is configured at `ai-provider-watch.ottto.net`. Users can
read live artifacts directly:

```bash
apw live latest --base-url https://ai-provider-watch.ottto.net/v1 --limit 10
apw live health --base-url https://ai-provider-watch.ottto.net/v1 --summary
```

The workflow publishes to Cloudflare R2 only when all of this dedicated APW
configuration exists:

- repository secret `APW_R2_ACCOUNT_ID`;
- repository secret `APW_R2_ACCESS_KEY_ID`;
- repository secret `APW_R2_SECRET_ACCESS_KEY`;
- repository variable `APW_R2_BUCKET`, recommended value
  `ai-provider-watch-live`;
- Cloudflare R2 custom domain `ai-provider-watch.ottto.net` connected to the
  bucket.

The publish step syncs `.apw/live` to `s3://$APW_R2_BUCKET/v1/` through R2's
S3-compatible endpoint, writes exact landing objects for `/v1` and `/v1/`, and
mirrors the same compact artifacts to root-level alias keys such as
`latest.json` and `health.json`. It then smokes the public health, landing, and
root alias endpoints. The workflow still has only `contents: read` GitHub
permissions and must not receive release, PyPI, provider, Slack, or private
Ottto credentials.

The Cloudflare zone for `ottto.net` must also have one URL Rewrite Rule:

- name: `AI Provider Watch root landing`;
- match: hostname equals `ai-provider-watch.ottto.net` and URI path equals `/`;
- action: static path rewrite to `/index.html`, query preserved.

Remaining v0 work:

1. Add the daily agent improvement workflow that opens parser, fixture,
   promotion, and quality-report PRs.
2. Add optional agent-review enrichment over sanitized live items.
3. Add live-quality metrics for misses, duplicate/noisy items, retractions, and
   promotions back into the reviewed repository feed.

The first live release may publish more imperfect items than the audited feed.
That is intentional. The core quality metric is whether APW surfaces interesting
official provider changes quickly enough for users and agents to react.

## Daily Improvement Agent

The daily agent should work like an editor and test author, not like a release
manager. It can:

- compare the last 24 hours of live items against official source snapshots;
- identify duplicate, noisy, missed, stale, or misclassified items;
- open PRs that improve parsers, fixtures, source descriptors, and live policy
  reason codes;
- propose audited `ProviderEvent` promotions with evidence refs;
- recommend retractions or superseding items for the next live run;
- publish a public quality report.

It must not merge its own PRs, create signed data tags, publish packages, or use
community/social-only evidence as unattended public facts.

## Quality Metrics

Measure these publicly:

- source run started/completed timestamps;
- source fetch success rate;
- live item count per run and per day;
- auto-published item count;
- agent-improved item count;
- `needs_followup` backlog;
- promoted-to-audited count;
- false positive/retracted count;
- missed official changes found by daily agent review;
- parser fixture coverage by source.

Early target:

- freshness: publish within 15-30 minutes of APW observing an official source
  change;
- recall: prefer surfacing all interesting official changes, even if some are
  `needs_followup`;
- correction: daily agent loop should clean up or promote the previous day.

## Research Notes

- GitHub scheduled workflows support intervals as short as five minutes, but
  schedule events can be delayed or dropped under high load and only run on the
  default branch:
  <https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule>
- GitHub workflow syntax documents `on.schedule` and the five-minute minimum:
  <https://docs.github.com/actions/using-workflows/workflow-syntax-for-github-actions>
- GitHub Actions standard hosted runners are free for public repositories:
  <https://docs.github.com/en/billing/concepts/product-billing/github-actions>
- GitHub Pages is static hosting and has usage limits for site size, deployment
  time, bandwidth, build frequency, and rate limiting:
  <https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits>
- Cloudflare Workers Cron Triggers are designed for periodic jobs:
  <https://developers.cloudflare.com/workers/configuration/cron-triggers/>
- Cloudflare Workers limits and plans should be checked before moving parser
  execution there:
  <https://developers.cloudflare.com/workers/platform/limits/>
- Cloudflare R2 pricing is low for APW-sized object storage and has no internet
  egress fees:
  <https://developers.cloudflare.com/r2/pricing/>
