# Security Policy

Report security issues privately through GitHub Security Advisories when
available. If advisories are unavailable, contact the maintainers listed in
[MAINTAINERS.md](MAINTAINERS.md).

Do not open public issues for active vulnerabilities, leaked secrets, or workflow
abuse paths.

APW is pre-release. Security fixes target the default branch until the first
stable release policy is published.

- Default `GITHUB_TOKEN` permissions should be read-only.
- Avoid `pull_request_target` for jobs that read contributor-controlled files.
- Never expose release tokens to jobs that process scraped or contributed source
  content.
- Treat provider pages, issue bodies, PR comments, and social posts as untrusted
  input.
