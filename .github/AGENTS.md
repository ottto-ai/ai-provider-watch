# GitHub Workflow Agent Guide

- Keep default `GITHUB_TOKEN` permissions read-only.
- Do not use `pull_request_target` for workflows that read contributed files
  unless maintainers explicitly approve the risk.
- Do not expose release tokens to jobs that process provider/source content.
- Prefer workflow dispatch or protected-environment gates for release jobs while
  the project is pre-release.
