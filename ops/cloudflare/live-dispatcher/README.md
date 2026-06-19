# APW Live Dispatcher Worker

Cloudflare Workers Cron wrapper for triggering the APW live publisher outside
GitHub's best-effort schedule queue.

The Worker calls GitHub's repository dispatch API every 15 minutes:

```text
POST /repos/ottto-ai/ai-provider-watch/dispatches
event_type: apw-live-publish
```

The APW workflow that receives this event is
`.github/workflows/live-publisher.yml`.

## Required Secret

Configure one Worker secret:

```bash
npx wrangler secret put GITHUB_DISPATCH_TOKEN --config ops/cloudflare/live-dispatcher/wrangler.toml
```

Use a GitHub fine-grained personal access token or GitHub App installation token
scoped only to `ottto-ai/ai-provider-watch`. It must be able to create repository
dispatch events. Do not use the local `gh` keyring OAuth token or any token with
private Ottto repo access.

## Deploy

```bash
npx wrangler deploy --config ops/cloudflare/live-dispatcher/wrangler.toml
```

After deploy, confirm GitHub receives `repository_dispatch` runs for
`live-publisher.yml`, then verify:

```bash
uv run apw live health --url https://ai-provider-watch.ottto.net/health.json --summary
```

## Behavior

- Scheduled event: dispatches APW live publisher.
- HTTP fetch event: returns a tiny health JSON and does not trigger dispatch.
- Missing token: scheduled run fails, so Cloudflare records the failed invocation
  instead of silently skipping publication.

