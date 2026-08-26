# chaos-testing-approaches

**Issue:** Testing system resilience by deliberately injecting failures
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Systems that work under normal conditions fail unpredictably when dependencies are unavailable. Chaos testing proactively surfaces these failures.

## Pattern / Solution
Common chaos experiments:
- Kill random instances mid-traffic
- Introduce network latency (100-500ms) to downstream services
- Drop network packets between services
- Fill disk to 95%
- Exhaust connection pool

Using chaos-mesh (Kubernetes):
```yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: add-latency
spec:
  action: delay
  mode: one
  selector:
    namespaces: [production]
    labelSelectors: { app: user-api }
  delay:
    latency: "200ms"
    jitter: "50ms"
  duration: "5m"
```

Using Netflix Chaos Monkey patterns:
- Schedule random instance termination during business hours
- Only in systems with auto-healing (health checks, circuit breakers)

## Gotchas
- Start with game days (planned, monitored chaos) not random
- Define steady-state hypothesis before running experiment
- Always have a kill switch to stop the experiment

## Related
- `stress-testing-patterns.md`
- `end-to-end-test-strategy.md`
