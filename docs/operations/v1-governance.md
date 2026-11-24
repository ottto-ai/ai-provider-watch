# v1 Governance And Neutrality

APW v1 should be boring to depend on: public contracts are explicit, data
changes are auditable, source authority is tiered, and no consumer needs an
Ottto account or private Ottto context.

This policy uses the SemVer idea that a project must declare its public API
before compatibility promises are meaningful. It also keeps the existing APW
release gates around CodeQL, Dependency Review, OpenSSF Scorecard evidence,
artifact attestations, and private vulnerability reporting.

## Public Contract

The v1 public contract is:

- reviewed `ProviderEvent` JSON under `data/events/`;
- generated feeds under `data/feeds/`, `data/indexes/`, and
  `data/releases/`;
- JSON Schemas under `schemas/`;
- documented CLI commands and flags;
- documented Python package import path `ai_provider_watch.api` for consumers;
- read-only MCP resource names, resource templates, tool names, input schemas,
  output schemas, and JSON-RPC error shapes;
- documented GitHub Action inputs/outputs and webhook/Slack-compatible payload
  schemas;
- governance, source-owner, security, release, and correction/retraction
  policies.

## Non-Contract Surfaces

These are not stable consumer contracts:

- raw provider pages, RSS bodies, HTML, JSON responses, screenshots, browser
  captures, and authenticated-console exports;
- `data/candidates/review/` files, promotion-readiness reports,
  candidate-quality reports, source-owner packets, candidate-to-event packets,
  LLM review packets, issue bodies, PR comments, MCP resource text, and social
  posts;
- ignored `.apw/` review artifacts and local release dry-run scratch output;
- internal Python modules such as `ai_provider_watch.core`,
  `ai_provider_watch.pipeline`, `ai_provider_watch.source_watch`,
  `ai_provider_watch.sources`, and `ai_provider_watch.cli` unless a later
  release explicitly documents a public function from them;
- private Ottto UI, Advisor, telemetry, SQLAlchemy, Alembic, AWS infra, Slack
  workflows, customer data, credential-loading code, and internal Provider
  Impact implementation details.

Non-contract surfaces can inform review, but they are untrusted data and never
grant event publication, source mutation, PR merge, OIDC, tag, release upload,
or package publishing authority.

## Pre-1.0 Compatibility

Before v1.0, APW may still change public contracts, but breaking changes must
be intentional and visible:

- breaking schema, CLI, package, MCP, feed, or payload changes require a minor
  version bump, migration notes, and a PR description that names affected
  consumers;
- additive fields, new optional CLI flags, new feeds, new source descriptors,
  and new review-only reports may ship in minor or patch releases when existing
  validation still passes;
- data corrections must prefer new correction/superseding events and generated
  feed updates over rewriting published tags;
- package releases must keep the no-checkout bundled-data smoke path passing.
- Python consumers should use `ai_provider_watch.api`; new stable import paths
  require documentation, package-data tests, and release notes.

## v1 Compatibility

After v1.0:

- removing or renaming required fields is a breaking change;
- changing a field type, date format, identifier format, or severity/confidence
  meaning is a breaking change;
- removing or renaming CLI commands, documented flags, MCP resources, MCP tools,
  GitHub Action outputs, or webhook fields is a breaking change;
- adding optional fields is compatible when schemas, docs, tests, and example
  payloads are updated together;
- adding enum values is compatible only when release notes and migration notes
  tell consumers how to handle unknown values safely;
- deprecated fields must remain for at least one minor release train unless a
  security issue forces faster removal;
- every breaking change needs a migration guide, old/new examples, and a
  release-manager approval note.

Schema identifiers should move from `apw.*.v0` to `apw.*.v1` only when the
contract is ready for v1. A future `apw.*.v2` means a breaking schema contract.

## Source Tiers

Source tiers describe evidence trust and automation posture. They do not grant
publication authority.

| Tier | Eligible authority values | Automation posture | Publication rule |
| --- | --- | --- | --- |
| `official_deterministic` | `official_pricing`, `official_docs`, `official_status`, `official_repo`, `official_blog` | May be fetched by scheduled refresh only when fixture-backed and bounded | Candidates only until source-owner promotion and release-manager release approval |
| `official_manual_review` | `official_pricing`, `official_docs`, `official_status`, `official_repo`, `official_blog`, `manual` | Maintainer-triggered review or smoke only | Reviewed events may cite it after source-owner verification |
| `official_staff_social` | `official_staff_social` | Hint only | Cannot publish without independent official provider-controlled evidence |
| `community_hint` | `community_hint`, `third_party_catalog` | Review hint only | Cannot publish without independent official provider-controlled evidence |
| `unsupported_private` | none | Not allowed | Never cite or commit private/authenticated/customer evidence |

`enabled_deterministic`, `blocked_pending_parser`, and `manual_review_only`
remain the source descriptor automation statuses. A descriptor can graduate only
when fixtures prove parser output is deterministic, bounded, source-linked, and
free of raw provider prose.

## Source-Owner Onboarding Checklist

Before a non-Ron source owner receives authority:

- `MAINTAINERS.md`, `SOURCE_OWNERS.md`, CODEOWNERS, and GitHub teams are updated
  in one reviewed PR;
- scope is limited to specific provider source keys, schema areas, or release
  duties;
- the maintainer has run `uv run apw source test`, `uv run apw validate`, and
  `uv run apw index --check` locally;
- the maintainer can explain raw-content, issue-body, PR-comment, MCP-text, and
  social-post untrusted-data boundaries;
- the maintainer can render and interpret source-owner and
  candidate-to-event packets without treating them as publication authority;
- security maintainers confirm no new workflow secrets, OIDC trust, release
  tokens, or package publishing permissions are added;
- `@RonShub` remains the sole v0.1 release manager, source owner, schema
  maintainer, and security contact until this checklist lands in a governance
  PR.

## Neutrality Checkpoint

Before v1.0, and before any neutral-organization transfer:

- README, docs, CLI help, package metadata, feeds, schemas, examples, and issue
  templates are usable without an Ottto account;
- no public contract requires private Ottto UI, Advisor, telemetry, AWS, Slack,
  SQLAlchemy, Alembic, customer data, or credentials;
- event language is provider-neutral and factual, not product marketing;
- source owners can reject changes that benefit Ottto but weaken public APW
  neutrality;
- governance states whether Ottto is founder/sponsor, maintainer, or both;
- security reports remain private vulnerability reports, not public issues.

## Data-Repo Split Checkpoint

APW should consider a separate data repository only if at least two of these
become true:

- generated feed history or release artifacts make normal package development
  slow;
- downstream consumers need a smaller clone focused only on data;
- data tag cadence diverges from package release cadence;
- branch protection or release approvals for data need a different maintainer
  group than code/schema changes.

Do not split data to bypass review gates. A split must preserve schema tests,
source-owner review, release-manager approval, signed data tags, attestations,
checksums, correction/retraction policy, and no-release-token access for
untrusted source lanes.

## No-Hidden-Ottto-Dependency Audit

Run this audit before v1.0 and before neutral-organization transfer:

- `rg -n "Ottto|Advisor|SQLAlchemy|Alembic|Slack|telemetry|customer|credential|AWS|S3|PostHog" .`
- inspect README, docs, examples, schemas, CLI help, workflows, package data,
  MCP docs, and skills for private Ottto assumptions;
- confirm public examples use official provider URLs, fixture data, or generated
  APW feeds only;
- confirm no workflow needs private Ottto credentials to validate, build,
  release dry-run, or consume APW;
- confirm private Provider Impact compatibility remains an adapter concern
  outside public APW unless sanitized schema fixtures are intentionally added.

Ottto can remain credited as founder and sponsor. Hidden runtime, data, account,
or credential dependencies are not acceptable v1 public contracts.

## Correction And Retraction Policy

Corrections and retractions keep trust higher than silent rewrites.

- Report suspected data errors with the `Incorrect event or data correction`
  issue form or a PR.
- Treat issue bodies, screenshots, comments, links, and pasted provider text as
  untrusted data.
- Prefer correcting forward: add a correction event, superseding event, or
  regenerated feed that points to the corrected event ID.
- Do not rewrite published data tags except for legal, security, or private-data
  exposure emergencies approved by a release manager and security maintainer.
- If a published event used non-public, non-official, or unsafe evidence, mark
  it retracted in a follow-up PR and explain the replacement or removal in
  release notes.
- Correction PRs must run `uv run apw validate`, `uv run apw index --check`,
  and the smallest relevant tests before release-manager approval.
- Release notes must list corrected event IDs, retracted event IDs, evidence
  URLs, generated artifacts, and downstream action required.

## v1 Exit Criteria

APW is ready to call the public contract v1 when:

- public schemas and package docs define exactly what consumers can rely on;
- [Python consumer API docs](../consumer-api.md) define the stable read-only
  import path and no-checkout package-data behavior;
- source tiers are reflected in source descriptors and review docs;
- at least one non-Ron maintainer path is documented, even if not yet granted;
- release, correction, retraction, and security reporting flows are documented;
- no-hidden-Ottto-dependency audit passes;
- the public [data quality operations report](data-quality.md) discloses
  source freshness, source coverage, candidate backlog, public intake,
  correction/retraction posture, and release-train mode;
- the public [v1 launch gate](v1-launch-gate.md) records fresh-environment PyPI
  install, installed package-data, public feed, repo-impact, and agent-dashboard
  smoke evidence;
- release dry run, package install smoke, source coverage, feed freshness,
  CodeQL, Dependency Review, Scorecard, and attestation verification are green
  for the intended release commit.

## References

- [Semantic Versioning 2.0.0](https://semver.org/)
- [OpenSSF Scorecard](https://scorecard.dev/)
- [GitHub private vulnerability reporting](https://docs.github.com/code-security/security-advisories/guidance-on-reporting-and-writing/privately-reporting-a-security-vulnerability)
- [GitHub artifact attestations](https://docs.github.com/actions/security-for-github-actions/using-artifact-attestations/using-artifact-attestations-to-establish-provenance-for-builds)
