# Chaos Engineering and Fault Injection

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your distributed system passes all unit and integration tests but fails
unpredictably in production — network partitions, disk full conditions,
clock skew, and cascading timeouts cause outages that were never tested
for. Post-incident reviews repeatedly find that failure modes were
theoretically known but never validated. You cannot confidently answer
"what happens when service X is unavailable?" because the system has
never been tested under that condition.

## Context

Chaos engineering is the discipline of experimenting on a distributed
system to build confidence in its ability to withstand turbulent
conditions in production. The process follows a scientific method:
define steady state, form a hypothesis, inject a fault, observe the
system, and compare results against the hypothesis. In 2026, LitmusChaos
(graduated CNCF project) and Gremlin are the dominant platforms for
Kubernetes-native and cloud-agnostic chaos experiments. AWS Fault
Injection Service (FIS) provides managed chaos for AWS workloads.
Chaos engineering has matured from "break things randomly" to structured
reliability validation — Gremlin's Reliability Score feature quantifies
system resilience from experimental history.

## The chaos engineering process

```
1. Define steady state
   → Identify measurable indicators of normal behavior
   → Examples: p99 latency < 200ms, error rate < 0.1%, orders/min > 100

2. Form a hypothesis
   → "When database replica fails, the system continues serving reads
      from remaining replicas with no user-visible impact"

3. Design the experiment
   → Target: database replica pod
   → Fault: kill pod
   → Blast radius: single pod in staging
   → Duration: 5 minutes
   → Abort conditions: error rate > 5% or p99 > 2s

4. Run the experiment
   → Inject the fault
   → Monitor steady-state metrics in real time

5. Analyze results
   → Did the system maintain steady state?
   → If not: what failed and why?
   → Document findings, create fix tickets
```

## Fault types

| Category | Fault | Tool support |
|---|---|---|
| **Infrastructure** | Kill pod/container | Litmus, Gremlin, FIS |
| | Kill node/VM | Litmus, Gremlin, FIS |
| | Disk fill | Litmus, Gremlin |
| | CPU/memory stress | Litmus, Gremlin, FIS |
| **Network** | Latency injection | Litmus, Gremlin, Istio |
| | Packet loss | Litmus, Gremlin, tc |
| | DNS failure | Litmus, Gremlin |
| | Network partition | Gremlin, Istio |
| **Application** | HTTP error injection | Istio, Envoy, Gremlin |
| | Slow responses | Istio, Envoy |
| | Exception injection | SDK-based (Chaos Monkey for Spring) |
| **State** | Clock skew | Gremlin, Litmus |
| | Data corruption | Custom scripts |
| | Cache invalidation | Custom scripts |

## LitmusChaos experiment

```yaml
apiVersion: litmuschaos.io/v1alpha1
kind: ChaosEngine
metadata:
  name: pod-kill-experiment
  namespace: production
spec:
  appinfo:
    appns: production
    applabel: app=api-server
    appkind: deployment
  chaosServiceAccount: litmus-admin
  experiments:
    - name: pod-delete
      spec:
        components:
          env:
            - name: TOTAL_CHAOS_DURATION
              value: "300"
            - name: CHAOS_INTERVAL
              value: "30"
            - name: FORCE
              value: "false"
        probe:
          - name: api-health-check
            type: httpProbe
            mode: Continuous
            httpProbe/inputs:
              url: http://api-server.production/health
              method:
                get:
                  criteria: ==
                  responseCode: "200"
            runProperties:
              probeTimeout: 5s
              interval: 5s
              retry: 3
```

## Gremlin experiment

```bash
# Kill a random container in a Kubernetes deployment
gremlin attack container \
  --target-type kubernetes \
  --namespace production \
  --deployment api-server \
  --type shutdown \
  --delay 0

# Inject network latency
gremlin attack network \
  --target-type kubernetes \
  --namespace production \
  --deployment payment-service \
  --type latency \
  --delay 500 \
  --length 300

# CPU stress test
gremlin attack resource \
  --target-type kubernetes \
  --namespace production \
  --deployment worker \
  --type cpu \
  --cores 0 \
  --percent 90 \
  --length 300
```

## Istio fault injection

```yaml
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: payment-service
spec:
  hosts:
    - payment-service
  http:
    - fault:
        delay:
          percentage:
            value: 10
          fixedDelay: 5s
        abort:
          percentage:
            value: 5
          httpStatus: 503
      route:
        - destination:
            host: payment-service
```

## Platform comparison (2026)

| Feature | LitmusChaos | Gremlin | AWS FIS |
|---|---|---|---|
| Type | Open source (CNCF) | Commercial | AWS managed |
| K8s native | Yes (CRDs) | Agent-based | EKS support |
| Cloud support | Any | Any | AWS only |
| Experiment library | 50+ built-in | 20+ attacks | AWS service faults |
| GameDays | Manual | Built-in | Scenarios |
| Reliability score | No | Yes | No |
| Cost | Free | Per-target pricing | Per-action pricing |
| Observability | Prometheus, Grafana | Built-in dashboard | CloudWatch |

## Experiment maturity levels

```
Level 0: No chaos engineering
  → "We hope it works"

Level 1: Manual experiments in staging
  → Ad-hoc pod kills, manual observation
  → Basic understanding of failure modes

Level 2: Automated experiments in staging
  → Scheduled chaos experiments (CI/CD integration)
  → Automated steady-state validation
  → Experiment results tracked and reviewed

Level 3: Automated experiments in production
  → GameDay exercises with controlled blast radius
  → Automated abort on threshold breach
  → Experiment history informs architecture decisions

Level 4: Continuous chaos in production
  → Always-on fault injection at low rates
  → Reliability Score drives engineering priorities
  → Chaos experiments gate production deployments
```

## Anti-patterns

- **Random destruction without a hypothesis** — killing pods randomly
  is not chaos engineering. Every experiment must have a hypothesis
  about expected behavior, measurable steady-state metrics, and abort
  conditions. Without these, you are causing outages, not learning.
- **Chaos in production without staging validation** — running
  experiments directly in production before validating in staging.
  Start in staging, prove the experiment is safe, then graduate to
  production with reduced blast radius.
- **No abort conditions** — running experiments without automatic
  abort thresholds. If an experiment causes unexpected impact, it
  must stop automatically. Define abort conditions before running
  any experiment.
- **Treating chaos as testing** — chaos engineering validates system
  resilience, not functional correctness. It complements but does
  not replace unit, integration, and end-to-end testing.

## Gotchas

- **Blast radius management** — start with the smallest possible
  blast radius (one pod, one node) and expand only after validating
  the system handles smaller failures. A network partition experiment
  across an entire cluster can cause a real outage.
- **Observability prerequisites** — chaos experiments are useless
  without observability. You must have metrics, logging, and tracing
  in place to observe the system's response to faults. Invest in
  observability before chaos engineering.
- **Stateful services** — killing a stateful pod (database, queue)
  has different consequences than killing a stateless pod. Stateful
  chaos experiments require additional safeguards (data backups,
  replication validation).
- **Team communication** — always notify the on-call team before
  running production chaos experiments. Unexpected experiments
  trigger real incident responses, wasting time and eroding trust.

## Verification

- Steady-state metrics are defined for all critical services.
- Chaos experiments run regularly in staging (weekly minimum).
- Production experiments have documented abort conditions.
- Experiment results are reviewed in architecture discussions.
- All critical failure modes (pod kill, network latency, disk full)
  have been validated for key services.
- GameDay exercises run quarterly with cross-team participation.

## Related

- `documentation/categories/testing/load-testing-k6-patterns.md`
- `documentation/categories/monitoring/synthetic-monitoring-uptime-checks.md`
- `documentation/categories/lessons/blameless-postmortem-incident-review.md`

## Source URLs (verified 2026-08-16)

- Chaos Engineering Using Gremlin — https://medium.com/@santhoshjsh/chaos-engineering-using-gremlin-break-things-on-purpose-before-production-does-it-for-you-0baa3d6a6702
- Principles of Chaos Engineering — https://principlesofchaos.org/
- Chaos Engineering: Benefits and Best Practices — https://www.splunk.com/en_us/blog/learn/chaos-engineering.html
- The Discipline of Chaos Engineering (Gremlin) — https://www.gremlin.com/blog/the-discipline-of-chaos-engineering
