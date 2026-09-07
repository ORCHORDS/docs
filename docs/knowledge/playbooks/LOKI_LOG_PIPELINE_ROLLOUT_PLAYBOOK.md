# Loki Log Pipeline Rollout Playbook

## Purpose

Stand up Loki (monolith or microservices mode) as the central log aggregation backend for cluster and container logs, with retention, multi-tenancy, and ingest controls covered end-to-end.

## Audience

Platform engineers, SREs, observability engineers.

## Pre-conditions

- `docs/knowledge/reference/LOKI_VERSION_GOVERNANCE.md` reviewed and current.
- Helm chart or operator target decided (Helm chart is the default; operator is allowed for HA control-plane customers).
- Object storage bucket created (S3, GCS, Azure Blob, or MinIO) with lifecycle rules pre-applied.
- Chunk encoder version chosen; the v2 schema is the documented best practice and must be selected unless the governance card explicitly approves v1.
- Tenant IDs prepared and mapped to business units, environments, and data classes.
- Collection agent picked from the supported set: Promtail, Grafana Alloy, Vector, or Fluent Bit.

## Procedure

### Step 1 — Install Loki in monolith mode for staging

1. Deploy the Helm chart with `deploymentMode: SingleBinary` against the staging cluster.
2. Pin the chart version to the version recorded in `LOKI_VERSION_GOVERNANCE.md`; do not float on `latest`.
3. Configure the chunk encoder to v2 schema and disable any v1 fallback paths.
4. Smoke test with a synthetic log stream from one cluster workload; confirm ingest, query, and rule evaluation in Grafana.

### Step 2 — Provision the object storage bucket and lifecycle

1. Create the bucket with versioning enabled and a lifecycle rule that transitions objects to the chosen cold-storage tier after the documented hot window.
2. Lock down the bucket policy to the Loki service account only; deny public access.
3. Configure `compactor.retention_enabled=true` and the retention window to match the lifecycle transition.
4. Run a synthetic retention pass: write logs, age them, and confirm the compactor deletes the expected keys.

### Step 3 — Flip to microservices mode for production

1. Set `deploymentMode: Distributed` and split the read, write, backend, and compactor components into their own StatefulSets.
2. Size the write path to the documented per-tenant ingest rate, and the read path to the documented query concurrency.
3. Wire the index gateway in front of the boltdb-shipper or tsdb index store.
4. Validate that staging data migrated cleanly and that no logs were dropped during the topology flip.

### Step 4 — Register tenants and write-paths in collectors

1. For each tenant, define an `X-Scope-OrgID` header value and a per-tenant write target in the collector configuration.
2. Enforce tenant isolation at the collector (Promtail/Alloy/Vector/Fluent Bit pipeline) so a misrouted stream cannot cross tenants.
3. Apply ingest controls per tenant: rate limits, drop rules for known-noisy labels, and label-allowlists to bound cardinality.
4. Validate end-to-end: a synthetic log from each tenant should land only in that tenant's query scope.

### Step 5 — Configure retention via the compactor

1. Enable the compactor with per-tenant retention periods.
2. Set retention deletions per stream, not per tenant, to avoid sweeping critical streams.
3. Confirm the compactor emits metrics for deletions, errors, and remaining-object count.
4. Schedule a retention dry-run review with the data owners at every quarterly cadence.

### Step 6 — Migrate from Elasticsearch or Splunk if applicable

1. Run dual-write from the existing collector into both the legacy sink and Loki for at least one full retention window.
2. Cut read traffic in Grafana to Loki, keeping Splunk/Elasticsearch as a read-only mirror for one billing cycle.
3. Decommission the legacy ingest once dashboards, alerts, and on-call runbooks all reference Loki.
4. Capture the decommission evidence in the change record and link it from `LOKI_VERSION_GOVERNANCE.md`.

## Rollback

1. Drain ingest via the `loki-consul-resolver` (or equivalent service registry resolver) so no new streams are accepted.
2. Stop the write path first; keep the read path online until dashboards are pointed back to the legacy backend.
3. Snapshot the compactor state for forensic recovery before any deletion step.
4. Preserve chunks for at least one full retention window in cold storage so post-rollback queries can be replayed if needed.

## References

- `docs/knowledge/reference/LOKI_VERSION_GOVERNANCE.md`
- Loki storage schema: `https://grafana.com/docs/loki/latest/storage/`
- Loki upgrade guide: `https://grafana.com/docs/loki/latest/upgrading/`
- Grafana Loki operations: `https://grafana.com/docs/loki/latest/operations/`
