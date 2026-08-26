# Kubernetes Network Policies and Service Mesh Security — Zero-Trust Pod Networking

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your Kubernetes cluster runs 40 microservices across 3 namespaces. A
compromised pod in the `staging` namespace can reach every pod in the
`production` namespace because Kubernetes allows all pod-to-pod traffic
by default. A penetration test demonstrates lateral movement from a
vulnerable web frontend to the production database in under 2 minutes.
Your team applies a NetworkPolicy but forgets to allow DNS — every pod
in the namespace loses name resolution and the entire application goes
down.

## Context

Kubernetes allows unrestricted pod-to-pod communication by default.
NetworkPolicy resources act as namespace-scoped firewalls, but
Kubernetes itself does not enforce them — enforcement depends entirely
on the CNI plugin (Calico, Cilium, Weave Net, Antrea). Flannel does
not implement NetworkPolicy at all. In 2026, zero-trust pod networking
combines NetworkPolicy for L3/L4 segmentation with service mesh
(Istio, Linkerd) for mTLS and L7 authorization. CNCF surveys report
47% of organizations running Kubernetes in production have adopted a
service mesh, up from 28% in 2023.

## Default deny foundation

```yaml
# Deny all ingress and egress — zero-trust baseline
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: production
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
  ingress: []
  egress: []
```

```yaml
# CRITICAL: always allow DNS or everything breaks
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-dns
  namespace: production
spec:
  podSelector: {}
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
```

## Microsegmentation pattern

```yaml
# Tiered: frontend → backend → database
# Only frontend can reach backend
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: backend-ingress
  namespace: production
spec:
  podSelector:
    matchLabels:
      tier: backend
  policyTypes:
    - Ingress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              tier: frontend
      ports:
        - protocol: TCP
          port: 8080

---
# Only backend can reach database
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: db-ingress
  namespace: production
spec:
  podSelector:
    matchLabels:
      app: postgres
      tier: database
  policyTypes:
    - Ingress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              tier: backend
              access-db: "true"
      ports:
        - protocol: TCP
          port: 5432
```

## Selector logic: AND vs OR

```yaml
# AND — both must match (single list item, both selectors)
- from:
  - namespaceSelector:
      matchLabels:
        env: production
    podSelector:
      matchLabels:
        app: frontend

# OR — either can match (separate list items)
- from:
  - namespaceSelector:
      matchLabels:
        env: production
  - podSelector:
      matchLabels:
        app: frontend

# The difference is a single '-' vs two '-' items
# Misunderstanding this is the #2 most common NetworkPolicy bug
```

## CNI comparison: Calico vs Cilium

```
                    Cilium                  Calico
──────────────────────────────────────────────────────────────
Data plane:         eBPF-only               iptables/nftables/eBPF
Rule lookup:        O(1) hash tables        O(n) iptables, O(1) eBPF
L7 policies:        Native (HTTP/gRPC)      Enterprise only
FQDN egress:        DNS proxy               Native integration
Min kernel:         4.19.57                 Any (iptables mode)
Windows:            No                      Yes
Observability:      Hubble (built-in)       Prometheus export

Performance (2026 benchmarks):
  Pod-to-Pod:       ~9.2 Gbps               ~8.5 Gbps
  Pod-to-Service:   ~28.5 Gbps              ~22.1 Gbps
  P50 latency:      ~0.20 ms                ~0.25 ms
  Policy eval:      0.1-0.2 ms              0.3-0.8 ms (iptables)

Choose Cilium:  Greenfield, GKE/AKS, 500+ services, L7 needed
Choose Calico:  Mixed Windows/Linux, BGP infra, older kernels
```

## mTLS with service mesh

```yaml
# Istio — strict mTLS enforcement
apiVersion: security.istio.io/v1beta1
kind: PeerAuthentication
metadata:
  name: strict-mtls
  namespace: production
spec:
  mtls:
    mode: STRICT
```

```yaml
# Istio — L7 authorization policy
apiVersion: security.istio.io/v1beta1
kind: AuthorizationPolicy
metadata:
  name: restrict-access
  namespace: default
spec:
  selector:
    matchLabels:
      app: my-service
  rules:
    - from:
        - source:
            principals:
              - "cluster.local/ns/default/sa/my-service-account"
      to:
        - operation:
            paths: ["/api/v1/data"]
```

```
mTLS latency overhead (2026 benchmarks):
  Istio (Envoy sidecar):     ~2.5 ms median per hop
  Linkerd (Rust proxy):      ~1.1 ms per hop
  Cilium (eBPF data plane):  <0.5 ms per hop

Istio Ambient Mode (1.29+): eliminates sidecars via CNI interception
  Throughput: 99.2% vs 95.8% sidecar mode
  CPU usage:  1.5% vs 3.2% sidecar mode
```

## Anti-patterns

- **Using Flannel and expecting enforcement** — Flannel does not
  implement NetworkPolicy. Policies are accepted by the API server
  but never enforced. Pods communicate freely.
- **Omitting `policyTypes`** — without explicit `policyTypes: [Ingress,
  Egress]`, egress defaults to allow-all, enabling data exfiltration
  even with ingress locked down.
- **Overly broad CIDR rules** — `/8` or `/16` egress rules defeat
  the purpose of microsegmentation. Restrict to specific IP ranges.
- **Not testing policies before production** — deploy to a test
  namespace first. Use `nicolaka/netshoot:latest` pods to verify
  connectivity.

## Gotchas

- **Blocking DNS is the #1 mistake** — always include a DNS allow
  rule in every deny-all policy. Without it, every pod loses name
  resolution.
- **FQDN-based egress not supported natively** — standard
  NetworkPolicy uses IP blocks, not domain names. For FQDN rules,
  use CiliumNetworkPolicy with `toFQDNs` or Calico Enterprise.
- **Cross-namespace policies require namespace labels** — the target
  namespace must be labeled for `namespaceSelector` to match. Run
  `kubectl label namespace production name=production`.
- **NetworkPolicy is additive** — there is no deny rule. Policies
  only whitelist traffic. Multiple policies on the same pod combine
  their allowed connections (union).
- **Istio Ambient Mode limitations** — supports multicluster in beta
  but not all L7 features are available without waypoint proxies.

## Verification

- Default deny policy exists in every namespace.
- DNS egress is explicitly allowed in all deny-all policies.
- Microsegmentation follows tiered architecture (frontend/backend/db).
- CNI plugin supports and enforces NetworkPolicy (not Flannel).
- mTLS is in STRICT mode across production namespaces.
- Policies are tested in staging before production deployment.

## Related

- `documentation/docs/policies/infra/terraform-state-management-remote-backend.md`
- `documentation/docs/policies/infra/kubernetes-autoscaling-hpa-keda.md`
- `documentation/docs/policies/security/supply-chain-security-slsa-sigstore.md`

## Source URLs (verified 2026-08-16)

- Cilium vs Calico: We Run Both in Production (2026) — https://tasrieit.com/blog/cilium-vs-calico-cni-comparison-2026
- Kubernetes Network Policies Security Implementation Guide 2025 — https://atmosly.com/blog/kubernetes-network-policies-security-implementation-guide-2025
- Cloud-Native Security: Zero Trust in Kubernetes and Istio — https://dasroot.net/posts/2026/03/cloud-native-security-zero-trust-kubernetes-istio/
- Kubernetes Network Policy Microsegmentation Guide — https://www.decryptiondigest.com/blog/kubernetes-network-policy-microsegmentation-guide
