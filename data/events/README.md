# Reviewed Events

Canonical event JSON files are stored here after maintainer review.

The first seed set is intentionally small: one reviewed official-source event
per initial provider. These records exercise the public feed shape for model
retirements, launches, and token-accounting/caching changes without copying raw
provider prose into the repository.

Data changes require:

- official evidence metadata with source URL, source key, retrieval timestamp,
  and content hash;
- regenerated `data/feeds/`, `data/indexes/`, and `data/releases/` artifacts via
  `apw index`;
- `apw validate` and `apw index --check` before publication.
