# CNCF Prometheus Federation and Scaling Governance

## Purpose

Govern the deployment of Prometheus at scale so that the monitoring system itself is operated as a production service: federation and remote write architectures are chosen deliberately, retention and cardinality budgets are set, and query performance degrades gracefully instead of collapsing during incidents.

## Scope

Applies to every Prometheus deployment the studio operates: single-instance, federated, and remote-write architectures, covering retention, cardinality management, federation topology, and long-term storage integration. It does not cover alert rule design or dashboard practice.

## Workflow

1. Choose the architecture for the query pattern: single-instance for contained scope, hierarchical federation for aggregating a few select metrics upward, remote write to a long-term store (e.g., Thanos/Mimir/Cortex) for global view and long retention. Document the choice.
2. Set retention per tier consistent with local storage capacity: short local retention with remote-write durability is preferred over long local retention without durability.
3. Enforce a cardinality budget: measure active series per instance, alert on cardinality growth, and require label allowlists for high-cardinality sources (user IDs, request IDs).
4. In federation, aggregate selectively: federate only curated recording rules and low-cardinality aggregates upward; federating raw series multiplies load on the global layer and is prohibited.
5. For remote write, control queue capacity, shards, and retry behavior per store; monitor queue drop rates — dropped samples are silent data loss.
6. Record rules for common queries: pre-aggregate expensive expressions into recording rules so dashboards and alerts query the rule output, not raw series.
7. Capacity-plan the monitoring stack itself: scrape target count, samples-per-second ingest rate, and query concurrency tracked against instance capacity.

## Controls and evidence

- Architecture decision record per deployment (federation vs. remote write) with rationale.
- Retention configuration per tier with storage capacity headroom evidence.
- Cardinality budget, per-instance series counts, and label allowlist enforcement records.
- Remote-write queue monitoring showing drop rate near zero.
- Recording rule catalogue for dashboard- and alert-serving queries.

## Validation

- Confirm cardinality alerting fires when a test high-cardinality source is introduced.
- Confirm remote-write queue drop rate is at or near zero over the sample window.
- Confirm dashboards and alerts query recording rule outputs for the top time-series expressions.

## Failure correction

- **Cardinality explosion** → drop or aggregate the offending labels at the source or via metric relabeling; post-mortem the allowlist gap.
- **Remote-write drops** → increase queue capacity or shards, investigate store-side rejection, and backfill lost samples if possible.
- **Federation overload at global layer** → replace raw-series federation with aggregated recording rules and re-establish the upward feed.

## Limitations

- Prometheus scaling patterns evolve; architecture decisions have a shelf life and should be revisited with major version changes.
- Recording rules shift cost from query time to ingest time; balance per actual usage patterns.
- Long-term storage backends add operational surface (object storage, compaction) with their own governance needs.

## Scope note

This article is part of the operations leaf and pairs with the monitoring index and SLO burn-rate guidance. Cross-reference: `monitoring/README.md`, `SRE_RELEASE_COORDINATION_ERROR_BUDGET_GOVERNANCE.md`, and `monitoring/prometheus-remote-write-queue-capacity-and-shard-tuning.md`.

## Canonical sources

- Prometheus Documentation — Federation: https://prometheus.io/docs/prometheus/latest/federation/
- Prometheus Documentation — Storage: https://prometheus.io/docs/prometheus/latest/storage/
- Thanos — Architecture: https://thanos.io/tip/thanos/design.md/
- Grafana Mimir — Architecture: https://grafana.com/docs/mimir/latest/
- Google SRE Workbook — Alerting on SLOs: https://sre.google/workbook/alerting-on-slos/
