# Cilium Network Policy Rollout Playbook

## Purpose

Roll out a Cilium-backed Kubernetes network policy without unintentionally cutting required workload traffic.

## Audience

Platform engineers, SREs, and security engineers.

## Pre-conditions

- Cilium is healthy on the target cluster.
- The target Cilium release is supported under `CILIUM_VERSION_GOVERNANCE.md`.
- Hubble or equivalent flow visibility is available.
- The workload has an identified owner and rollback contact.

## Procedure

### Step 1 — Baseline traffic

1. Record the namespaces, workloads, services, and ports in scope.
2. Observe normal flows before enforcement.
3. Identify DNS, metrics, health-check, ingress, egress, and control-plane dependencies.
4. Record known cross-namespace and external dependencies.

### Step 2 — Author the policy

5. Prefer the narrowest policy API that satisfies the requirement.
6. Define explicit selectors and required ingress or egress paths.
7. Avoid broad wildcard allowances unless the exception is documented.
8. Validate the manifest with Kubernetes server-side dry-run where supported.

### Step 3 — Stage

9. Apply first to a non-production environment or representative canary namespace.
10. Generate representative workload traffic.
11. Run Cilium connectivity checks appropriate to the environment.
12. Inspect Hubble flows for unexpected drops.

### Step 4 — Promote

13. Apply to a small production slice.
14. Verify service health, DNS resolution, metrics, and dependent calls.
15. Expand only after the observation window is clean.

### Step 5 — Verify

16. Confirm intended disallowed flows are denied.
17. Confirm intended allowed flows remain successful.
18. Save policy revision, test evidence, and relevant flow evidence.

## Rollback

If required traffic is blocked:

1. Revert the policy manifest through the normal configuration workflow.
2. If urgent, remove only the newly introduced policy object.
3. Confirm traffic recovery with service checks and Hubble.
4. Correct the dependency model before reattempting rollout.

## Sources

- Cilium network policy: `https://docs.cilium.io/en/stable/security/policy/`
- Cilium connectivity tests: `https://docs.cilium.io/en/stable/operations/performance/tuning/`
- Hubble: `https://docs.cilium.io/en/stable/gettingstarted/hubble/`
