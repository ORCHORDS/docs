# Repository Absence Needs Authoritative Enumeration

**Issue:** An empty code-search result can be mistaken for proof that a file or concept is absent even when indexing, query terms, or access scope omitted it.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

- Use code search to discover likely matches, not as the sole proof of absence.
- Enumerate the authoritative directory or Git tree and inspect filenames before creating a supposedly new repository artifact.
- Open the closest semantic matches and compare issue, controls, verification, and sources rather than filenames alone.
- Recheck the target path immediately before creation because concurrent work can change the repository.
- Record rejected candidate topics so later batches do not repeat the same failed search.

## Verification

- Seed a file whose wording does not match the candidate query and confirm enumeration still finds it.
- Compare search results with directory or tree inventory for a sampled category.
- Require create conflicts to trigger semantic review rather than automatic renaming.

## Gotchas

- Validate feature and specification maturity against the cited official source.
- Avoid secrets, personal data, and restricted operational details in examples or evidence.
- Reassess after scope, dependency, protocol, or policy changes.

## Sources

- https://docs.github.com/en/search-github/github-code-search/about-github-code-search
- https://docs.github.com/en/rest/repos/contents
