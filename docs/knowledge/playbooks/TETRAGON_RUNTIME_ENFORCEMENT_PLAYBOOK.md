# Tetragon Runtime Enforcement Rollout Playbook

## Purpose

Bring Cilium Tetragon runtime enforcement into a Kubernetes cluster under the version, kernel, and TracingPolicy constraints in `TETRAGON_VERSION_GOVERNANCE.md` without breaking workloads or generating unenforceable TracingPolicies that silently allow violations.

## Audience

Platform engineers, security engineers, and SREs responsible for runtime enforcement in Kubernetes clusters where Falco-style detection is already in place or where prevention-at-kernel is the primary control.

## Pre-conditions

- The cluster runs a supported Kubernetes release under `KUBERNETES_VERSION_GOVERNANCE.md` and Cilium CNI under `CILIUM_VERSION_GOVERNANCE.md`.
- Tetragon minor is within ±1 minor of the running Cilium minor.
- The node kernel is ≥ 5.8 (x86_64) or ≥ 5.10 (aarch64) with BTF available.
- A tracing-policy owner (team or individual) and an exception-approval workflow are defined.

## Procedure

### Step 1 — Choose the enforcement entry point

- Decide between three entry points: in-cluster TracingPolicy CRDs (most common), `tetragon-cli` (debug/audit only), or the Tetragon gRPC API (custom controllers).
- For production rollouts, use TracingPolicy CRDs exclusively; reserve `tetragon-cli` for one-off incident response.
- Document the entry point in the policy file and reference the `TETRAGON_VERSION_GOVERNANCE.md` minor that introduces the fields used.

### Step 2 — Deploy the Tetragon daemonset

- Install Tetragon via the Cilium Helm chart (preferred) or the Tetragon operator.
- Pin the Tetragon image tag to the minor in `TETRAGON_VERSION_GOVERNANCE.md`; avoid `latest`.
- Validate the eBPF program loads on every node type (control plane, worker, GPU, Arm) before progressing.
- Confirm the TracingPolicy CRD is installed and that the API version matches the Tetragon minor.

### Step 3 — Stage alert-only TracingPolicies

- Begin with `enforcementAction: NONE` for every policy; Tetragon still records events but does not block.
- Subscribe a single observable consumer (Hubble UI, Grafana, Falco sidecar, or a SIEM) and confirm events flow.
- Compare observed events against an expected workload baseline for at least 24 hours before continuing.

### Step 4 — Move to enforcement on non-production

- Promote the highest-confidence policy to `enforcementAction: SIGKILL` on a non-production cluster.
- Run a representative workload (HTTP, gRPC, file I/O, network egress) for at least one full deploy-and-restart cycle.
- Capture false-positive rate, time-to-detect, and time-to-recover; gate production promotion on the agreed SLO.

### Step 5 — Promote to production enforcement

- Promote enforcement policies incrementally per workload class: read-only workloads first, then network-egress workloads, then privileged workloads.
- Maintain a single owner per `enforcementAction` value per workload to prevent conflicting layered enforcement.
- Confirm a runtime override path: a labeled workload or namespace that the policy skips during incident response.

### Step 6 — Verify and document

- Document every active TracingPolicy, its owner, the target workload, the enforcement action, and the rollback command.
- Validate the audit log is reaching the SIEM under `NIST_SP_800_92_LOG_MANAGEMENT_GOVERNANCE.md`.
- Schedule the next policy review at the cadence defined in `TETRAGON_VERSION_GOVERNANCE.md` (≤ 180 days).

## Rollback

- Revert `enforcementAction: SIGKILL` (or other block action) to `NONE` on the affected policy.
- If the eBPF program is unstable on a node, drain the node and roll the Tetragon daemonset back to the previous minor.
- If a policy misfires at scale, remove the TracingPolicy entirely; the workload continues running under the default-allow posture (fail-open).

## References

- `TETRAGON_VERSION_GOVERNANCE.md`
- `CILIUM_VERSION_GOVERNANCE.md`
- `KUBERNETES_VERSION_GOVERNANCE.md`
- `FALCO_RUNTIME_DETECTION_ROLLOUT_PLAYBOOK.md` — for detection-side co-deployment
- `NIST_SP_800_92_LOG_MANAGEMENT_GOVERNANCE.md` — for audit-log retention
