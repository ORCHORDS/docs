---
title: Kyverno Policy Engine Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-06
review-cycle: 180 days
next-review: 2027-03-05
source: Kyverno installation, release, and policy documentation
---

# Kyverno Policy Engine Version Governance

## Scope

This card governs Kyverno version support, Kubernetes compatibility, and policy-API migration decisions.

## Current community support

As of 2026-09-06, Kyverno v1.19 is the supported community minor release. The project documents Kubernetes v1.33 through v1.35 as tested with that release.

Kyverno community patch support is approximately three months and focuses on critical bugs and critical-to-high severity CVEs. Production operators SHOULD track the active release branch and upgrade before community support ends.

## API migration

Kyverno v1.19 emits deprecation warnings for legacy `kyverno.io` policy types. New policy work SHOULD prefer the CEL-based policy APIs in `policies.kyverno.io` where they satisfy the use case.

Important migration points:

- Legacy `ClusterPolicy` is deprecated in v1.19.
- Legacy `PolicyException` in the `kyverno.io` API group is deprecated in v1.19.
- CEL-based `ValidatingPolicy`, `MutatingPolicy`, `GeneratingPolicy`, and `ImageValidatingPolicy` are the forward path.
- Rule-level validation `failureAction` SHOULD be used instead of deprecated top-level `spec.validationFailureAction`.

## Compatibility evidence

Before promotion, record:

1. Kyverno version.
2. Kubernetes server version.
3. Policy API groups and kinds in use.
4. Admission-controller warnings.
5. Background-report health.
6. Results from policy tests against representative resources.

## Upgrade rules

- Review the release page and migration notes before each minor upgrade.
- Resolve deprecation warnings before the removal release.
- Test admission and background behavior separately.
- Verify failure policies and webhook availability during maintenance.
- Re-run policy tests after CRD or API migration.

## Sources

- Kyverno releases: `https://kyverno.io/docs/installation/releases/`
- Validate rules: `https://kyverno.io/docs/policy-types/cluster-policy/validate/`
- CEL migration: `https://kyverno.io/docs/guides/migration-to-cel/`
- Policy exceptions: `https://kyverno.io/docs/guides/exceptions/`
