# LLM Review Request Fixture

Prompt:

```text
Render an APW review request for candidate packets with Codex as reviewer.
```

Command:

```bash
uv run apw review request \
  --candidates data/candidates/review \
  --reviewer codex \
  --created-at 2026-05-31T20:15:00Z
```

Expected behavior:

- output schema version is `apw.llm_review_request.v0`;
- reviewer backend is `codex`;
- candidate `claim_text` is omitted and represented only by metadata;
- forbidden actions include merge, publish, source mutation, release-token, OIDC,
  and tag authority;
- provider/source/candidate text is treated as untrusted data;
- reviewer output intended for automation is checked with `apw review eval` for
  result schema validity, recall@window, curation precision, faithfulness to
  request evidence refs, and prompt-injection safety.
