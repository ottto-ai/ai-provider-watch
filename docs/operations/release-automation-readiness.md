# Release Automation Readiness

`apw release automation-readiness` renders the machine-readable decision record
for APW data-release automation. It exists to prevent a passing dry run from
being mistaken for permission to publish unattended `data-YYYY.MM.DD` tags.

```bash
uv run apw release automation-readiness --summary
uv run apw release automation-readiness \
  --created-at 2026-06-10T00:00:00Z \
  --output .apw/release-automation-readiness.json
```

The JSON output conforms to
`schemas/release-automation-readiness.schema.json`.

## Current Decision

For v0.x, real public data publication remains manual:

1. run release gates from the intended `main` commit;
2. render and review the publication packet;
3. verify branch protection, CI, CodeQL, Dependency Review, Scorecard,
   checksums, and artifact attestations;
4. create a release-manager signed `data-YYYY.MM.DD` tag locally;
5. publish the matching GitHub data release with the reviewed evidence packet.

The readiness report therefore returns `status: blocked` while local workflow
guardrails pass. That status is intentional: the remaining blocker is a
signing-equivalence decision, not a failing checkout.

## Why Not Publish From Actions Yet?

GitHub artifact attestations establish workflow provenance for build artifacts.
They are useful evidence for APW dry-run bundles, but they do not replace the
release manager's signed data tag or prove release-manager publication intent by
themselves.

PyPI Trusted Publishing is appropriate for package uploads because PyPI mints a
short-lived token from a configured OIDC identity. APW data tags are different:
the durable public data artifact is a Git tag plus release packet. Before APW
lets a workflow create that artifact, maintainers must approve an equivalent
signature posture and prove the workflow cannot be influenced by untrusted
provider pages, issue bodies, PR comments, MCP resources, social posts, source
observations, candidate generation, or optional LLM review.

## Required Graduation PR

A future PR may add real data publication only after it changes the readiness
report from `blocked` to an approved publication mode and adds tests proving:

- the publisher runs only from trusted `main` commits;
- the `data-release` environment requires release-manager review;
- source refresh, candidate generation, LLM review, Codex review, issue text,
  PR comments, MCP, provider pages, and social/community lanes have no release
  authority;
- downloaded dry-run bundle checksums match `checksums.txt` and the release
  manifest;
- `gh attestation verify` succeeds for the dry-run evidence bundle;
- CI, CodeQL, code scanning, Dependency Review, and OpenSSF Scorecard are green
  for the release commit;
- the selected tag mechanism provides the approved signing-equivalent posture;
- signing keys are never available to workflows that process untrusted content.

Until that PR lands, `data-publisher.yml` is allowed to run no-op and packet
modes only. It must not create data tags, upload GitHub Releases, request OIDC,
or read secrets.

## References

- [GitHub artifact attestations](https://docs.github.com/actions/security-for-github-actions/using-artifact-attestations/using-artifact-attestations-to-establish-provenance-for-builds)
- [GitHub deployment environments](https://docs.github.com/actions/deployment/targeting-different-environments/using-environments-for-deployment)
- [PyPI Trusted Publishing security model](https://docs.pypi.org/trusted-publishers/security-model/)
