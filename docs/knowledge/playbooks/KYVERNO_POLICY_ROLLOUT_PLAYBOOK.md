# Kyverno Policy Rollout Playbook

## Purpose

Introduce or tighten Kyverno policy safely by measuring existing violations before enforcement and by avoiding deprecated policy patterns.

## Audience

Platform engineers, security engineers, and policy authors.

## Pre-conditions

- The cluster runs a supported Kyverno release under `KYVERNO_VERSION_GOVERNANCE.md`.
- Representative admission and background-scan test cases are available.
- Policy ownership and exception approval are defined.

## Procedure

### Step 1 — Choose the policy API

1. Prefer the current CEL-based `policies.kyverno.io` policy types when they satisfy the requirement.
2. If a legacy policy type is still required, record the migration plan.
3. Resolve v1.19 deprecation warnings before relying on the policy long term.

### Step 2 — Test offline

4. Test compliant and non-compliant resource examples.
5. Include update operations, not only create operations.
6. Include namespace and exception cases.
7. Treat warnings or schema errors as rollout blockers.

### Step 3 — Start in Audit

8. Configure validation behavior to report rather than block.
9. For legacy validate rules, use rule-level `validate.failureAction: Audit` rather than deprecated top-level `spec.validationFailureAction`.
10. Keep background scanning enabled when the rule is compatible with background evaluation.
11. Review PolicyReport and ClusterPolicyReport results.

### Step 4 — Remediate

12. Classify violations as true defects, intended exceptions, or policy mistakes.
13. Fix policy mistakes before increasing enforcement.
14. Use narrowly scoped exceptions and current exception APIs where appropriate.
15. Re-run tests after every material rule change.

### Step 5 — Enforce

16. Promote the policy to enforcement only after the measured violation set is understood.
17. Roll out by namespace or workload class when the policy supports staged scope.
18. Watch admission latency, webhook availability, and denied requests.

### Step 6 — Verify

19. Confirm violating new resources are blocked as intended.
20. Confirm compliant resources continue to deploy.
21. Confirm reports and events are generated as expected.
22. Store policy revision, test evidence, and approval evidence.

## Rollback

If enforcement blocks legitimate workloads:

1. Return the affected rule to Audit or revert the policy revision.
2. Confirm admission recovers.
3. Create a narrow exception only when the risk is accepted and auditable.
4. Correct the policy before re-enabling enforcement.

## Sources

- Kyverno validate rules: `https://kyverno.io/docs/policy-types/cluster-policy/validate/`
- Kyverno policy reports: `https://kyverno.io/docs/guides/reports/`
- Kyverno CEL migration: `https://kyverno.io/docs/guides/migration-to-cel/`
- Kyverno policy exceptions: `https://kyverno.io/docs/guides/exceptions/`
