---
title: "HashiCorp Consul Service Mesh Version Governance"
owner: "Knowledge Engineering"
status: "approved"
classification: "public"
last-reviewed: "2026-09-08"
review-cycle: "180 days"
next-review: "2027-03-07"
source: "HashiCorp Consul documentation, Connect service mesh, and Consul release notes"
---

# HashiCorp Consul Service Mesh Version Governance

## Service Mesh and Sidecar
Consul service mesh (formerly Consul Connect) places a transparent Envoy sidecar next to every registered service. Envoy runs in transparent mode, so existing applications require no code changes. Consul coordinates x509 certificates and configuration via its control plane; data-plane traffic flows directly between proxies.

## Mutual TLS and SPIFFE
Mesh traffic is encrypted with mTLS. Each workload receives a short-lived x509 SVID from the Consul CA, encoding a SPIFFE identity such as `spiffe://<trust-domain>/ns/<namespace>/dc/<datacenter>/svc/<service>`. The identity drives downstream authorization.

## Intentions
Intentions are Consul's declarative policy. L4 rules match source and destination services. L7 rules add method, path, and header matching and require an ingress or terminating gateway. Default-deny is the recommended baseline.

## Cluster Peering
Peering links datacenters across administrative boundaries without merging gossip pools or sharing ACL tokens. Peers are allow-listed; intentions reference exported service names.

## Admin Partitions
Admin partitions deliver hard multi-tenancy behind dedicated Consul servers, with independent ACL policies and replication boundaries. This is an Enterprise feature.

## Sampled Telemetry
Traces are sampled through `proxy-defaults.envoy_tracing_*` and exported to OpenTelemetry-compatible collectors, keeping overhead bounded.

## Deployment Surfaces
The mesh runs on VMs, Kubernetes via Consul on K8s, and AWS ECS via task definition sidecars. Control plane and proxy are identical across surfaces.

## Connect-Native and Gateways
Connect-native apps embed the Consul API and negotiate mTLS directly. Ingress gateways accept external traffic; terminating gateways expose non-mesh backends as mesh destinations.

## License Tiers
Open source covers core, intentions, peering (since 1.14), mesh, and gateways. Enterprise adds admin partitions, namespaces, and Sentinel integration.

## Compatibility Horizon
Consul ships about two minor releases per quarter with no LTS. Pin to the latest patch and validate upgrades one minor behind. Consult Envoy, Kubernetes, and Vault compatibility matrices per upgrade.

## Version Selection Decision Tree
- Single admin boundary and datacenter: open-source Consul with default ACLs.
- Multiple datacenters owned by one team: cluster peering.
- Hard multi-tenancy: Enterprise admin partitions.
- Kubernetes-dominant workloads: Consul on K8s with synced services.
- VM or ECS workloads: Consul agents on each host.
- Internet ingress or legacy backends: add ingress and terminating gateways.

## Operational Impact Points
- Envoy sidecar adds roughly 50-100m CPU and 64-128Mi memory per instance.
- Define CA rotation and certificate lifetime policy.
- Intentions are cluster-global; mis-edits affect the entire mesh.
- Upgrade windows must include Envoy compatibility verification.

## Cross-References
- See [HashiCorp Consul Version Governance](CONSUL_VERSION_GOVERNANCE.md) for the baseline Consul governance card.
- See [HashiCorp Boundary Secure Access Version Governance](BOUNDARY_VERSION_GOVERNANCE.md) for the complementary zero-trust access tier.
- See [HashiCorp Vault Version Governance](VAULT_VERSION_GOVERNANCE.md) for token and credential rotation governance.

---

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
