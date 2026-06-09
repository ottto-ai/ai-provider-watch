# Azure OpenAI Sources

Azure OpenAI pricing and docs sources. The model catalog source points at
Microsoft Learn and has synthetic fixture coverage for bounded Azure OpenAI
model identifiers. The pricing parser emits bounded pricing/model signals from
synthetic fixture-proven patterns.

The legacy lifecycle source is enabled for deterministic daily refresh. The
2026-06-09 maintainer live smoke followed the official Microsoft Learn redirect
from `/azure/ai-services/openai/concepts/legacy-models` to
`/azure/foundry/openai/concepts/retired-models`, returned HTTP 200, emitted
bounded model/date rows, produced 8 row-scoped lifecycle candidates, and
reported no parser errors. The configured heading-range scope keeps Azure
OpenAI rows separate from neighboring provider sections. Do not commit raw
fetched provider HTML; use `.apw/` smoke artifacts for review evidence.
