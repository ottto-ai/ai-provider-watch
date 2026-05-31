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

Validate with:

```bash
uv run apw validate
```
