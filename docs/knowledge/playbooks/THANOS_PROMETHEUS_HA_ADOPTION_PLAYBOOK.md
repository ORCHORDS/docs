# Thanos Prometheus HA Adoption Playbook

## Purpose

Pair Thanos with Prometheus for durable long-term metrics, cross-cluster query deduplication, and unified rule evaluation, while keeping the operator path simple and reversible.

## Audience

Platform engineers, observability engineers, SREs.

## Pre-conditions

- `docs/knowledge/reference/THANOS_VERSION_GOVERNANCE.md` reviewed and current.
- Object storage bucket provisioned with lifecycle rules applied and access locked to the Thanos service account.
- Thanos sidecar injected into each Prometheus instance, with the sidecar pointing at the same bucket.
- Replication and deduplication labels aligned across every Prometheus pair in every cluster.
- CPU and memory budget per sidecar decided and recorded against the Thanos resource matrix.
- Recognition that Thanos Rule requires gRPC connectivity with the sidecar on the configured sidecar listen port.

## Procedure

### Step 1 — Install Thanos components in HA

1. Deploy the Thanos sidecar alongside every Prometheus instance as a co-located container.
2. Deploy the Thanos Store gateway and Thanos Querier as a stateful pair with at least two replicas per region.
3. Deploy the Thanos Compactor as a single active replica with `--wait` and `--consistency-delay` set to the documented values.
4. Deploy Thanos Ruler with at least two replicas; elect one as the query endpoint for `rule_files`.

### Step 2 — Register the sidecar with Prometheus

1. Add `--enable-feature=agent` is not used; instead pass `--storage.tsdb.path` and the standard scrape config.
2. Configure the sidecar `--tsdb.path` to match the Prometheus `--storage.tsdb.path`.
3. Point `--objstore.config` at the bucket prepared in Pre-conditions.
4. Verify sidecar health via `/metrics` and confirm the gRPC listen port is reachable from Querier and Ruler.

### Step 3 — Enable the Store API and index caches

1. Configure the Store gateway with `--store=tsdb` and the index cache pointing at memcached or Redis.
2. Enable bucket index caching to accelerate cross-bucket queries.
3. Validate a synthetic query that spans a series older than the local Prometheus retention window.
4. Capture p95 query latency before and after cache enablement to size the cache.

### Step 4 — Install Querier with replica labels

1. Start Querier with `--query.replica-label` set to the documented dedup label and `--endpoint=<sidecar-grpc>`.
2. Configure `--query.auto-downsampling` only if the use case requires it; default is off.
3. Validate dedup behavior: emit the same series from two Prometheus instances and confirm Querier returns exactly one.
4. Lock down the Querier gRPC and HTTP ports to the cluster-internal network only.

### Step 5 — Deploy Ruler for global rules

1. Configure Thanos Ruler with `--query.url` pointing at Querier and `--rule-file` paths in the rule ConfigMap.
2. Set `--alert.label-drop` to match the local Prometheus alert label policy so alerts do not double-fire across clusters.
3. Validate a global rule that spans two clusters by inspecting Alertmanager receivers.
4. Confirm Ruler writes back evaluated rules to Querier for unified alerts.

### Step 6 — Enable Compactor retention and re-upload options

1. Set `--retention.resolution-raw` and `--retention.resolution-5m` to the documented values.
2. Enable `--compact.enable-vertical-compaction` and `--compact.blocks-fetch-concurrency` per the resource matrix.
3. Schedule a soft retention review at every quarterly cadence with the data owners.
4. Validate cross-cluster dedupe under load: replay a captured production trace and confirm rule dedup holds at peak.

## Rollback

1. Drain Thanos Ruler and Querier via SIGTERM; do not SIGKILL until the rule queue and query queues are both empty.
2. Leave the Compactor running until the bucket is fully drained, so historical blocks remain queryable.
3. Re-route Grafana data sources to a vanilla Prometheus if query latency or dedup behavior is misbehaving.
4. Never delete the bucket without first locking the replica via a temporary bucket policy that denies all but the operator's break-glass account.

## References

- `docs/knowledge/reference/THANOS_VERSION_GOVERNANCE.md`
- Thanos Get Started: `https://thanos.io/v0.35/thanos/quick-start.md/`
- Thanos Query dedup: `https://thanos.io/v0.35/thanos/query.md/`
- Thanos Compactor: `https://thanos.io/v0.35/thanos/compact.md/`
- Thanos Ruler: `https://thanos.io/v0.35/thanos/rules.md/`
