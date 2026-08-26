# blue-green-traffic-switch

**Issue:** Application-level blue-green deployment via traffic switching (ingress / load balancer / service swap) — distinct from database cutover
**Date:** 2026-08-13
**Status:** documented

## Symptom
You deploy a new version of a stateless web service. You take the
old version down to put the new one up. During the swap there is a
30-second window where some users get 502s, and when the new version
turns out to be broken you have no fast way back — you must redeploy
the old version from scratch. Total outage: 12 minutes.

## Root cause
**Taking the old version offline to bring the new one online creates
a gap and destroys your instant-rollback option.** Blue-green keeps
both versions running simultaneously behind a traffic switch, so
cutover is a config change (seconds) and rollback is flipping it
back (seconds).

**Note:** This article covers *application* traffic switching. For
*database* blue-green cutover see `blue-green-database-cutover.md`
and `database-blue-green-migration.md`.

**Source:** Harness — Kubernetes CI/CD Best Practices (blue/green
deployment patterns); Octopus Deploy — 2026 K8s deployment strategies.

## The "two deployments, one switch" pattern

Run `blue` (current) and `green` (new) as two Deployments behind a
single Service whose selector you flip:

```yaml
# blue deployment — the live version
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-blue
spec:
  replicas: 3
  selector:
    matchLabels: { app: api, slot: blue }
  template:
    metadata:
      labels: { app: api, slot: blue }
    spec:
      containers:
        - name: api
          image: registry/core:2.4.1-abc1234
---
# green deployment — the candidate, scaled to 0 until ready
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-green
spec:
  replicas: 0
  selector:
    matchLabels: { app: api, slot: green }
  template:
    metadata:
      labels: { app: api, slot: green }
    spec:
      containers:
        - name: api
          image: registry/core:2.5.0-def5678
---
# the Service routes to whichever slot is selected
apiVersion: v1
kind: Service
metadata:
  name: api
spec:
  selector: { app: api, slot: blue }   # <- the switch
  ports:
    - port: 80
      targetPort: 8080
```

## The "prepare green without dropping traffic" pattern

Scale up green, warm it, and health-check it — all while blue still
serves 100% of traffic:

```bash
# 1. Scale green to full size
kubectl scale deployment/api-green --replicas=3

# 2. Wait for green pods to be Ready AND pass readiness
kubectl rollout status deployment/api-green --timeout=5m

# 3. Smoke-test green directly (a throwaway Service or port-forward)
kubectl port-forward deployment/api-green 8090:8080 &
curl -fsS http://localhost:8090/healthz || exit 1

# Blue is still live the entire time. No user is affected.
```

## The "the switch" pattern

Flip the Service selector. This is the entire cutover — a single
API call, sub-second:

```bash
# Patch the Service selector from blue -> green
kubectl patch service api -p \
  '{"spec":{"selector":{"slot":"green"}}}'

# Confirm traffic now hits green
kubectl get endpoints api -o wide   # should list green pods
```

If anything looks wrong, flip it back:

```bash
# Instant rollback: green -> blue
kubectl patch service api -p \
  '{"spec":{"selector":{"slot":"blue"}}}'
```

Rollback is one command, not a redeploy.

## The "ingress-weighted split" pattern

For a gradual cutover instead of a hard flip, weight traffic at the
ingress (NGINX Ingress example):

```yaml
# 10% to green (canary-style), 90% to blue
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: api
  annotations:
    nginx.ingress.kubernetes.io/canary: "true"
    nginx.ingress.kubernetes.io/canary-weight: "10"
spec:
  rules:
    - host: api.example.com
      http:
        paths:
          - pathType: Prefix
            path: "/"
            backend:
              service:
                name: api-green
                port: { number: 80 }
---
# the main (blue) ingress, unchanged
```

Bump the weight 10 → 50 → 100; at 100, retire blue.

## The "drain before teardown" pattern

When you are done and blue is no longer needed, drain it gracefully
so in-flight requests finish:

```bash
# 1. Stop routing to blue (selector already on green)
# 2. Wait for blue's active connections to drain (connection drain)
kubectl annotate service api \
  nginx.ingress.kubernetes.io/connection-drain="30s" || true

# 3. Scale blue to 0, then delete
kubectl scale deployment/api-blue --replicas=0
kubectl delete deployment/api-blue   # only after a soak period
```

Keep blue around (scaled to 0, not deleted) for the soak period so
rollback is still possible.

## The "stateful workload warning" pattern

Blue-green is for **stateless** services. For stateful workloads
(databases, queues with local state), a traffic switch does not give
you instant rollback because the new version has already mutated
shared state. For those, use:

- `database-blue-green-migration.md` (dual-write + cutover)
- `feature-flag-deploy-coupling.md` (decouple deploy from release)

## Verification
- **Test:** Cutover flips the Service selector and `kubectl get
  endpoints` shows the new slot within 2 seconds.
- **Test:** Rollback (flip back) restores the old slot and traffic
  resumes within 2 seconds.
- **Test:** During cutover, no user-facing request returns 5xx
  (check access logs / error rate).
- **Live:** After cutover, compare green's error rate and p99
  latency against blue's baseline for at least 15 minutes.

## Gotchas
- **The "take old down first" anti-pattern.** Never scale blue to 0
  before green is live. Keep both running through the switch.
- **The "sticky sessions across slots" anti-pattern.** If sessions
  are pinned to blue and you flip to green, users get logged out.
  Use a shared session store or disable affinity during cutover.
- **The "delete blue immediately" anti-pattern.** Keep blue scaled
  to 0 for a soak period (hours to a day) so rollback is still one
  command.
- **The "stateful blue-green" anti-pattern.** A traffic switch does
  not roll back data mutations. Use dual-write cutover for DBs.
- **The "no health check before flip" anti-pattern.** Always warm
  and health-check green before flipping the selector.

## Related
- `blue-green-database-cutover.md`
- `database-blue-green-migration.md`
- `canary-deployments.md`
- `progressive-delivery-2026.md`
- `zero-downtime-deploy-strategies.md`
- `kubernetes-rolling-update.md`
- `feature-flag-deploy-coupling.md`
