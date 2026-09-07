# Kubewarden Policy Server Adoption Playbook

## Purpose

Provide a controlled adoption path for Kubewarden policy enforcement on Kubernetes, covering `PolicyServer` selection, `ClusterAdmissionPolicy` rollout with `privileged` vs `restricted` modes, and safe promotion of WebAssembly (wasm) policies from `monitor` to `protect`.

## Audience

Platform engineers operating the Kubewarden stack, security engineers curating wasm policies, and SREs responsible for cluster reliability.

## Pre-conditions

- Kubewarden version pinned per `docs/knowledge/reference/KUBEWARDEN_VERSION_GOVERNANCE.md` and the helm chart values reviewed.
- A `PolicyServer` CR named for the workload class is defined and reachable; `cert-manager` is healthy.
- Wasm policies are pulled from a verifiable registry and their signatures are validated by `kubewarden-controller`.
- GitOps pipeline can apply `ClusterAdmissionPolicy` and `AdmissionPolicy` manifests idempotently.

## Procedure

1. Add the Kubewarden helm repository and pin the chart version. Install `kubewarden-defaults` and `kubewarden-controller` with the audit scanner and policy-recommender enabled. Verify with `kubectl get policyservers` and `/healthz` on the controller.
2. Use `restricted` (namespaced) `PolicyServer` for tenant workloads. Reserve `privileged` (cluster-wide) for shared platform or infrastructure policies. Confirm matching `securityContext`, resource requests, and TLS source.
3. Apply each `ClusterAdmissionPolicy` (or `AdmissionPolicy`) with `mode: monitor`. Sample audit logs with `kubectl logs -n kubewarden deploy/kubewarden-controller -c policy-server | grep deny`. Use `kwctl` and policy-recommender output to triage violations; do not advance unknown or unowned findings.
4. Flip `mode: protect` for a single policy at a time. Use `failurePolicy: Ignore` initially and switch to `Fail` only once monitor-mode evidence supports it. Limit blast radius with `namespaceSelector` or `objectSelector` for the first 24 hours. Abort if admission p99 exceeds the SLO.
5. To update, bump the `modules` reference (image tag or artifact hash) and let reconciliation reload. To retire, delete the `ClusterAdmissionPolicy` first, then clean unused wasm artifacts. Re-run the recommendation job after every change.

## Rollback

- Set `mode: monitor` (or remove the policy) via GitOps; reconciliation downshifts without a controller restart.
- If a policy corrupts admission, scale the affected `PolicyServer` deployment to zero and investigate offline.
- For wasm crashes, pin to the previous known-good module version and revoke the bad artifact.
- Re-run the audit scanner after rollback and confirm the cluster returns to the prior violation baseline.

## References

- `docs/knowledge/reference/KUBEWARDEN_VERSION_GOVERNANCE.md`
- `docs/knowledge/reference/KUBERNETES_VERSION_GOVERNANCE.md`
- https://docs.kubewarden.io/reference/CRDs#policyserver
- https://docs.kubewarden.io/howtos/operating-policies/05-policy-modes
- https://docs.kubewarden.io/howtos/operating-policies/03-policy-servers/02-policy-servers.html
