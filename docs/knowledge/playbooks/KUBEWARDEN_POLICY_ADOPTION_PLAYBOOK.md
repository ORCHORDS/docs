# Kubewarden Policy Server Adoption Playbook

## Purpose

Provide a controlled adoption path for Kubewarden policy enforcement on Kubernetes, covering `PolicyServer` selection, `ClusterAdmissionPolicy` rollout with `privileged` vs `restricted` modes, and safe promotion of WebAssembly (wasm) policies from `monitor` to `protect` without disrupting live workloads.

## Audience

Platform engineers operating the Kubewarden stack, security engineers curating wasm policies, and SREs responsible for cluster reliability.

## Pre-conditions

- Kubewarden version pinned per `docs/knowledge/reference/KUBEWARDEN_VERSION_GOVERNANCE.md` and the helm chart values reviewed.
- A `PolicyServer` CR named for the workload class is defined and reachable; `cert-manager` (or the chosen signer) is healthy.
- Wasm policies are pulled from a verifiable registry and their signatures are validated by `kubewarden-controller`.
- GitOps pipeline can apply `ClusterAdmissionPolicy` and `AdmissionPolicy` manifests idempotently.

## Procedure

### Step 1 - Install or upgrade the Kubewarden stack

1. Add the Kubewarden helm repository and pin the chart version.
2. Install `kubewarden-defaults` and `kubewarden-controller` with the audit scanner and policy-recommender enabled.
3. Verify with `kubectl get policyservers` and check `/healthz` on the controller.

### Step 2 — Pick the deployment topology

4. Use `restricted` (namespaced) `PolicyServer` for tenant workloads.
5. Reserve `privileged` (cluster-wide) for shared platform or infrastructure policies.
6. Ensure the chosen `PolicyServer` has matching `securityContext`, resource requests, and TLS source.

### Step 3 — Stage policies in monitor mode

7. Apply each `ClusterAdmissionPolicy` (or `AdmissionPolicy`) with `mode: monitor`.
8. Sample audit logs: `kubectl logs -n kubewarden deploy/kubewarden-controller -c policy-server | grep deny`.
9. Use `kwctl` and policy-recommender output to triage violations; map each to a remediation owner.
10. Do not advance policies with unknown, unowned, or unbounded violations.

### Step 4 — Promote to protect

11. Flip `mode: protect` for a single policy at a time.
12. Use `failurePolicy: Ignore` initially and only switch to `Fail` once monitor-mode evidence supports it.
13. Add `namespaceSelector` or `objectSelector` to limit blast radius during the first 24 hours.
14. Verify admission latency using Kubewarden metrics; abort if p99 exceeds the agreed SLO.

### Step 5 — Update or retire a policy

15. To update, bump the `modules` reference (image tag or artifact hash) and let reconciliation reload the wasm module.
16. To retire, delete the `ClusterAdmissionPolicy` first, then clean up unused wasm artifacts from the registry mirror.
17. Re-run the recommendation job after every change to detect policy drift.

## Rollback

- Set `mode: monitor` (or remove the policy) via GitOps; reconciliation downshifts without a controller restart.
- If a policy corrupts the admission pipeline, scale the affected `PolicyServer` deployment to zero, then investigate offline.
- For wasm crashes, pin to the previous known-good module version and revoke the bad artifact from the local registry mirror.
- Re-run the audit scanner after rollback and confirm the cluster returns to the prior violation baseline before re-promoting.

## References

- `docs/knowledge/reference/KUBEWARDEN_VERSION_GOVERNANCE.md`
- `docs/knowledge/reference/KUBERNETES_VERSION_GOVERNANCE.md`
- https://docs.kubewarden.io/reference/CRDs#policyserver
- https://docs.kubewarden.io/howtos/operating-policies/05-policy-modes
- https://docs.kubewarden.io/howtos/operating-policies/03-policy-servers/02-policy-servers.html
