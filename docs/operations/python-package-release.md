# Python Package Release

APW publishes the `ai-provider-watch` Python package with PyPI Trusted
Publishing. The package exposes the `apw` CLI.

## v0.1 Authority

For the v0.1 launch window, `@RonShub` is the sole package release manager and
PyPI source owner. Revisit this before v1.0 or before adding another PyPI
publisher.

## Trusted Publisher Configuration

Configure PyPI with a pending Trusted Publisher before the first package upload.
No PyPI API token is needed.

| Field | Value |
| --- | --- |
| PyPI project | `ai-provider-watch` |
| GitHub owner | `ottto-ai` |
| GitHub repository | `ai-provider-watch` |
| Workflow filename | `publish-python.yml` |
| Environment | `pypi` |

The GitHub repository must also have an environment named `pypi`. Keep it
protected by a required reviewer during v0.1, with `@RonShub` as the reviewer.
Do not add PyPI credentials, API tokens, or repository secrets for package
publishing.

Official setup references:

- <https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/>
- <https://docs.pypi.org/trusted-publishers/using-a-publisher/>
- <https://docs.pypi.org/attestations/producing-attestations/>
- <https://docs.github.com/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-pypi>

## Workflow Security

`.github/workflows/publish-python.yml` separates build and publish authority:

- `build` runs tests, validation, source fixtures, generated-index checks, and
  package build without `id-token: write`;
- `publish` runs only for refs matching `refs/tags/v*`;
- `publish` uses the protected `pypi` environment;
- only `publish` receives `id-token: write`;
- no workflow runs on `pull_request_target`;
- no release or PyPI token is available to source-refresh, candidate-review,
  LLM-review, or PR-comment workflows.

## First Publish Checklist

1. Verify the package name still returns 404 from
   `https://pypi.org/pypi/ai-provider-watch/json`.
2. Confirm the PyPI pending publisher fields match this document exactly.
3. Confirm GitHub environment `pypi` requires `@RonShub` review.
4. Land the release commit through PR.
5. Create and push a signed package tag such as `v0.1.0a0`.
6. Approve the `pypi` environment deployment.
7. Verify the PyPI project page and file attestations.
8. Run an install smoke in a fresh environment:

```bash
python -m venv /tmp/apw-pypi-smoke
. /tmp/apw-pypi-smoke/bin/activate
python -m pip install --upgrade pip
python -m pip install ai-provider-watch==0.1.0a0
apw --root /path/to/ai-provider-watch validate
```

Keep package release evidence with the tag, workflow run, PyPI file hashes, and
install-smoke output.
