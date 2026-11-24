# Repository Settings

This runbook records repository settings that cannot be enforced by files alone.
They are required before a public `data-YYYY.MM.DD` release tag.

## Branch Protection Or Ruleset

`main` must be protected by a branch protection rule or repository ruleset.
Required behavior:

- pull requests required before merge;
- required status checks for `test`, `analyze`, and CodeQL code scanning;
- required branch to be up to date before merge;
- force pushes disabled;
- branch deletion disabled;
- during v0.x, zero required approving reviews is allowed only to avoid a
  single-maintainer self-review deadlock while strict required checks remain
  enabled;
- CODEOWNERS review enabled after maintainer teams are configured.

For v0.1, the repository intentionally uses a single-maintainer posture:
`@RonShub` is the explicit CODEOWNER, release manager, source owner, schema
maintainer, and security contact. Team-only CODEOWNERS gates are deferred until
there is a second maintainer or equivalent team structure, because enabling them
too early can lock out the launch maintainer.

Before v1.0 or before adding a second release manager, revisit the review-count
exception and restore at least one required approving review plus CODEOWNERS
review for protected branches.

Check current branch protection:

```bash
export REPO=ottto-ai/ai-provider-watch

gh api "repos/$REPO/branches/main/protection" \
  --jq '{required_status_checks, required_pull_request_reviews, enforce_admins}'
```

Check current repository rulesets:

```bash
gh api "repos/$REPO/rulesets" \
  --jq '.[] | {id, name, target, enforcement, conditions, rules}'
```

If both checks show no active protection for `main`, the release is blocked even
when local dry-run checks pass.

## Security And Dependency Settings

Dependency Review requires dependency graph support. Check repository security
settings before release:

```bash
gh api "repos/$REPO" \
  --jq '{security_and_analysis, delete_branch_on_merge, allow_squash_merge}'
```

Required release posture:

- dependency graph available for Dependency Review;
- Dependabot security updates enabled when available;
- secret scanning enabled when available;
- push protection enabled when available;
- delete branch on merge enabled;
- squash merge allowed.

If an availability or plan limitation prevents a setting, record the limitation
in release evidence before publishing.

## Actions Workflow Permissions

The source-refresh workflow opens draft candidate-review PRs with the default
`GITHUB_TOKEN`. The repository must keep default workflow permissions read-only
and explicitly allow Actions to create pull requests:

```bash
gh api "repos/$REPO/actions/permissions/workflow" \
  --jq '{default_workflow_permissions, can_approve_pull_request_reviews}'
```

Expected release posture:

- `default_workflow_permissions` is `read`;
- `can_approve_pull_request_reviews` is `true`.

GitHub exposes pull-request creation and approval under the same repository
setting. APW workflows do not approve PRs, and untrusted source-refresh jobs must
not receive release tokens, OIDC credentials, or repository secrets.

## Maintainer Teams

Configure these teams or equivalent repository roles:

| Team | Role key | Required for |
| --- | --- | --- |
| `ai-provider-watch-maintainers` | `apw-release-managers` | Release approval, signed tags, final merges. |
| `ai-provider-watch-data-maintainers` | `apw-data-maintainers` | Source owner review, event promotion, generated feeds. |
| `ai-provider-watch-schema` | `apw-schema-maintainers` | Schema compatibility review. |
| `ai-provider-watch-security` | `apw-security` | Security and workflow-token review. |

Until teams exist, `@RonShub` remains the explicit CODEOWNER, release manager,
source owner, schema maintainer, and security contact for v0.1 operations.

## Attestation Verification

The dry-run release workflow uploads `.apw/apw-release-dry-run.tgz` and uses
GitHub artifact attestations to create provenance for that bundle. After
downloading the artifact:

```bash
gh attestation verify .apw/apw-release-dry-run.tgz \
  --repo "$REPO"
```

The attestation proves workflow provenance for the evidence bundle. It is not a
publishing approval; a release manager must still review checksums, release
notes, source commit, and branch/ruleset state.

## Data Release Environment

Create a protected environment named `data-release` before using the guarded
publisher workflow as release evidence. During v0.1, the environment must
require `@RonShub` approval and must not contain secrets while the workflow is
no-op only.

The publisher workflow is intentionally separate from source refresh, candidate
generation, and LLM review workflows. It should run only from trusted `main`
commits and should remain `contents: read` until a signed-tag mechanism is
approved in a follow-up PR.
