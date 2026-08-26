# service-mesh-ambient-sidecar

**Issue:** Deciding between sidecar-based service mesh (classic Istio/Linkerd) and sidecar-less ambient mode — and debugging the mTLS/traffic-policy failures each one introduces
**Date:** 2026-08-13
**Status:** documented

## Symptom / Context
Teams want what a mesh sells: zero-trust mTLS between services, retries/timeouts/traffic splitting, and telemetry without touching app code. What they get instead: every pod carrying a sidecar proxy that adds latency, eats 50-100 MB RAM, breaks on every upgrade (injection, version skew), and makes CPU/thread dumps confusing ("why are there two processes?"). Ambient mode (Istio 1.22+ GA) promises sidecar-less, but brings its own ztunnel/waypoint mental model and failure modes.

## Pattern / Solution
**Pick the lightest thing that delivers the actual requirement:**

| Need | Tool |
|---|---|
| Just mTLS in cluster | Linkerd, or Istio ambient (ztunnel only) |
| mTLS + L7 policy (authz per route, retries, splits) | Istio ambient + waypoint, or sidecar mesh |
| Traffic splitting for canary | Mesh traffic policy, or the gateway + header routing |
| Nothing — one team, 5 services | Kubernetes Gateway API + NetworkPolicies. Do not install a mesh. |

**Ambient mode layout — know the two planes:**
- **ztunnel** (node-level DaemonSet): L4 mTLS, identity, telemetry. Covers every pod in an ambient-enrolled namespace with zero per-pod cost.
- **waypoint proxy** (one per namespace, optional): L7 — HTTP routes, authz, retries, splits. Only traffic to services that need L7 flows through it.

```bash
istioctl install --set profile=ambient
kubectl label ns prod istio.io/dataplane-mode=ambient   # enroll namespace
# L7 policy for one service only:
istioctl waypoint apply --enrolls -n prod --for service payments
```

**mTLS verification (works in sidecar and ambient):**
```bash
istioctl proxy-status                          # all proxies in sync?
istioctl x describe pod api-7d9f8b6c5-xyz      # shows mTLS status + policies applied
# Prove encryption: no plaintext on the wire
kubectl exec -n debug netshoot -- tcpdump -i eth0 -A tcp port 8080 | head
```

**Retries/timeouts at the mesh layer only as a safety net:**
```yaml
apiVersion: networking.istio.io/v1
kind: DestinationRule
metadata: {name: payments}
spec:
  host: payments.prod.svc.cluster.local
  trafficPolicy:
    connectionPool:
      tcp: {maxConnections: 100}
      http: {http1MaxPendingRequests: 50, idleTimeout: 10s}
    outlierDetection:
      consecutive5xxErrors: 5
      interval: 10s
      baseEjectionTime: 30s
```

**Rollout safety (applies to both modes):**
1. Install mesh, enroll one canary namespace, measure p99 before/after for a week
2. Enable mTLS in PERMISSIVE mode first; flip to STRICT only when 100% of peers present client certs
3. Upgrade data plane with revision-based rollouts (istioctl tag) — never in-place across all namespaces at once

## Gotchas
- Ambient is not "free": ztunnel adds a hop on the same node (usually sub-millisecond) and waypoint adds a real network hop for L7. Waypoint-per-namespace means one waypoint's CPU is shared by the whole namespace — size it or throttle it.
- mTLS can mask broken load balancing: if clients cache long-lived connections through ztunnel/waypoint, new pod replicas receive no traffic and you scale into a ghost. Set realistic idle timeouts.
- STRICT mTLS breaks anything non-meshed — cron jobs, operators, external probes, legacy VMs calling into the cluster. PERMISSIVE-first is not optional caution; it is the only migration path that survives.
- Sidecar meshes: proxy concurrency defaults burn CPU on small pods; set `proxyConfig.concurrency` to match container CPU. Also `terminationDrainDuration` too low = 502s during deploys as the proxy dies before in-flight requests finish.
- Application-level retries × mesh-level retries multiply: 2 app retries × 2 mesh retries × timeout skew = retry storm exactly when the dependency is struggling. Own timeouts in exactly one layer (see `outbound-dependency-deadline-and-error-contract.md`).
- EnvoyFilter and other escape hatches are invisible technical debt — they do not show in `istioctl analyze`, break on upgrades, and nobody remembers them. Document every one in the repo, ban them in CI if possible.
- Mesh observability needs explicit sampling decisions: 100% tracing on a 10k-rps cluster via a slow collector becomes a self-inflicted outage. Bound tail-based sampling.
- Linkerd vs Istio: Linkerd is markedly simpler and lighter but Rust-only data plane with fewer L7 knobs; teams needing Envoy-config-level control end up migrating. Decide by feature need, not fashion.
- `NetworkPolicy` still matters — mesh mTLS authenticates identities but does not firewall ports. Both layers, always.

## Related
- `k8s-gateway-api.md`
- `zero-trust-network-access.md`
- `opentelemetry-collector-config.md`
- `outbound-dependency-deadline-and-error-contract.md`
- `network-segmentation-strategy.md`
