# GitHub dependency review enforcement

**Issue:** Vulnerable or disallowed dependencies can be introduced by a pull request unless dependency changes are inspected and enforced before merge.
**Date:** 2026-08-26
**Status:** documented

## Sources

- GitHub Docs — Customizing dependency review action configuration: https://docs.github.com/en/code-security/tutorials/secure-your-dependencies/customize-dependency-review-action
- GitHub Docs — Reviewing dependency changes in a pull request: https://docs.github.com/en/pull-requests/how-tos/review-pull-requests/reviewing-dependency-changes-in-a-pull-request

## Current behavior

GitHub's dependency review shows dependency additions, removals, and updates in pull requests and includes vulnerability information. The dependency review action can fail a workflow when a pull request introduces a dependency that violates configured vulnerability or license policy.

GitHub's current examples use `actions/dependency-review-action@v4`. The action can be configured with controls such as `fail-on-severity`, license allow/deny lists, and dependency scopes.

## Enforcement pattern

1. Enable the dependency graph for the repository.
2. Run dependency review on pull requests that can modify dependency manifests or lockfiles.
3. Configure an explicit severity threshold appropriate to the repository's risk tolerance.
4. Add license policy only when the organization's license rules are documented and reviewed.
5. Make the dependency-review check required if the goal is to block noncompliant changes from merging.
6. Review workflow-action dependencies too; workflow changes can introduce third-party code into CI.

## Important limitation

A dependency review check that is not required is advisory only. A successful enforcement design must connect the check result to the repository's merge policy.

## Verification checklist

- Introduce a test pull request with a known policy violation in a disposable branch/repository fixture.
- Confirm the dependency review workflow detects it.
- Confirm the repository rules prevent merge when the required check fails.
- Confirm allowed dependency updates continue to pass.

## Related

- `github-artifact-attestations.md`
- `github-immutable-releases.md`
