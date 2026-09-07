---
title: SPIFFE and SPIRE Workload Identity Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-07
review-cycle: 180 days
next-review: 2027-03-06
source: https://spiffe.io ; https://github.com/spiffe/spire ; https://github.com/spiffe/spiffe
---

# SPIFFE and SPIRE Workload Identity Version Governance

## 1. Purpose

This reference card defines the version-governance model for the Secure Production Identity Framework for Everyone (SPIFFE) and its reference implementation, the SPIFFE Runtime Environment (SPIRE). It applies to platforms that issue cryptographic workload identities to Kubernetes workloads, VMs, and bare-metal services for mTLS, JWT-based authentication, and federated trust.

## 2. Scope

In scope:

- **SPIRE Server** (control plane) ≥ 1.7.x and **SPIRE Agent** ≥ 1.7.x.
- **SPIFFE Workload API** ≥ v0.3 (Unix domain socket and experimental gRPC).
- **SVID** types: X.509-SVID and JWT-SVID, including the rotated `federated_bundles` map.
- SPIRE plugins: **Node Attestation** (aws_iid, gcp_iit, azure_msi, k8s_psat, k8s_sat), **Workload Attestation** (unix, k8s), and **Key Manager** (memory, disk, aws_kms, pkcs11).
- **Trust domain** federation between SPIRE deployments.

Out of scope:

- SPIRE Federation for hardware TPMs and HSMs as the primary attestation source.
- Custom SPIFFE Verifiable Identity Document (SVID) types beyond X.509 and JWT.

## 3. Versioning policy

- Pin the SPIRE Server and Agent to a specific `--version` (e.g. `v1.7.6`) and SHA-256 digest. Never float on `:latest`.
- Maintain a single **trust domain** per cluster; cross-cluster federation is achieved through SPIRE Federation, not by sharing a trust domain.
- Use `spire-agent` DaemonSet with at most one Agent per node. Multi-Agent deployments are allowed only when `nested_spire` is enabled and the child SPIRE is federated with the parent.
- Run SPIRE Server HA in 3 or 5 replica configurations with Raft consensus; do not run single-node SPIRE Server in production.

## 4. Compatibility matrix

| SPIRE | Kubernetes | Notes |
| --- | --- | --- |
| 1.6.x | 1.27+ | k8s_psat uses BoundServiceAccountTokenVolume |
| 1.7.x | 1.28+ | experimental nested SPIRE, attestation caching |
| 1.8.x | 1.30+ | k8s_sat Workload Identity (EKS Pod Identity upstream) |

## 5. Identity issuance

- Issue X.509-SVIDs with TTL ≤ 1 hour and rotate transparently; intermediate CA TTL ≤ 24 hours.
- Issue JWT-SVIDs only for cross-cluster/cross-cloud federation; restrict TTL ≤ 5 minutes.
- Combine with Cilium CNI `mutual` TLS to enforce workload identity on the wire.

## 6. Federation setup

1. Generate a **trust bundle** with `spire-server bundle show -format spiffe_json > bundle.json` and exchange bundles with the peer SPIRE via `spire-server bundle set`.
2. Configure `federation {}` block per trust domain with explicit `bundle_endpoint_url`, `trust_domain`, and `spiffe_trust_domain` mapping.
3. Validate with `spire-server federation list` and a smoke test that issues an X.509-SVID against the foreign trust domain.

## 7. Upgrade procedure

1. Roll SPIRE Agents first, one node at a time, validating that workloads still obtain X.509-SVIDs.
2. Roll the SPIRE Server last; use the built-in Raft-based HA failover (no manual leader promotion).
3. Verify trust bundle propagation via `spire-server bundle show` post-upgrade.

## 8. Rollback procedure

- `helm rollback spire <previous-revision>` reverts the chart; SPIRE Server keeps the Raft log so previous bundles are recoverable.
- If a CA compromise is suspected, call `spire-server token revoke -spiffeID spiffe://td/workload` and force a key rotation.

## 9. Observability

- Required metrics: `spire_agent_svid_rotation_total{type}`, `spire_server_rpc_total{status,method}`, `spire_attestation_failures_total`.
- Alert on `rate(spire_attestation_failures_total[5m]) > 0.05` and on `spire_server_rpc_total{status="error"}` > 0.1.

## 10. References

- SPIFFE specification — https://github.com/spiffe/spiffe
- SPIRE documentation — https://spiffe.io/docs/latest/spire/
- Kubernetes Workload Identity (KEP-1209) — https://github.com/kubernetes/enhancements
