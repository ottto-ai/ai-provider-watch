# Google Sources

Gemini and Vertex AI docs and pricing sources. The model-doc parser has
synthetic fixture coverage for bounded `gemini-*` model identifiers and
table-only default-model signals. The Vertex pricing parser emits bounded
pricing/model/quota signals from synthetic fixture-proven patterns. Quota,
rate-limit, and default-model extraction emits normalized fields and numeric or
model identifiers, not provider prose.

The Vertex model-version lifecycle source is enabled for deterministic daily
refresh. The 2026-06-09 maintainer live smoke followed the official redirect
from `cloud.google.com/vertex-ai/generative-ai/docs/learn/model-versions` to
`docs.cloud.google.com/gemini-enterprise-agent-platform/models/model-versions`,
returned HTTP 200, emitted bounded model/date rows, produced 8 row-scoped
lifecycle candidates, and reported no parser errors. Do not commit raw fetched
provider HTML; use `.apw/` smoke artifacts for review evidence.
