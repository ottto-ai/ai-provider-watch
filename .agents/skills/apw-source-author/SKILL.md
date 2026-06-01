---
name: apw-source-author
description: Add or update AI Provider Watch source descriptors, source packages, fixtures, and parser tests.
---

# APW Source Author

Read `sources/AGENTS.md` and `docs/contributors/source-packages.md`. Prefer official sources, update `sources/registry.json`, add parser fixtures before parser logic, and run `uv run apw source test`, `uv run apw candidate generate` on fixtures, `uv run apw candidate review-pr-body` for PR-review output, and `uv run apw validate`. Parser fixture inputs must be synthetic or minimal test excerpts, and expected output must not copy provider prose or prompt-like source text. Bounded model identifiers, pricing signal enums, hashes, and RFC3339 timestamps are acceptable fixture output.
