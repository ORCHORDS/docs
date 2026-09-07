# Calico Network Policy Rollout Playbook

## Purpose

Roll out a new Calico `NetworkPolicy` or `GlobalNetworkPolicy` resource across the cluster, progressing from `staged` (log only) through `warn` (advisory event) to `enforce` (drop traffic) without breaking legitimate workloads.

## Audience

Platform engineers operating the Calico CNI, security engineers owning the policy, and SREs responsible for workload reliability.

## Pre-conditions

- Calico >= 3.27 deployed (see Batch 104 reference card `CALICO_VERSION_GOVERNANCE.md`).
- `calicoctl` CLI installed and authenticated to the cluster.
- A dashboard for `calico_denied_packets_total{namespace,policy}` already published.
- Communication channel: `#net-policy-announce` Slack channel for stage transitions.

## Procedure

1. **Author the policy**: write a `NetworkPolicy` (or `GlobalNetworkPolicy` for cluster-wide scope). Validate with `calicoctl apply --dry-run`.
2. **Stage with log only**: set `spec.stagedAction: Log` (or omit `stagedAction` on a `NetworkPolicy` to default to allow). Collect denials in the dashboard for 7 days; identify false positives.
3. **Promote to warn**: set `spec.stagedAction: Warn`. Verify cluster events but no drops.
4. **Promote to enforce**: remove `stagedAction` (defaults to allow) and ensure the policy spec is a deny rule. Capture the timestamp in `policies/calico/CHANGELOG.md`.
5. **Document exemptions**: record any namespace exemptions in `policies/calico/exemptions.md` with the rationale.

## Rollback

- Set `spec.stagedAction: Log` to disable enforcement. Existing workloads are unaffected.
- Delete the policy resource entirely if the rule is no longer needed; pending connections are not impacted.

## References

- Calico docs — https://docs.tigera.io/calico/latest/network-policy/
- Internal reference card: `CALICO_VERSION_GOVERNANCE.md`.
- Staged network policy — https://docs.tigera.io/calico/latest/network-policy/staged-policies/
