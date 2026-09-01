# Data Lakehouse Medallion Lake Architecture

## Scope

This article addresses the lakehouse pattern and its concrete realisation in the medallion architecture (bronze, silver, gold layers). It explains the role of each tier, the storage formats and table formats that make the pattern viable, and the trade-offs against the older data warehouse and data lake patterns. The discussion covers table formats such as Delta Lake, Apache Iceberg, and Apache Hudi; columnar storage such as Parquet and ORC; and the metadata, schema, and transactional guarantees that distinguish a lakehouse from a raw data lake. The article applies to any organisation that needs a single substrate for both analytics and machine learning, including those running on Cloudflare R2, S3, Azure Data Lake Storage, or on-premises object stores.

## Workflow or implementation guidance

The medallion architecture organises a lakehouse into three layers that progressively refine the data. The bronze layer holds the raw, append-only ingest: events, CDC records, application logs, third-party feeds. The bronze layer is the source of truth for "what did we actually receive?" It is preserved indefinitely because every later transformation must be reproducible from the bronze. The silver layer holds cleaned, deduplicated, conformed data: events with schema applied, entities resolved, time zones normalised, nulls handled. The silver layer is the system of record for the analytic entities of the business. The gold layer holds aggregated, denormalised, business-facing data: feature tables, dimensional models, reports. The gold layer is optimised for the queries that the business actually runs.

The first step in implementation is to choose the table format. The table format is the substrate that turns a collection of files into a table: it provides schema, partitioning, time travel, ACID transactions, and the ability to evolve. Delta Lake, Apache Iceberg, and Apache Hudi are the three dominant open formats. The choice depends on the query engine, the operational ecosystem, and the team's familiarity; all three are sufficient for the medallion pattern. The second step is to choose the storage format for the underlying files. Parquet is the dominant choice because of its columnar layout, predicate pushdown, and broad engine support. ORC is a viable alternative. The third step is to wire the ingest pipeline. Bronze ingest should be append-only and idempotent: a duplicate delivery of the same event must produce a single row in bronze, identified by the event ID. Silver and gold transformations are streaming or batch jobs that read from the previous layer and write the next.

The fourth step is to establish schema and contract. Bronze accepts whatever arrives and records it as received, but silver enforces a schema that is the agreed contract between producers and the analytic entities. The schema lives in a registry (a schema-registry-style service, an OpenAPI specification, or a Protobuf file) and is versioned. The fifth step is to plan for compaction and optimisation. Object-store-backed tables accumulate small files; a compaction job merges them into larger files so that queries can scan efficiently. Time travel, partitioning, and vacuuming are operational concerns that must be scheduled and observed.

The sixth step is to plan for query access. Silver and gold are queried by analysts, by notebooks, by reverse-ETL jobs, and by feature stores. Each consumer benefits from a different shape: silver for ad hoc exploration, gold for repeated queries, and per-consumer materialised views for hot paths. The medallion architecture does not prescribe a query engine; Spark, Trino, Flink, DuckDB, and cloud-native services such as Athena, BigQuery, or Databricks SQL can all read the same tables.

## Controls

Lakehouse controls span data quality, schema evolution, retention, and access. Data quality controls include expectations at each tier: bronze accepts anything, silver enforces uniqueness and referential integrity, gold enforces business invariants. Schema evolution controls include backward-compatible changes by default and forward-compatible reviews for breaking changes. Retention controls include tiered storage classes (hot for gold, cool for silver, archive for bronze) and time-bound retention policies for PII. Access controls include table-level grants, column-level masking for sensitive fields, and audit logging for every query.

The schema registry must be the single source of truth for event schemas. A lakehouse without a schema registry quickly accumulates undocumented fields and silently drifts from the producers. Lakehouse-specific controls also include the metadata catalogue: a central metastore (Hive Metastore, Glue Data Catalog, Unity Catalog) that tracks table locations, schemas, partitions, and statistics.

## Validation evidence

Validation must prove that transformations are correct and reproducible. A medallion lakehouse is built on the principle that any gold table can be regenerated from bronze through the same silver and gold pipeline; this is the strongest evidence of correctness. Validation tests include: a known input set produces a known silver and gold output; a schema change in bronze does not silently corrupt silver; a compaction does not change the query results. The tests are typically run as part of CI on a sampled subset of data.

Lakehouse validation also includes performance evidence: the tables are tuned for the queries the business actually runs, and the queries finish within their SLOs. Without this evidence, a "lakehouse" degrades into a slow lake: data is technically there but practically unusable.

## Failure modes and correction

The dominant failure is small files. Streaming ingest produces millions of tiny files that obliterates query performance. The cure is to schedule compaction and to use auto-compaction features where available. A second failure is schema drift. Producers add fields without coordination; silver silently accepts the new fields; gold breaks because a join key has changed shape. The cure is a schema registry with strict compatibility checks and a CI gate that rejects incompatible changes.

A third failure is bronze becoming a dump. Bronze is preserved indefinitely under the medallion promise, but the cost of storing everything forever is real. The cure is tiered storage: bronze in cold storage with lifecycle policies, silver in warm storage with retention, gold in hot storage. A fourth failure is gold tables drifting from the business definition. A "daily revenue" table has been computed differently for two months because no one owns the gold layer's semantics. The cure is to assign ownership of each gold table and to record the business definition alongside the table.

A fifth failure is the medallion architecture turning into a swamp of intermediate tables. Every analyst's ad hoc silver table becomes part of the pipeline; no one knows which tables are authoritative. The cure is governance: a registry of silver and gold tables with owners, SLAs, and deprecation policies.

## Limitations

The lakehouse pattern requires operational maturity. A team that does not have a working data platform will not magically gain one by adopting the medallion architecture; they will simply have an empty lakehouse. The pattern also requires a query engine that understands the table format; running Spark against Delta on one cluster and Trino against Iceberg on another is fine, but running both against the same dataset without careful coordination produces inconsistent reads. The pattern is not a substitute for a data warehouse; for high-concurrency, low-latency BI workloads, a traditional warehouse may still be the right answer. The medallion architecture is also expensive at scale: bronze is preserved forever, silver is recomputed frequently, and gold is replicated across consumers; cost discipline is required to keep the storage and compute from ballooning.

## Canonical sources

- Databricks — *Lakehouse Platform* and the *Medallion Architecture* page on the Databricks documentation site: https://docs.databricks.com/aws/en/lakehouse/medallion/
- Databricks — *Lakehouse Glossary* and product documentation explaining the bronze/silver/gold layering: https://www.databricks.com/glossary/medallion-architecture
- Delta Lake, Apache Iceberg, and Apache Hudi project documentation, the table-format ecosystem that underpins the lakehouse pattern
- Martin Fowler — *Data Lake* bliki entry, on the relationship between data lakes, warehouses, and lakehouses: https://martinfowler.com/bliki/DataLake.html
