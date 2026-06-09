# OpenAI Sources

OpenAI pricing, status, news, and deprecation sources. The status Atom parser
hashes entry title/id values and keeps source prose out of parser payloads. The
pricing parser emits bounded pricing/model signals from fixture-proven patterns.
The deprecations lifecycle parser is enabled for deterministic refresh after
synthetic fixtures and a 2026-06-09 live smoke proved the scoped `Deprecations`
heading range still bounds the provider page. It emits bounded model IDs,
lifecycle dates, row hashes, and row-scoped candidate claims without copying
provider prose or publishing events.
