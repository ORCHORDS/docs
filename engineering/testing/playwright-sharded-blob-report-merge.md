# Playwright sharded blob report merge governance

**Issue:** A test suite is sharded for speed, but report merging hides incomplete shards, mixes incompatible selections, or produces misleading project-level results.
**Date:** 2026-08-12
**Author:** ORCHORDS
**Status:** documented

## Root cause

Playwright's blob reporter is designed to capture run data for later merged reporting. Shards must be treated as parts of one declared selection: filters affect blob output identity, and merged output still represents separate project instances rather than proof that every intended shard ran.

**Sources:**

- [Playwright test reporters](https://playwright.dev/docs/test-reporters)
- [Playwright Reporter API](https://playwright.dev/docs/api/class-reporter)

## Fix

- define the full test selection, project matrix, shard count, and source revision before starting shards;
- publish one uniquely named blob artifact per shard and retain a machine-readable manifest of expected artifacts;
- fail the workflow when any expected shard, project, or artifact is missing;
- merge only blobs from the same revision, selection/filter set, configuration version, and environment class;
- make the merged report a required post-shard gate, not an informational attachment;
- keep retries and flaky-test classification visible so a green merge cannot hide excessive reruns.

## Verification

- A complete sharded run produces exactly the expected artifact manifest and merged report.
- A missing, stale, or selection-mismatched blob fails the merge gate.
- A focused or filtered test run is labelled as such and cannot masquerade as the full suite.
- The merged report preserves project/shard provenance and retry information.
- A deliberate failing test in a shard blocks the aggregate required check.

## Gotchas

- Sharding improves wall-clock time, not test isolation; shared state still needs isolation controls.
- Do not merge reports across commits or incompatible configuration changes.
- Artifact retention should be sufficient for triage but must not retain secrets, video captures, or personal test data unnecessarily.

## Related

- `testing/playwright-e2e.md`
- `testing/ci-test-parallelization.md`
- `testing/flaky-test-management.md`
