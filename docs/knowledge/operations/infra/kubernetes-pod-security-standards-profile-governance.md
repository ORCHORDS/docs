---
title: "Pod Security Standards Profile Governance"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# Pod Security Standards Profile Governance

## API semantics

Pod Security Standards (PSS) are versioned tables, not API objects. `Privileged` imposes no restrictions. `Baseline` rejects known privilege-escalation mechanisms such as `spec.hostNetwork`, `hostPID`, `hostIPC`, privileged containers, `hostPath`, unsafe capabilities, unconfined seccomp, and disallowed sysctls. `Restricted` includes Baseline and additionally constrains volume types, requires `allowPrivilegeEscalation: false`, non-root execution, a non-Unconfined seccomp profile, and dropping `ALL` capabilities; only `NET_BIND_SERVICE` may be added under the current Restricted table. Check the table for the pinned Kubernetes minor because permitted safe sysctls and checked fields evolve. Since v1.25, Linux-only Restricted controls use `spec.os.name`; kubelets before v1.24 do not enforce that field, so mixed old nodes need special care.

## Minimal configuration

```yaml
apiVersion: v1
kind: Pod
metadata: {name: restricted-demo}
spec:
  os: {name: linux}
  securityContext:
    runAsNonRoot: true
    seccompProfile: {type: RuntimeDefault}
  containers:
  - name: app
    image: registry.example/app@sha256:...
    securityContext:
      allowPrivilegeEscalation: false
      capabilities: {drop: ["ALL"]}
    volumeMounts: [{name: cache, mountPath: /cache}]
  volumes: [{name: cache, emptyDir: {}}]
```

## Ordering, versions, and edge cases

Evaluate all pod-bearing templates, including `containers`, `initContainers`, and `ephemeralContainers`; a compliant main container does not rescue a privileged initializer. Pin policy versions during cluster upgrades instead of assuming `latest` is stable. Test Linux and Windows manifests separately. Record every need for host namespaces, host ports, hostPath, privileged mode, extra capabilities, root UID, or local seccomp. Keep infrastructure workloads in narrowly administered namespaces rather than weakening application namespaces.

## Deployment, evidence, and rollback

Use `kubectl apply --dry-run=server -f pod.yaml` against a namespace configured to warn or enforce the target profile. Observe Warning headers and API audit annotations. Roll back a profile change by restoring the previous pinned namespace label, not by applying `privileged` globally; existing pods are not evicted when a profile changes.

Preserve the applied object, server version, server-side dry-run result, relevant events or audit records, and the exact rollback object. Test both acceptance and rejection. Re-run after Kubernetes minor upgrades because API defaults, feature state, and policy tables can change even when manifests still decode.

## Profile migration checklist

Export workload templates and evaluate fields, not just running Pod snapshots. Controllers may retain an old ReplicaSet that passes while the next rollout fails. For Restricted, verify every container sets or inherits a permitted seccomp profile, drops capabilities, cannot escalate privileges, and cannot select UID 0. Inspect projected, secret, configMap, CSI, PVC, emptyDir, downwardAPI, and ephemeral volumes against the current allowed-volume table. Baseline testing should include host ports, proc mount, AppArmor/SELinux options, and newly added probe host fields for the target minor.

Maintain a namespace-to-profile inventory with the pinned PSS minor and the reason Restricted cannot be used. Before advancing from v1.N to v1.N+1, run the newer table in warn/audit mode and group violations by controller owner. Evidence is the normalized PodSpec plus policy-version result; image vulnerability reports are unrelated evidence. A rollback returns the profile version, but any workloads changed to satisfy the new profile need an application rollback test too.

## Sources

- [PSS](https://kubernetes.io/docs/concepts/security/pod-security-standards/)
