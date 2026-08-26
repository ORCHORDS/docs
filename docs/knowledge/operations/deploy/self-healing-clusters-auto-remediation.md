# self-healing-clusters-auto-remediation

**Issue:** Self-healing Kubernetes clusters — automatic detection and remediation of failing nodes, crashed pods, and policy violations without human on-call intervention
**Date:** 2026-08-12
**Status:** documented

## Symptom
A node runs out of disk space, a pod enters CrashLoopBackOff, or a
deployment violates a security policy at 3 AM. Your on-call engineer
gets paged, SSHes in, runs `kubectl delete pod`, and goes back to
sleep. The same failure recurs weekly. MTTR is 20 minutes because a
human must intervene for routine issues a machine could fix.

## Root cause
**No automated remediation.** Kubernetes self-heals *pods* (restarts
them) but does not self-heal *nodes* (draining, cordoning, replacing
failed instances) or *policy violations* (quarantining non-compliant
workloads). A 2026 platform team automates the full remediation
loop.

**Source:** Fairwinds 2026 Kubernetes Playbook — "self-healing
clusters" as a top trend. Tools: Karpenter, Cluster Autoscaler,
Kyverno, OPA Gatekeeper, Litmus Chaos, kube-fledged.

## The "pod self-healing" pattern (built-in)

Kubernetes restarts failed pods automatically. Tune the defaults:

```yaml
spec:
  template:
    spec:
      containers:
        - name: api
          restartPolicy: Always        # default, but be explicit
          livenessProbe:
            httpGet: { path: /healthz, port: 8080 }
            failureThreshold: 3          # restart after 3 failures
            periodSeconds: 10
          # Add a startup probe so slow apps aren't killed
          startupProbe:
            httpGet: { path: /healthz, port: 8080 }
            failureThreshold: 30         # allow up to 5 min startup
            periodSeconds: 10
```

For CrashLoopBackOff, add exponential backoff awareness — if a pod
restarts >5 times in 10 minutes, page a human (it's a code bug, not
a transient failure):

```yaml
# Alertmanager rule
- alert: PodCrashLooping
  expr: rate(kube_pod_container_status_restarts_total[10m]) > 5
  for: 2m
  annotations:
    summary: "{{ $labels.pod }} has restarted {{ $value }} times in 10m"
```

## The "node self-healing" pattern

Use the Cluster Autoscaler or Karpenter + node auto-repair. On
cloud-managed K8s (EKS/GKE/AKS), enable auto-repair:

```bash
# GKE — enable node auto-repair and auto-upgrade
gcloud container node-pools update default-pool \
  --cluster prod \
  --enable-autorepair \
  --enable-autoupgrade

# EKS — use Karpenter (replaces unhealthy nodes automatically)
# karpenter.yaml (helm values)
```

For self-managed clusters, use a remediation controller that
detects unhealthy nodes and cordons + drains them:

```yaml
# system-upgrade-controller — replace unhealthy nodes
apiVersion: upgrade.cattle.io/v1
kind: Plan
metadata:
  name: node-auto-replace
spec:
  nodeSelector:
    matchLabels:
      node-problem: "true"   # set by node-problem-detector
  serviceAccountName: system-upgrade
  cordon: true
  drain:
    force: true
    ignoreDaemonSets: true
  upgrade:
    image: registry.example.com/node-repair:v1
```

Pair with node-problem-detector:
```yaml
# node-problem-detector flags problematic conditions
# that K8s itself does not detect: disk pressure, kernel deadlock,
# file system corruption, Docker daemon hangs
```

## The "policy auto-remediation" pattern

Kyverno can not only *block* non-compliant resources (admission
control) but also *mutate* and *generate* fixes automatically:

```yaml
# Kyverno mutate policy — auto-add resource limits if missing
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: auto-add-resource-limits
spec:
  rules:
    - name: add-default-limits
      match:
        any:
          - resources:
              kinds: [Pod]
      mutate:
        patchStrategicMerge:
          spec:
            containers:
              - (name): "*"
                resources:
                  limits:
                    memory: "512Mi"
                    cpu: "500m"
                  requests:
                    memory: "128Mi"
                    cpu: "100m"
```

Auto-quarantine pods that fail runtime policies:
```yaml
# Kyverno generate — create a NetworkPolicy blocking a bad namespace
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: quarantine-noncompliant
spec:
  rules:
    - name: block-egress
      match:
        any:
          - resources:
              kinds: [Namespace]
              selector:
                matchLabels:
                  compliance-status: "failed"
      generate:
        apiVersion: networking.k8s.io/v1
        kind: NetworkPolicy
        name: default-deny
        data:
          spec:
            podSelector: {}
            policyTypes: [Ingress, Egress]
```

## The "healing loop" — detect, decide, act

```
  ┌─────────┐    ┌──────────┐    ┌────────┐    ┌────────┐
  │ Detect  │───▶│ Decide   │───▶│ Act    │───▶│ Verify │
  │ (probe/ │    │ (policy/ │    │ (mute/ │    │ (probe  │
  │  metric)│    │  rule)   │    │  drain)│    │  passes)│
  └─────────┘    └──────────┘    └────────┘    └────────┘
```

Every remediation must have a verify step. If the action did not
fix the issue, escalate to a human. Never loop infinitely.

## Verification
- **Pod restart works:** `kubectl delete pod <pod>` — pod
  recreates within 30s and passes readiness
- **Node repair works:** SSH into a node, fill the disk
  (`dd if=/dev/zero of=/fill bs=1M count=99999`) — within 5
  minutes the node is cordoned, drained, and replaced
- **Policy mutate works:** deploy a pod with no resource limits —
  `kubectl get pod <pod> -o yaml` shows limits were injected
- **Escalation works:** disable a remediation policy and confirm
  Alertmanager pages a human after the retry threshold

## Gotchas
- **Flapping.** If remediation triggers a restart that fails again
  immediately, you get infinite restart loops. Always set a max
  retry count and an escalation path (CrashLoopBackOff does this for
  pods; you must build it for node-level actions).
- **Drain hangs on PDB-less pods.** PodDisruptionBudgets protect
  quorum, but if a pod has no PDB and a `local` volume, `kubectl
  drain` can hang forever. Always set `--ignore-daemonsets` and a
  timeout.
- **Auto-repair does not equal auto-upgrade.** Auto-repair replaces
  a failed node with the same version. Auto-upgrade changes the
  Kubernetes version — that can break workloads. Enable them
  separately and test upgrades in staging first.
- **Kyverno mutate runs at admission time only.** If a pod was
  created *before* you added the mutate policy, it will not be
  retroactively fixed. Run the policy in `background` scan mode to
  catch existing resources.
- **node-problem-detector conditions are advisory.** By default, K8s
  does not act on custom node conditions (kernel deadlock, FS
  corruption). You must wire them to a remediation controller
  explicitly — the detector only *reports*.
- **Humans must still be in the loop for novel failures.** Auto-
  remediation handles the 80% of known failure modes. The remaining
  20% (novel bugs, security incidents, cascading failures) need a
  human. Design escalation, not elimination of on-call.

## Related
- `kubernetes-readiness-liveness-probes.md`
- `health-check-readiness-patterns.md`
- `kubernetes-horizontal-pod-autoscaler.md`
- `incident-runbook-template.md`
- `mean-time-to-recovery.md`
- `deployment-verification-smoke-tests.md`
- Kyverno: https://kyverno.io/
- node-problem-detector: https://github.com/kubernetes/node-problem-detector
- Karpenter: https://karpenter.sh/
