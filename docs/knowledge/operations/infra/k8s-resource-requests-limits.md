# k8s-resource-requests-limits

**Issue:** Pods getting OOMKilled, CPU-throttled into latency spikes, or evicted by node pressure — because resource requests/limits were guessed, copied from a blog post, or omitted entirely
**Date:** 2026-08-13
**Status:** documented

## Symptom / Context
Classic triad:
1. `CrashLoopBackOff` with exit code 137 (SIGKILL) — OOMKilled, limit too low
2. P99 latency spikes every few minutes while CPU sits at "only 60%" — CFS throttling, limit too low (60% of what the app sees is the limit, not node capacity)
3. Pods randomly disappear with `Evicted` events — node memory pressure, no requests set so scheduler overcommitted the node

Root cause is almost always: requests were never measured, so the scheduler's bin-packing is fiction.

## Pattern / Solution
**Measure first, then set. Requests are for the scheduler; limits are for containment.**
```bash
# What does this workload actually use? (per-pod, over a representative window)
kubectl top pod -l app=api --containers
# Prometheus: p95 over 7 days is the floor, not the average
sum by (container) (
  rate(container_cpu_usage_seconds_total{pod=~"api-.*", container!="", image!=""}[5m])
)
max by (container) (
  container_memory_working_set_bytes{pod=~"api-.*", container!=""}
)
```

**Sane starting rules:**
- CPU request = p95 usage. CPU limit = 2-4x request (or no limit; see gotchas).
- Memory request = limit = p99 working set + 20-30% headroom. Memory is not compressible; request≠limit only buys you eviction risk.
- JVM/Node/Python runtimes: use working set (`container_memory_working_set_bytes`), not RSS — that is what the OOM killer watches.

```yaml
resources:
  requests:
    cpu: 250m        # p95 measured
    memory: 512Mi    # p99 + headroom
  limits:
    memory: 512Mi    # memory: request == limit (Guaranteed-ish)
    # cpu limit omitted: avoids throttling; node-level protection via
    # LimitRanges / KEDA scaling instead
```

**QoS classes follow from the numbers — know which one you are in:**
- `Guaranteed`: requests == limits (cpu+mem, every container) → last to be evicted
- `Burstable`: anything else → evicted proportional to usage vs request
- `BestEffort`: nothing set → first killed, and (on many clusters) unreleasable under pressure

**Make under/over-provisioning visible and enforced:**
```yaml
# Kyverno: require resources on every container
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: require-resource-requests
spec:
  rules:
    - name: check-resources
      match:
        resources: {kinds: [Pod]}
      validate:
        message: "requests and limits for cpu/memory are required"
        pattern:
          spec:
            containers:
              - resources:
                  requests: {cpu: "?*", memory: "?*"}
                  limits: {memory: "?*"}
```
Also export the requests-vs-usage ratio ( utilization panel: `usage / request`); anything under 10% for a week is wasted quota; anything pegged at 100%+ was a bad guess.

**Vertical right-sizing loop (quarterly):** pull p95/p99 → propose new values via PR → let CI comment the diff on the PR (tools: Goldilocks/VPA in recommendation mode, or a scripted Prometheus query). Never run VPA in `Auto` mode on latency-sensitive pods — it recreates them to apply values.

## Gotchas
- Exit code 137 with memory at limit is the OOM killer; exit 137 with memory under limit is usually liveness-probe timeout or `kubelet` eviction — check `kubectl describe pod` Events and `dmesg` on the node before raising the limit.
- CPU limits throttle in 100 ms CFS periods: an app using only "50%" average can still be throttled hard if it bursts within a period. Check `container_cpu_cfs_throttled_periods_total / container_cpu_cfs_periods_total` before trusting any CPU number.
- The "no CPU limits" advice is sound for latency-sensitive services but requires node headroom discipline; on shared nodes without limits, one misbehaving pod starves neighbors. Pair no-limits with namespace `ResourceQuotas`.
- Java on K8s: the container was OOMKilled because the JVM sized heap off the node, not the limit. Use `-XX:+UseContainerSupport` (default in 11+) and `-XX:MaxRAMPercentage=70` — the other 30% is for metaspace/threads/NIO buffers, which the OOM killer bills you for.
- Requests drive bin-packing: inflating requests "to be safe" fragments the cluster and triggers premature scale-out (cost). This interacts with Karpenter — inflated requests select bigger node types.
- `kubectl top` shows a 15-30 s window; a JVM warming up or a cron burst will mislead you. Always confirm with Prometheus over days.
- DaemonSets and sidecars need requests too — an unrequested istio-proxy/otel sidecar is invisible to the scheduler and the classic source of "node shows 95% allocatable used but pods sum to 60%".
- Eviction order under memory pressure is (QoS, then usage-vs-request). A Burstable pod using 5x its request is killed before a BestEffort pod using 1x — mis-set requests can make you the preferred victim.

## Related
- `karpenter-keda-autoscaling.md`
- `auto-scaling-policies.md`
- `policy-as-code-opa-kyverno.md`
- `golden-path-templates.md`
- `monitoring-sla-slo-sli.md`
