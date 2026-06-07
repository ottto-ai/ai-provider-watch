# Azure OpenAI Sources

Azure OpenAI pricing and docs sources. The model catalog source points at
Microsoft Learn and has synthetic fixture coverage for bounded Azure OpenAI
model identifiers. The pricing parser emits bounded pricing/model signals from
synthetic fixture-proven patterns.

The legacy lifecycle source stays disabled because the current Microsoft Learn
URL redirects into a broader Foundry retired-models page. Synthetic fixtures
prove the configured heading-range scope keeps Azure OpenAI rows separate from
neighboring provider sections, but unattended refresh should wait for a
maintainer live smoke against the current page shape.
