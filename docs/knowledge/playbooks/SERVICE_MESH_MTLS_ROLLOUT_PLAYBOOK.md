# Service Mesh mTLS Rollout Playbook

## Purpose

Roll out strict mutual TLS (mTLS) across a Kubernetes-orchestrated ORCHORDS service mesh (Istio, Linkerd, or Cilium service mesh) in a phased manner, ensuring traffic continues to flow during the migration and that plaintext traffic is progressively eliminated. The play covers the permissive→strict transitions and the rollback path for any service that fails its post-cutover SLOs.

## Procedure

1. **Establish the baseline.**
   - Confirm mesh version (Istio ≥ 1.20, Linkerd ≥ 2.14, or Cilium ≥ 1.14 recommended).
   - Inventory all `Namespace`, `Service`, and `Workload` objects in the mesh.
   - Capture pre-rollout golden signal baselines: RPS, p50/p95/p99 latency, error rate.
2. **Enable mesh-wide permissive mode.** Set `meshConfig.peerAuthentication.mode: PERMISSIVE` (Istio) or equivalent (`linkerd install --cluster-domain ...` defaults to permissive). Mesh accepts both plaintext and mTLS traffic during this phase.
3. **Issue workload identities.**
   - SPIRE/Istio: `spire-server entry create -spiffeID ... -parentID spiffe://.../ns/.../sa/... -selector k8s:ns=... -selector k8s:sa=...`.
   - Linkerd: linkerd-svc `linkerd upgrade --identity-issuer ... --identity-issuer-scheme ...`.
   - Cilium: configure CiliumClusterwideEnvoyConfig with SPIFFE-aware `AuthenticationPolicy`.
4. **Per-namespace permissive pilot.**
   - Apply `PeerAuthentication` namespace-scope with `PERMISSIVE`.
   - Watch telemetry for at least one full release cycle (default 24h).
   - Inspect mesh dashboard for any client using plaintext-only connections.
5. **Per-workload strict rollout.** Roll out `PeerAuthentication` with `STRICT` mode one workload at a time. For each workload:
   - Confirm mesh-internal callers (sidecars) can authenticate via SPIFFE.
   - Confirm external callers (ingress gateway, third-party clients) are explicitly excluded or terminated via mesh ingress.
   - Confirm encryption of east-west traffic via `tcpdump` on a sidecar interface.
6. **Observe and gate.**
   - Watch SLO dashboards for the workload: any error-rate regression > 0.1% OR latency regression > 5% MUST trigger rollback (step 9).
   - Confirm zero plaintext in traffic telemetry (`metric=istio_tcp_connections_closed_total{...}` shows `tls=mtls` for all intra-mesh flows).
7. **Promote to strict cluster-wide.** Once >95% of workloads are on `STRICT`, set mesh-wide `meshConfig.peerAuthentication.mode: STRICT`. Verify ingress gateway and external auth chains still work.
8. **Tighten AuthorizationPolicy.** Layer `AuthorizationPolicy` (Istio) or `ServerAuthorization`/`NetworkPolicy` (Linkerd, Cilium) on top of mTLS so each workload only accepts the SPIFFE IDs it needs to.
9. **Rollback path.** For any workload failing SLOs after strict mode, fall back to namespace `PERMISSIVE` while root-causing. Document the rollback in the change record.
10. **Lock and audit.** Disable any fallback to plaintext; remove permissive exemptions; confirm `meshConfig.peerAuthentication.mode: STRICT`. Save audit log of all `PeerAuthentication`/`AuthorizationPolicy` deltas to long-term storage.
