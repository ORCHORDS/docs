# GitHub Dependency-Submission Snapshot Identity

**Issue:** Multiple build tools can submit dependency snapshots for the same repository. Unstable detector identity or correlation values can overwrite, fragment, or stale the dependency graph.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Use stable detector name/version and correlation identifiers per manifest/build context.
- Submit complete resolved relationships for the commit SHA being analyzed.
- Record submission time, job identity, and manifest path without secrets.
- Monitor rejected and stale snapshots and retire obsolete detectors deliberately.

## Verification

- Submit two manifests and two detector contexts without unintended replacement.
- Rebuild the same commit and verify stable identity.
- Submit an invalid or partial snapshot and confirm failure is visible.

## Gotchas

- A successful API response does not prove graph completeness.
- Submitted dependencies are evidence claims and need reproducible provenance.

## Official sources

- https://docs.github.com/en/rest/dependency-graph/dependency-submission
