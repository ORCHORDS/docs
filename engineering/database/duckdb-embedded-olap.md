# DuckDB — Embedded OLAP Analytics

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your team runs ad-hoc analytical queries against Parquet/CSV/JSON files by
spinning up a Spark cluster or loading data into a data warehouse. The
feedback loop is slow, the infrastructure is expensive, and local development
requires a network connection to the analytics stack.

## Context

DuckDB is an in-process SQL OLAP database that runs inside your application
(Python, Node.js, Rust, Go, Java, R, or CLI). It is the SQLite of analytics
— zero external dependencies, no server, columnar storage, vectorized
execution. It processes analytical queries on local files at speeds that
rival dedicated warehouses for datasets that fit on a single machine.

## When to use DuckDB

- **Local analytics** — query Parquet, CSV, JSON, or Arrow files without
  loading into a remote warehouse.
- **Per-tenant SaaS reporting** — embed DuckDB in your API to generate
  reports without a shared analytics cluster.
- **dbt development** — run dbt models locally against DuckDB instead of
  waiting for cloud warehouse slots.
- **ETL pipeline prototyping** — test transformation logic on local data
  before deploying to production.
- **Log analysis** — query structured logs without centralized infra.
- **Data exploration** — interactive SQL in Jupyter notebooks with sub-second
  response on millions of rows.

## When NOT to use DuckDB

- **High-concurrency OLTP** — DuckDB is single-writer; not designed for
  concurrent transactional workloads.
- **Multi-node distributed queries** — single-machine only (MotherDuck
  offers a managed cloud layer, but the core engine is single-node).
- **Real-time streaming ingestion** — DuckDB is batch-oriented; use
  ClickHouse or Kafka + materialized views for streaming.
- **Datasets exceeding available RAM + disk** — DuckDB spills to disk but
  performance degrades beyond what one machine can handle.

## Key capabilities

```sql
-- Query Parquet files directly (no COPY/LOAD step)
SELECT region, SUM(revenue) FROM 's3://bucket/sales/*.parquet'
WHERE year = 2026 GROUP BY region;

-- Query CSV with auto-detection
SELECT * FROM read_csv_auto('logs.csv') WHERE status >= 400;

-- Attach and query a remote Postgres database
ATTACH 'dbname=prod host=db.example.com' AS pg (TYPE POSTGRES);
SELECT * FROM pg.public.orders WHERE created_at > '2026-01-01';

-- Export results to Parquet
COPY (SELECT * FROM analysis) TO 'output.parquet' (FORMAT PARQUET);
```

## DuckDB vs ClickHouse

| Dimension | DuckDB | ClickHouse |
|---|---|---|
| Deployment | Embedded / in-process | Client-server |
| Concurrency | Single-writer, few readers | High-concurrency reads |
| Scaling | Single-node | Distributed cluster |
| Best for | Local analytics, embedded | Production dashboards, streaming |
| Latency at 1B rows | Seconds (single machine) | Sub-second (distributed) |

## Gotchas

- **Single-writer lock** — only one process can write to a DuckDB file at a
  time. Design multi-process workflows around this constraint.
- **Not a Postgres replacement** — DuckDB speaks SQL but is not
  transaction-oriented. Don't use it as your application's primary database.
- **Memory pressure on large joins** — DuckDB spills to disk, but
  performance cliffs are real. Monitor `temp_directory` size.
- **Extension ecosystem is young** — spatial, full-text search, and some
  format readers are extensions that may lag behind the core release cycle.
- **MotherDuck (cloud) is a separate product** — the open-source DuckDB is
  strictly local; cloud collaboration requires the commercial offering.

## Verification

- `SELECT * FROM duckdb_settings()` — confirm memory limit and threads.
- Benchmark your actual analytical queries against your current stack.
- Test file format compatibility (Parquet version, compression codecs).
- Verify disk spill behavior with datasets 2-3x your RAM.

## Related

- `documentation/categories/database/clickhouse-analytics.md`
- `documentation/categories/database/query-plan-optimization.md`
- `documentation/categories/database/sqlite-d1-patterns.md`
- `documentation/categories/patterns/agent-context-engineering-2026.md`

## Source URLs (verified 2026-08-16)

- Embedded databases in 2026: DuckDB, SQLite, Polars — https://kestra.io/blogs/embedded-databases
- DuckDB embedded analytics 2026 — https://blog.nepexgroup.com/databases/analytics/2026/05/09/duckdb-embedded-analytics-modern-applications.html
- DuckDB vs ClickHouse 2026 — https://siliconpin.com/topics/duckdb-vs-clickhouse-why-modern-data-teams-are-rethinking-analytics-infrastructure-in-2026
- The enterprise case for DuckDB — https://motherduck.com/blog/duckdb-enterprise-5-key-categories/
- What is DuckDB — https://motherduck.com/learn/what-is-duckdb/
