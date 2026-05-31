# Event Schema

`ProviderEvent` is the canonical public event envelope.

Required envelope fields:

- `schema_version`
- `id`
- `title`
- `event_kind`
- `lifecycle_status`
- `provider_refs`
- `event_date`
- `observed_at`
- `summary`
- `severity`
- `confidence`
- `source_authority`
- `evidence_refs`
- `impacts`
- `detail`

`detail.kind` selects the typed payload. v0 includes `price_change`,
`quota_change`, `rate_limit_change`, `model_lifecycle`,
`default_model_change`, `token_accounting_change`, `api_contract_change`,
`status_incident`, `subscription_change`, and `generic_change`.

Impact is repeatable, not a paragraph. Each impact row has `scope_type`,
`scope_ref`, `impact_kind`, `direction`, `severity`, and `confidence`.

Every published event needs at least one evidence row with `source_key`, `url`,
`retrieved_at`, `authority`, and `content_sha256`.

## Finding Candidates

`FindingCandidate` is the review-stage shape between `Observation` and
`ProviderEvent`. It is intentionally separate from published data:

- `id` is stable over source key, fingerprint, and normalized claim text;
- `claim_text` is a factual parser claim, not provider instructions;
- `evidence_refs` include source URL, retrieval timestamp, authority, content
  hash, and fingerprint;
- candidate evidence URLs must use `https` and stay inside the source descriptor's
  `allowed_domains`; browser-ambiguous URLs with backslashes or control
  characters and URLs with embedded userinfo are rejected;
- candidate evidence authority must match the referenced source descriptor;
- candidate `provider_refs`, `source_keys`, and evidence source keys must be
  internally consistent;
- candidate fingerprints are compact SHA-256 values; snapshot refs are bounded
  identifiers, not raw source excerpts;
- parser claims cannot persist arbitrary nested payloads or raw source excerpts;
- `review_status` starts as `needs_review`;
- `parser.contract_version` is `apw.candidate_parser.v0`;
- `untrusted_input_policy` records that source content is inert data.

Candidates may be committed for review, but they are not canonical provider
facts until a maintainer promotes them into `data/events/`.

Validate with:

```bash
uv run apw validate
```
