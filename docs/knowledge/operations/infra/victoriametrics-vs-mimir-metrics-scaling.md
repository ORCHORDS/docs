# victoriametrics-vs-mimir-metrics-scaling

**Issue:** Vanilla Prometheus stores metrics on local disk with a fixed retention and no horizontal scaling, which stops working somewhere between one and a few million active series: disk fills, queries over long ranges time out, and adding more monitored services means another siloed Prometheus to federate. The standard fix is a remote-write backend for long-term storage and global query, but the 2025-2026 landscape offers three credible answers — Thanos, Grafana Mimir, and VictoriaMetrics — with genuinely different architectures (object storage sidecars versus horizontally-scaled microservices versus single-binary efficiency play), and the choice is expensive to reverse once hundreds of Prometheus servers remote-write into it. Teams need a decision framework based on scale, multi-tenancy needs, operational appetite, and cost per million series, not vendor benchmarks.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## How the three architectures differ

1. **Thanos: sidecar plus object storage.** A sidecar next to each Prometheus uploads blocks to S3/GCS; store gateways serve the history, compactors downsample, and a query layer federates it. This is the smoothest migration from vanilla Prometheus — no change to scrape configs, and object storage keeps per-byte costs low — at the price of running four or five new component types.

2. **Grafana Mimir: horizontally scalable microservices by design.** Mimir (Cortex's successor) splits ingest, store, query-frontend, and compactor into independently scaled services with strong multi-tenancy (per-tenant limits, isolated query namespaces). It is the most operationally ambitious: designed for tens of billions of series, at home in an organization already running big Kubernetes clusters and the Grafana ecosystem.

3. **VictoriaMetrics: efficiency-first single binary.** VM can run as one binary (or a small vmselect/vminsert/vmstorage cluster) with its own storage engine rather than object storage, and accepts Prometheus remote-write plus its own query language (MetricsQL). Community and vendor benchmarks through 2025 consistently show it using less CPU, RAM, and disk per million series than the others; Grafana Mimir's own comparisons concede VM's efficiency while contesting feature breadth.

4. **Latency profiles favor VM for mid-scale.** Independent roundups put median query latency around 20-50 ms for VictoriaMetrics, 30-80 ms for Mimir with caching, and 50-100 ms for Thanos, reflecting how many network hops each architecture puts between query and data. At small scale all three feel instant; at large scale the differences compound into dashboard usability.

## Decision criteria

1. **Choose Thanos when Prometheus is already everywhere and S3 exists.** The sidecar model means near-zero application change, and object storage economics beat dedicated disks for multi-year retention. Accept slower long-range queries and more moving parts than VM.

2. **Choose Mimir when multi-tenancy is a hard requirement.** If platform teams serve dozens of internal teams with per-tenant quotas, retention, and isolation, Mimir's tenant model is the most complete of the three, and it pairs naturally with Grafana's RBAC and alerting ecosystem.

3. **Choose VictoriaMetrics when cost and simplicity dominate.** For the common mid-scale case — tens of millions of active series, a handful of operators — a single VM binary with replicas beats running a distributed system. VM's own Mimir benchmark showed roughly 1.7x less CPU usage; treat vendor numbers skeptically, but independent evaluations reach the same efficiency conclusion.

4. **Do not forget Thanos compatibility gravity.** Thanos and Mimir speak PromQL natively against all Prometheus features; VM's MetricsQL is a superset but has edge-case semantic differences (notably around rate and extrapolation) that occasionally surprise dashboards migrated verbatim.

5. **Size from active series and cardinality, not host count.** The real cost driver is active time series (cardinality), so estimate per-service series counts, add label-growth headroom, and pressure-test the candidate with realistic cardinality before committing — a spike in high-cardinality labels is what actually pages on-call at 3 a.m.

## Migration mechanics

1. **Remote-write dual-ship before cutover.** Point Prometheus remote_write at the new backend while keeping local retention short; run old and new dashboards side by side for a week to catch dropped samples and semantic drift before anyone relies on the new system.

2. **Backfill history deliberately.** Thanos can import existing TSDB blocks directly; VM and Mimir have their own import tooling for Prometheus data. Decide how many years of history actually justify backfill — usually far less than teams assume.

3. **Preserve recording rules and alerts or rewrite them once.** Recording rules can stay in Prometheus, move into the backend's ruler component (Thanos Ruler, Mimir ruler, vmalert), or split between the two. Pick one convention per org; split rule ownership is how alerts silently diverge.

4. **Plan cardinality governance from day one.** Whichever backend wins, deploy the cardinality analysis tooling (VM's cardinality explorer, Mimir/Thanos' tenant metrics, or PromQL topk on counts) and set per-tenant or per-job series limits before the first runaway label turns into an outage.

## Operational cost comparison

1. **Count component types, not just servers.** Rough operational footprint: VM single binary (1-3 nodes), Thanos (sidecars plus 4 service types), Mimir (6 or more service types plus dependencies like object storage, memcached, and optionally Kafka at high scale). Each component is an on-call surface.

2. **Object storage is a cost lever and a failure domain.** Thanos and Mimir depend on S3-compatible storage for durability; a misconfigured lifecycle policy or an outage in the bucket becomes a monitoring outage. VM's local-disk model trades that dependency for disk management and snapshot-based backups.

3. **Compress retention into the architecture.** Downsampling (Thanos/Mimir) and VM's compression both shrink long-term storage roughly 5-10x for year-plus retention; enable them at setup because retrofitting retention changes onto months of raw data is painful.

4. **Benchmark with your own queries.** Dashboard query patterns (range queries over 30 days, heavy label matching) vary wildly between orgs; a one-day load test replaying real dashboards against a candidate with production cardinality is the cheapest de-risking available before a multi-year commitment.
