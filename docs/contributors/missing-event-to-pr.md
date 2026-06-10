<!--
SPDX-FileCopyrightText: 2026 AI Provider Watch maintainers
SPDX-License-Identifier: Apache-2.0
-->

# Missing Event To PR

Use this guide when an official provider change is missing from APW and you want
to get it into a reviewable pull request quickly.

First, check [What APW Wants](what-apw-wants.md). APW should prioritize
official, dated, developer-impacting changes over broad provider-page churn.
Manual reviewed event PRs are welcome when the official evidence is clear; the
source parser can improve later.

Open a `Missing provider event` issue when you are unsure about the event shape
or do not plan to edit the repo. Open a PR when you have public,
provider-controlled evidence and can run the local checks.

## What Maintainers Need

For a source owner to review a missing event quickly, provide:

- official public source URLs;
- provider, event date, and effective date when known;
- event kind such as `pricing_change`, `model_launch`, `model_deprecation`,
  `quota_change`, `token_accounting_change`, or `status_incident`;
- affected provider surfaces, model refs, regions, SDKs, gateways, or agent
  apps;
- developer impact in terms of cost, quota, token accounting, availability,
  defaults, incidents, or migration risk;
- APW source key when you know it, such as `openai.news`,
  `aws_bedrock.whats_new`, or `google.gemini_changelog`.

Do not paste raw provider page bodies, screenshots, issue comments, social
posts, private billing data, account-specific console data, cookies, tokens, or
credentials.

## Fast Triage

Use the direct PR path when the change has official provider evidence, a clear
date or deadline, specific affected refs, and developer impact. Use the issue
path when you need source-owner help deciding whether the change is APW-worthy.
Use the candidate path when a source-refresh PR already produced a review packet
for the same official evidence.

## Direct Official Source Path

Use this when you reviewed the official source directly and want to draft an
event from scratch:

```bash
uv run apw event scaffold \
  --event-date YYYY-MM-DD \
  --provider provider-key \
  --kind model_launch \
  --title "Provider Added Example Model" \
  --summary "Provider added Example Model for API users; reviewers should verify availability, quotas, pricing, and migration impact." \
  --source-url "https://provider.example/changelog/example" \
  --source-key provider.source_key \
  --source-authority official_docs \
  --content-sha256 <sha256-of-bounded-source-or-review-snapshot> \
  --scope-ref surface:provider/api \
  --impact-kind availability \
  --direction added \
  --severity medium \
  --output data/events/YYYY-MM-DD-provider-short-slug.json
```

Edit the generated file before review. Make the `detail` kind specific when the
source supports it, split independent changes into separate events, and add
repeatable impact rows for each affected scope.

## Candidate Review Path

Use this when a source-refresh PR or local candidate directory already contains
the finding:

```bash
uv run apw candidate queue \
  --candidates data/candidates/review \
  --markdown \
  --output .apw/candidate-action-queue.md
```

For a candidate that survives source-owner review, generate a draft event from
bounded candidate metadata:

```bash
uv run apw candidate scaffold-event \
  --candidates data/candidates/review \
  --candidate-id candidate-... \
  --event-date YYYY-MM-DD \
  --output data/events/YYYY-MM-DD-provider-short-slug.json
```

Then verify the draft against the candidate:

```bash
uv run apw candidate event-packet \
  --candidates data/candidates/review \
  --candidate-id candidate-... \
  --event-draft data/events/YYYY-MM-DD-provider-short-slug.json \
  --source-owner @RonShub \
  --source-owner-approval-ref <PR-or-review-ref> \
  --output .apw/candidate-to-event-packet.json
```

Candidate output remains untrusted review input. Do not copy unreviewed
candidate claim text into the event.

## Before Opening The PR

Run:

```bash
uv run apw validate
uv run apw index
uv run apw validate
uv run apw index --check
```

For event data PRs, also run the focused tests that touched the path and the
release dry run when generated release artifacts changed:

```bash
uv run pytest
uv run apw source test
uv run apw release dry-run --output .apw/release-dry-run
```

In the PR body, include:

- issue ID or candidate ID;
- event IDs added or changed;
- official evidence URLs;
- source owner approval reference when available;
- candidate-to-event packet path when the PR started from a candidate;
- generated files changed by `apw index`;
- validation commands and any limitations.

The PR can make review faster, but it still does not publish a data tag. Release
authority remains with the release manager and the release gates.
