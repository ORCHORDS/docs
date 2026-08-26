# Git fsck skip-list governance

**Problem**

A skip list can suppress known object-integrity findings and become a permanent blind spot if entries lack provenance and expiry.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use only for immutable historical objects that cannot feasibly be rewritten and whose exact defect is understood.

## Controls

- List exact full object IDs with owner, rationale, and expiry review.
- Keep new corruption unsuppressed.
- Protect fsck configuration from workflow writes.

## Implementation

- Validate each object independently before adding.
- Run strict fsck with and without the list in a controlled report.
- Monitor list growth.

## Tests

- Test listed/unlisted corruption, malformed IDs, missing list, alternates, and clones.

## Gotchas

- Skip lists do not repair objects.
- Some defect types are not safely ignorable.
- Rewriting history has wider consequences.

## Official sources

- [Official documentation](https://git-scm.com/docs/git-fsck)
