# Prometheus High-Availability Playbook

## Purpose

Define the operational procedure for running Prometheus in a high-availability (HA) configuration. The procedure covers duplicate instances with external long-term storage (Thanos / Cortex / Mimir / VictoriaMetrics) and the standard query / alert paths.

## Audience

Platform engineers, SREs, and observability engineers.

## Pre-conditions

- Prometheus 2.30+ (per `PROMETHEUS_VERSION_GOVERNANCE.md`).
- The team operates at least two Prometheus replicas per scrape target.
- Long-term storage is configured via `remote_write`.
- Alertmanager is HA-deployed.

## Procedure

### Step 1 — Design

1. Plan for at least 2 Prometheus replicas per HA shard.
2. Plan for an external storage backend (Thanos / Cortex / Mimir / VictoriaMetrics).
3. Plan for an HA Alertmanager cluster (gossip-based).

### Step 2 — Configure

4. Both Prometheus replicas scrape the same targets.
5. Both replicas write to `remote_write`.
6. Each replica has a unique `external_labels`.
7. Set `replica_label` on the remote-write config to dedupe.

### Step 3 — Deploy

8. Deploy both replicas via GitOps (per `GITOPS_SYNC_FAILURE_RECOVERY_PLAYBOOK.md`).
9. Deploy Alertmanager in HA gossip mode.
10. Deploy the query layer (Thanos querier, Grafana, etc.).

### Step 4 — Validate

11. Confirm both replicas are scraping: `/api/v1/targets`.
12. Confirm remote-write is succeeding.
13. Confirm Alertmanager peers are connected.

### Step 5 — Verify

14. Confirm query latency is within SLO.
15. Confirm alerts fire on both replicas.
16. Confirm long-term storage is ingesting.

### Step 6 — Failure scenarios

17. If one replica is down, the other continues to scrape and alert.
18. If Alertmanager loses quorum, alerts are buffered and re-sent.
19. If the storage backend is down, replicas buffer via `remote_write` queue.

## Rollback

If HA configuration breaks scrape:

1. Restore the previous Prometheus config from Git.
2. Confirm targets are reachable.
3. Investigate the regression.

## References

- `PROMETHEUS_VERSION_GOVERNANCE.md`
- Prometheus HA: `https://prometheus.io/docs/prometheus/latest/operating_ha_archives/`
- Thanos: `https://thanos.io/`
- Cortex: `https://cortexmetrics.io/`
- Alertmanager HA: `https://github.com/prometheus/alertmanager`
