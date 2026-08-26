# OSV alias, range, and withdrawal reconciliation

**Issue:** Vulnerability ingestion creates duplicate issues or false version matches when it treats aliases, upstream records, related records, and version ranges as interchangeable.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Decision

Consume the current stable OSV schema defensively and preserve source records. OSV 1.8.0 defines `aliases`, `upstream`, and `related` with different graph semantics.

## Controls

- Validate `schema_version`; tolerate additive minor/patch fields by ignoring unknown fields while retaining raw input.
- Canonicalize aliases using symmetric/transitive closure, but do not merge `upstream` or `related` as aliases.
- Match ecosystem plus package name/purl before versions.
- Apply SEMVER, ECOSYSTEM, and GIT range ordering using ecosystem-specific logic.
- Interpret `fixed` as exclusive and `last_affected` as inclusive.
- Reconcile `modified` and `withdrawn`; close/suppress only after checking other sources and local evidence.
- Keep source IDs on the canonical issue and update rather than opening duplicates.

## Verification

Build fixtures for multiple disjoint ranges, reintroduction, no-fix ranges, aliases, upstream advisories, withdrawal, and malformed ordering. Compare results with authoritative ecosystem tooling and specific affected/fixed artifacts.

## Gotchas

Alias claims can be corrected. GIT ranges require the commit graph. Distribution advisories that bundle upstream flaws belong in `upstream`, not aliases. `limit` can introduce false negatives; OSV prefers `fixed` where possible.

## Sources

- [OpenSSF OSV schema 1.8.0](https://ossf.github.io/osv-schema/)
