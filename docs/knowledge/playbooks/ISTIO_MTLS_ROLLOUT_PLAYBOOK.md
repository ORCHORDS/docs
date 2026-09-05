# Istio mTLS Rollout Playbook

## Purpose

Define the operational procedure for rolling out Istio mTLS in STRICT mode across a service mesh. The procedure uses a phased PERMISSIVE → STRICT transition to ensure that legacy plaintext clients do not lose connectivity.

## Audience

Platform engineers, SREs, and security engineers.

## Pre-conditions

- Istio 1.19+ installed (per `ISTIO_VERSION_GOVERNANCE.md`).
- The mesh namespace exists.
- AuthorizationPolicy CRDs are installed.
- The team can roll back via GitOps revert.

## Procedure

### Phase 1 — Inventory

1. List all workloads in the target namespace: `kubectl get deploy -n <ns> -o yaml`.
2. Identify workloads without a sidecar (legacy plaintext).
3. Identify workloads that originate traffic outside the mesh (ingress gateways, external clients).
4. Document every legacy plaintext client.

### Phase 2 — Audit policy baseline

5. Confirm the mesh-wide `PeerAuthentication` is `PERMISSIVE` (no enforcement).
6. Confirm `DestinationRule` `mesh-wide` TLS mode is `ISTIO_MUTUAL` (or not set).
7. Confirm AuthorizationPolicy defaults are not blocking plaintext.

### Phase 3 — Opt-in per workload

8. For each workload, apply a `PeerAuthentication` in PERMISSIVE mode first.
9. Observe mesh telemetry (Kiali / Prometheus) for failed TLS connections.
10. Validate that the workload accepts both plaintext and mTLS traffic.

### Phase 4 — Selective STRICT

11. For each workload, change its `PeerAuthentication` to STRICT.
12. Monitor the workload for 24 hours:
    - `istio_requests_total{response_code=~"5.."}`.
    - `istio_tcp_connection_closed_local{...}`.
13. If errors spike, revert to PERMISSIVE and investigate.

### Phase 5 — Mesh-wide STRICT

14. Apply mesh-wide `PeerAuthentication` with `mtls.mode: STRICT`.
15. Confirm every workload has its own `PeerAuthentication` aligned (STRICT or PERMISSIVE explicitly).
16. Monitor mesh-wide for 24 hours.

### Phase 6 — Lock down

17. Set AuthorizationPolicy default-deny on every namespace.
18. Add explicit ALLOW rules per workload pair.
19. Validate with `kubectl authz-can-i` (if installed) or via synthetic test.

### Phase 7 — Verify

20. Confirm every connection in Kiali shows the lock icon (mTLS).
21. Confirm access logs show `conn_security_policy: ISTIO_MUTUAL`.
22. Confirm no plaintext traffic in `istio_tcp_connection_opened`.

## Rollback

If STRICT mode breaks a workload:

1. Revert the `PeerAuthentication` to PERMISSIVE (or remove it).
2. Verify traffic recovers.
3. File a postmortem per `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md`.

## References

- `ISTIO_VERSION_GOVERNANCE.md`
- `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md`
- Istio mTLS: `https://istio.io/latest/docs/concepts/security/mutual-tls/`
- Istio PeerAuthentication: `https://istio.io/latest/docs/reference/config/security/peer_authentication/`
