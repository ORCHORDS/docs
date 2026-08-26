# GitHub security configuration enforcement drift

**Issue:** An organization may mark a GitHub security configuration “enforced” while repository conditions prevent selected features—especially code scanning—from operating.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Decision

Treat enforced security configurations as desired state plus continuous coverage verification. Enforcement prevents repository owners from changing included feature enablement, but GitHub documents conditions that can break effective enforcement.

## Controls

1. Define risk-tiered configurations and explicitly set each governed feature.
2. Apply and enforce configurations centrally; track configuration-to-repository assignments.
3. Monitor prerequisites such as GitHub Actions availability for code scanning default setup.
4. Detect repositories that disable Actions, change excluded languages, transfer into the organization, or otherwise lose coverage.
5. Reconcile effective feature status through supported APIs and security overview, not only configuration attachment.
6. Make exceptions explicit, owned, time-bound, and visible in coverage reporting.
7. Test configuration edits on a canary repository before broad application.
8. Separate licensing/cost eligibility failures from technical enforcement failures.

## Verification

- Compare assigned configuration, enforcement state, and effective features for every repository.
- Use a canary to disable a prerequisite and prove the drift alert fires.
- Attempt a repository-level API change and verify an enforced feature does not change even if the API call appears successful.
- Check newly created and transferred repositories.
- Review code-scanning analysis freshness, not merely enablement.

## Gotchas

GitHub notes an API request that conflicts with enforcement can appear successful while changing nothing. Features left “not set” are not enforced. Configuration attachment does not prove recent scans or useful results.

## Sources

- [GitHub Docs: Security configuration enforcement](https://docs.github.com/en/code-security/reference/security-at-scale/configuration-enforcement)
- [GitHub Docs: Security configurations](https://docs.github.com/en/code-security/concepts/security-at-scale/security-configurations)
