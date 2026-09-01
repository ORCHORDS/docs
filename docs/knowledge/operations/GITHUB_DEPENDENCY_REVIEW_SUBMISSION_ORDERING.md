# GitHub Dependency Review and Submission Ordering

## Purpose

GitHub dependency review can include dependencies that are submitted dynamically during a build. When dependency submission and dependency review run independently, the review can execute before the expected dependency snapshot exists and therefore produce an incomplete comparison.

## Current GitHub behavior

GitHub documents that the dependency review API and dependency submission API work together. A dependency submission is a snapshot associated with a commit SHA and metadata such as the detector and correlator. Multiple submission mechanisms can contribute data to the dependency graph, and GitHub applies precedence and deduplication rules when the same manifest is represented more than once.

For workflows that depend on build-time dependency submission, GitHub recommends controlling execution order so submission completes before dependency review consumes the graph state.

## Workflow pattern

### GitHub Actions

Prefer placing dependency-submission actions and the dependency review action in the same workflow when the review depends on those submitted snapshots. Use explicit job dependencies so every relevant submission finishes before review begins.

If dependency review must run separately:

- enable retry behavior for snapshot warnings;
- set the retry timeout long enough to cover the normal runtime of the slowest submission job; and
- treat persistent snapshot warnings as an incomplete-data condition rather than silently passing the review.

### Direct API consumers

When using the APIs directly, submit dependency snapshots first and call dependency review afterward. If independent systems force parallel execution, implement bounded exponential-backoff retry behavior when the dependency-review response indicates missing snapshots.

## Snapshot identity

Use stable, intentional detector and correlator values so independent submission producers remain distinguishable. Do not randomly change correlators on every run unless that is required by the submission design, because correlator identity participates in how GitHub selects the latest relevant submission.

## Governance checks

1. Document which manifests are obtained statically and which require build-time resolution.
2. Identify every job or external system that submits snapshots.
3. Define ordering between submission and pull-request dependency review.
4. Fail or flag the review when required snapshots remain unavailable after bounded retry.
5. Periodically inspect the dependency graph to confirm that expected transitive/build-time dependencies are present.
6. Treat changes to build systems, manifest detectors, or correlators as dependency-graph configuration changes that require verification.

## Failure modes

- Running dependency review before submission can omit build-time dependencies.
- Running submission and review in separate workflows without retry can create race conditions.
- Treating a snapshot-warning response as a clean review can create false confidence.
- Duplicate submissions with inconsistent detector/correlator design can make dependency-graph results difficult to reason about.
- Assuming organization dependency insights contain all manually submitted dependencies can be incorrect; GitHub documents different feature visibility for submitted data.

## Sources

- GitHub Docs — Dependency review: https://docs.github.com/en/code-security/concepts/supply-chain-security/dependency-review
- GitHub Docs — REST API endpoints for dependency submission: https://docs.github.com/en/rest/dependency-graph/dependency-submission
- GitHub Docs — How the dependency graph recognizes dependencies: https://docs.github.com/en/code-security/concepts/supply-chain-security/dependency-graph-data

## Scope note

This article describes GitHub dependency-graph sequencing and completeness controls. It does not replace ecosystem-specific SBOM, lockfile, or package-resolution verification.