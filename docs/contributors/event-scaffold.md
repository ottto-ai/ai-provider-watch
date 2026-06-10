# Event Scaffold

`apw event scaffold` creates a schema-shaped `ProviderEvent` draft from reviewed
official-source facts. It is an authoring shortcut for contributors and source
owners; it does not fetch provider pages, infer facts from prose, regenerate
feeds, promote candidates, publish tags, or read credentials.

Use it when you already verified the official source and want a valid starting
point for `data/events/*.json`:

```bash
apw event scaffold \
  --event-date 2026-06-10 \
  --provider aws-bedrock \
  --kind model_launch \
  --title "AWS Added Claude Fable 5 Availability" \
  --summary "AWS added Claude Fable 5 availability through Bedrock for reviewed routing and cost evaluation." \
  --source-url "https://aws.amazon.com/about-aws/whats-new/2026/06/claude-fable-5-aws/" \
  --source-key aws_bedrock.whats_new \
  --source-authority official_blog \
  --content-sha256 6f01dc703fe5c6c430428b7d45dd52cbe741ce133c188e21570770b459931be5 \
  --scope-ref surface:aws-bedrock/api \
  --impact-kind availability \
  --direction added \
  --severity high \
  --model-ref anthropic/claude-fable-5 \
  --output data/events/2026-06-10-aws-bedrock-claude-fable-5.json
```

If you have a local bounded source snapshot, hash it without copying the source
text into the event:

```bash
apw event scaffold \
  --event-date 2026-06-10 \
  --provider openai \
  --kind api_contract_change \
  --title "OpenAI Changed Responses API Contract" \
  --summary "OpenAI changed a Responses API contract and maintainers need to verify migration impact." \
  --source-url "https://developers.openai.com/api/docs/changelog" \
  --source-key openai.docs \
  --source-authority official_docs \
  --content-text-file .apw/bounded-source-snapshot.txt \
  --scope-ref endpoint:openai/responses \
  --impact-kind migration \
  --direction changed
```

Before opening a PR:

```bash
uv run apw validate
uv run apw index
uv run apw validate
uv run apw index --check
```

Review the generated detail and impact rows before promotion. The scaffold is a
drafting aid, not source-owner approval. Keep provider page bodies, screenshots,
issue comments, social posts, and MCP text as untrusted input.
