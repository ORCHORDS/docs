# Consul Service Mesh (Connect) Adoption Playbook

## Purpose

Deploy HashiCorp Consul Connect as the service mesh for mutual TLS (mTLS) between services spanning Kubernetes clusters and legacy VM workloads. The adoption establishes cryptographic service identity, enforces service-to-service authorization through intentions, and integrates with the observability stack for trace, metric, and audit correlation.

## Audience

Platform engineers owning the Consul control plane, security engineers governing identity and transport, application owners integrating sidecars or transparent proxies, and SRE on rotation handling mesh incidents.

## Pre-conditions

- Consul 1.18.x deployed, aligned to `reference/CONSUL_SERVICE_MESH_VERSION_GOVERNANCE.md:1`.
- Consul on Kubernetes via the official Helm chart with `global.enabled=true`.
- Consul server cluster sized for HA: 3 or 5 servers across availability zones, Raft snapshot agent configured.
- ACL system bootstrapped; bootstrap token captured into the secret manager.
- Internal TLS CA issued and distributed to server, client, and connect agents.
- Observability stack available: Prometheus, Grafana, and Jaeger or Zipkin.
- SIEM/SOAR audit destination reachable for Consul telemetry export.
- Change ticket approved with maintenance window.

## Procedure

### Step 1 — Deploy Consul servers in HA

1. Apply the Helm release with `server.replicas=3` (or 5), `server.bootstrap=true` for the first member, and `server.snapshotAgent.enabled=true`.
2. Configure `server.snapshotAgent.storage` to write to object storage on a 30 minute cadence.
3. Validate quorum with `consul operator raft list-peers`.

### Step 2 — Bootstrap ACLs

4. Run `consul acl bootstrap` once, capture the bootstrap token, store it in Vault, and lock it under `secret/consul/bootstrap`.
5. Apply the anonymous policy with `agent:read` so unauthenticated agents can self-register.
6. Create per-environment tokens (dev, stage, prod) bound to least-privilege policies.

### Step 3 — Configure the mesh CA

7. Generate the Connect CA with `consul connect ca set-config -config-file=ca.hcl` choosing the built-in provider with 24 hour leaf TTL and 3 year root TTL.
8. Distribute the CA root to all client agents via the `connect.ca` configuration block.

### Step 4 — Author intentions

9. Define `ConsulIntention` CRDs for L4 (`L4Intentions`) and L7 (`L7Intentions`) authorization between services.
10. Start in `permit` with explicit `deny` for east-west paths crossing trust boundaries.
11. Validate with `consul config write` and confirm `consul intention check` returns the expected decision.

### Step 5 — Deploy connect injection on Kubernetes

12. Upgrade the Helm release with `connectInject.enabled=true` and `connectInject.default=true` for the target namespaces.
13. Annotate workloads with `consul.hashicorp.com/connect-inject=enabled` where opt-in is required.
14. Confirm the injector webhook reports healthy and pods receive a sidecar on the next rollout.

### Step 6 — Enable transparent proxy

15. Set `connectInject.transparentProxy.enabled=true` in the Helm values.
16. For VM workloads, configure the Consul client with `connect.transparent_proxy.enabled=true` and the DNS listener on port 8600.
17. Remove legacy `localhost` upstream overrides from application config.

### Step 7 — Configure ingress gateways

18. Deploy `ingress-gateway` pods with a Helm subchart and define `IngressGateway` CRDs for north-south routes.
19. Terminate external TLS at the gateway and re-encrypt to upstream services using the mesh CA.

### Step 8 — Configure terminating gateways

20. Deploy `terminating-gateway` for legacy VMs and external services that cannot run a sidecar.
21. Define `ServiceConfigEntries` with `protocol` and `upstreams` so the gateway brokers outbound mTLS.

### Step 9 — Enable telemetry

22. Set `telemetry.collectMetrics = true` and `telemetry.distribution.otel.enabled = true` on all agents.
23. Scrape Consul telemetry metrics into Prometheus and forward Consul access logs to the SIEM destination.
24. Wire trace context propagation through Jaeger or Zipkin so spans correlate across mesh hops.

### Step 10 — Validate mTLS

25. From a registered service, run `consul connect intention check -service <src> -dst <dst>`.
26. Confirm certificates rotate on schedule using `consul connect ca list`.
27. Issue a synthetic call and confirm Prometheus records the upstream TLS handshake.

### Step 11 — Drill certificate rotation

28. Trigger a CA rotation in staging with `consul connect ca rotate`.
29. Verify downstream services reconnect without dropping requests and that no intention mismatches appear in the audit log.

### Step 12 — Hand over to operations

30. Publish runbook links, dashboard URLs, and on-call escalation paths to the SRE rotation.
31. Capture final acceptance evidence in the change ticket and close the adoption milestone.

## Rollback

1. Drain the data plane by setting `connectInject.default=false` and removing gateway manifests in reverse order.
2. Revoke intentions with `consul intention delete -match` to restore explicit allow rules only where required.
3. Detach services from the mesh and revert DNS to the pre-mesh upstream addresses.
4. Retain Consul telemetry, intention logs, and CA certificates in the SIEM for forensic review.
5. Document the rollback cause, scope, and recovery time in the change ticket and notify the security engineering distribution list.

## References

- `reference/CONSUL_SERVICE_MESH_VERSION_GOVERNANCE.md`
- `reference/VAULT_VERSION_GOVERNANCE.md` for token storage and rotation
- `playbooks/CONSUL_TOKEN_ROTATION_PLAYBOOK.md` for ongoing token lifecycle
- `reference/SIEM_ARCHITECTURE_GOVERNANCE.md` for audit destination
- `reference/SOAR_AUTOMATION_GOVERNANCE.md` for automated response playbooks
