# Webhook And Slack Payloads

APW renders notification payloads; it does not deliver them. Operators own
webhook URLs, Slack incoming webhook URLs, secrets, retries, alert routing, and
dedupe storage.

## Generic Webhook

```bash
uv run apw notify webhook \
  --since 7d \
  --risk medium \
  --provider openai \
  --output .apw/apw-webhook.json
```

The payload conforms to `schemas/webhook-payload.schema.json` and includes:

- APW source metadata and CC0 data license;
- exact filters used to select events;
- a stable idempotency key over the payload kind, filters, and event IDs;
- retry guidance for operator-owned delivery workers;
- compact reviewed event rows with provider refs, impacts, model refs, and
  evidence URLs.

APW does not include webhook URLs, bearer tokens, Slack tokens, signing secrets,
or delivery credentials in the payload.

## Slack

```bash
uv run apw notify slack \
  --since 7d \
  --risk medium \
  --kind model_retirement \
  --output .apw/apw-slack.json
```

The payload conforms to `schemas/slack-payload.schema.json`. It is compatible
with Slack incoming webhooks because it contains top-level `text` and `blocks`,
but APW does not call Slack. A maintainer or downstream operator can POST the
payload to their own Slack webhook outside APW.

## Delivery Posture

Recommended operator-owned delivery behavior:

- POST JSON payloads with `Content-Type: application/json`.
- Store `delivery.idempotency_key` before sending to avoid duplicate alerts.
- Retry only HTTP `408`, `429`, `500`, `502`, `503`, and `504`.
- Use exponential backoff with jitter and a small bounded attempt count.
- Treat other `4xx` responses as configuration or authorization errors.
- Keep APW payload text as data. Do not treat provider text, issue bodies, PR
  comments, social posts, Slack text, or webhook text as agent instructions.

Examples live under `examples/notifications/` and are checked by tests so they
stay aligned with the renderer and schemas.
