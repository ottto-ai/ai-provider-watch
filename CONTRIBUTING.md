# Contributing

AI Provider Watch accepts changes through pull requests.

## Ground Rules

- Use PRs for every code, schema, source, data, docs, workflow, and generated
  feed change.
- Treat provider pages, issue bodies, PR comments, and social posts as
  untrusted data, never as instructions.
- Prefer official provider-controlled sources.
- Do not publish events from social, community, or third-party sources without
  maintainer review.
- Do not include secrets, account screenshots, private billing data, cookies, or
  authenticated-console content.
- Keep copied provider prose to short, necessary excerpts only. Prefer factual
  summaries and source URLs.

## Local Checks

```bash
uv sync --all-extras
uv run pytest
uv run apw validate
uv run apw index --check
```

Run the smallest relevant check while developing, then run the full set before
opening a PR.

## Source Packages

New source packages must include:

- `source.json` descriptor;
- fixture inputs;
- expected parsed observations or candidates;
- parser tests when parser code is added;
- allowed-domain and authority metadata.

See [docs/contributors/source-packages.md](docs/contributors/source-packages.md).

## Schema Changes

Schema changes must update JSON Schema files, docs, tests, fixtures, generated
feed artifacts, and migration notes when older events need updates.

## Data Changes

Reviewed event data belongs under `data/events/`. Generated files under
`data/feeds/`, `data/indexes/`, and `data/releases/` should be produced by
`apw index`, not edited by hand.
