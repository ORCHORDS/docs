# Falco Runtime Detection Rollout Playbook

## Purpose

Bring Falco runtime detection into a Kubernetes cluster under the version, driver, and ruleset constraints in `FALCO_VERSION_GOVERNANCE.md` without breaking workloads or generating unsustainable alert volume.

## Audience

Platform engineers, security engineers, and SREs responsible for runtime detection in Kubernetes clusters.

## Pre-conditions

- The cluster runs a supported Kubernetes release under `KUBERNETES_VERSION_GOVERNANCE.md`.
- Falco release and ruleset versions are pinned to a supported minor under `FALCO_VERSION_GOVERNANCE.md`.
- The destination SIEM is reachable from the cluster and has a documented ingest schema.
- Policy ownership and exception approval are defined.

## Procedure

### Step 1 — Choose the driver

1. Default to the modern eBPF probe on kernels ≥ 5.8 with BTF enabled.
2. Fall back to the kernel module only when running on kernels without BTF or with restricted eBPF.
3. Avoid the ptrace user-space driver in production; reserve for air-gapped debugging.
4. Document the driver selection and the supported kernel matrix.

### Step 2 — Deploy the daemonset

5. Pin the Falco image tag to the supported minor.
6. Pin the ruleset repository to a SHA tag.
7. Configure resources requests and limits to the documented SLO.
8. Configure the health endpoint and liveness/readiness probes per the release notes.

### Step 3 — Stage alert output

9. Configure Falcosidekick to forward to the SIEM, to a ticketing system, and to a local pager for severity-paged alerts.
10. Tune the output format to match the SIEM ingest schema; record the schema mapping.
11. Configure a fallback output path in case the SIEM is unreachable.

### Step 4 — Roll out in audit mode

12. Start in audit mode; collect, but do not page on, detection output.
13. Run for at least one full business cycle (typically two weeks) to capture the baseline.
14. Triage output for high-volume low-value rules and either suppress or tune them.

### Step 5 — Promote to enforced mode

15. Switch the policy from audit to enforced for the tuned rule set.
16. Wire paging and on-call rotation.
17. Capture a baseline of expected alert volume and time-to-acknowledge.

### Step 6 — Verify and operate

18. Confirm that violations of enforced rules are paged and that compliant workloads continue to run.
19. Confirm that ruleset updates are pulled via CI and not at runtime unless the runtime supports out-of-band rules update with audit.
20. Capture a recent driver kernel compatibility report and the most recent ruleset update record.

## Rollback

- Revert the daemonset to the previous Falco minor.
- Switch the policy back to audit mode.
- Capture a roll-forward plan for the next attempt and record the failure mode.

References: `FALCO_VERSION_GOVERNANCE.md`, `KUBERNETES_VERSION_GOVERNANCE.md`, `KYVERNO_POLICY_ROLLOUT_PLAYBOOK.md`.
