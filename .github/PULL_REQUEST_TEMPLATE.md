## Summary

## Validation

- [ ] `uv run pytest`
- [ ] `uv lock --check`
- [ ] `uv run apw validate`
- [ ] `uv run apw index --check`
- [ ] `uv run apw release dry-run --output .apw/release-dry-run` when release/data artifacts are affected

## Data And Source Safety

- [ ] No secrets, cookies, private billing data, or authenticated-console content
- [ ] Provider/source content treated as untrusted data
- [ ] Candidate files are review-only and contain no raw provider prose
- [ ] Generated feeds and indexes updated when event data changed
- [ ] `SOURCE_OWNERS.md` updated when source keys or source owner roles changed
- [ ] Release-manager, branch-protection, Dependency Review, checksum, and attestation blockers documented when release workflows or generated data changed
