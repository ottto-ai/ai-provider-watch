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
- CODEOWNERS review enabled after maintainer teams are configured.

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

Until teams exist, `@RonShub` remains the explicit CODEOWNER and release
manager.

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
