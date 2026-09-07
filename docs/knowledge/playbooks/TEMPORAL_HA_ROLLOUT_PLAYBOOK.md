# Temporal HA Rollout Playbook

## Purpose

Deploy Temporal Server in HA configuration across multiple Kubernetes clusters (or hosts) with a quorum-aware persistence store, ensuring that a single host or zone failure does not interrupt workflow executions.

## Audience

Platform engineers, SRE on-call, database operators maintaining the persistence store.

## Pre-conditions

- Temporal Server ≥ 1.24.
- PostgreSQL ≥ 15 or Cassandra ≥ 5.0 deployed as the persistence backend, with at least 3 replicas.
- TLS certificates (server and client) signed by the ORCHORDS internal CA.
- Worker code already tested against the target Temporal SDK version.

## Procedure

1. **Schema bootstrap**: run `temporal-sql-tool` (or `temporal-cassandra-tool`) to create the schema in the persistence backend. Capture the schema version in `policies/temporal/schema.md`.
2. **Static config**: produce a `production.yaml` with at least:
   - `services.frontend.frontend.address = "0.0.0.0:7233"`
   - `services.frontend.frontend.mTLS = { enabled: true, ... }`
   - `cluster.metadata.replicationFactor = 3` (Postgres) or `local_dc + remote_dc` (Cassandra).
3. **Dynamic config**: commit `dynamic-config.yaml` with limits (RPS, task-schedule-to-start timeout) set conservatively; tune after canary.
4. **Helm install**: `helm install temporal temporal/temporal --values production.yaml --set server.replicaCount=3`. Confirm all 5 services (frontend, matching, history, worker, ui) come up healthy.
5. **Namespace create**: `temporal operator namespace create prod-orders --retention 30d --history_archival_state=enabled --visibility_archival_state=enabled`.
6. **Worker rollout**: deploy worker pods with `TEMPORAL_ADDRESS=<server>:7233` and `TEMPORAL_NAMESPACE=prod-orders`.
7. **Smoke tests**: run a canary workflow that exercises `signal`, `query`, `update`, and `continueAsNew`.
8. **Cross-zone resilience**: stop one pod; observe `temporal_pending_activities` recover and `temporal_workflow_completed_total` keep incrementing.

## Rollback

- `helm uninstall temporal` removes the deployment; persistence state is preserved, so the same state can be re-attached to a reverted install.
- If a code-path mismatch between server and worker causes replay failures, downgrade worker SDKs first and roll the server back with `helm rollback`.

## References

- Temporal Cluster deployment guide — https://docs.temporal.io/cluster-deployment-guide
- Temporal SQL schema tool — https://github.com/temporalio/temporal/blob/master/tools/sql/README.md
- Internal: Batch 100 reference card `TEMPORAL_VERSION_GOVERNANCE.md`.
