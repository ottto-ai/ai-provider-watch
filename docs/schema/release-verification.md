# Release Verification Schema

`ReleaseVerificationReport` is the local, read-only verification result for APW
release evidence.

It is produced by:

```bash
apw release verify --dry-run-report .apw/release-dry-run/data-YYYY.MM.DD/dry-run-report.json
```

## Purpose

Use this report before a release manager signs or publishes a data tag. It
verifies local dry-run evidence and optional publication packets without calling
GitHub, PyPI, attestation services, or provider sources.

## Contract

- `schema_version`: `apw.release_verification.v0`.
- `verified`: `true` only when every verification check passed.
- `release_id` and `source_commit`: copied from the dry-run report.
- `dry_run_report_path`: verified dry-run report path.
- `publication_packet_path`: optional packet path.
- `artifacts_root`: artifact directory used for file verification.
- `checks`: pass/fail rows for schema, dry-run checks, artifact files,
  manifest/checksums, expected release/source commit, and packet consistency.
- `verified_artifacts`: artifact paths with recomputed SHA-256 and byte counts.

## Scope

The verifier is intentionally offline. It checks recorded evidence references
and local artifact integrity, but it does not verify GitHub workflow status,
GitHub release existence, PyPI package hashes, or artifact attestations over the
network. Release managers still run the external commands recorded in the
publication packet and release runbook.
