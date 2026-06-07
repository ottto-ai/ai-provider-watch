# OpenAI Sources

OpenAI pricing and status sources. The status Atom parser has synthetic fixture
coverage that hashes entry title/id values and keeps source prose out of parser
payloads. The pricing parser emits bounded pricing/model signals from synthetic
fixture-proven patterns. The deprecations lifecycle parser is disabled for
unattended refresh until a maintainer live-smoke proves the scoped source range,
but its fixtures cover bounded OpenAI model IDs, display model names,
search-preview IDs, and lifecycle dates without copying provider prose.
