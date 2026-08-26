# Time-Series Databases — TimescaleDB, InfluxDB, and Query Patterns

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your application stores time-stamped data (metrics, IoT sensor readings,
financial ticks, logs) in a general-purpose relational database, and
queries are slowing down as the table grows into hundreds of millions of
rows. Aggregation queries over time ranges take minutes. You need
downsampling, retention policies, and continuous aggregates, but
implementing them in PostgreSQL or MySQL requires custom cron jobs and
complex partitioning. Time-based queries dominate your workload but your
database is not optimized for them.

## Context

Time-series databases (TSDBs) are purpose-built for workloads where data
is primarily written as time-stamped records and queried over time
ranges. They optimize for high-throughput ingestion, time-range scans,
automatic partitioning by time, built-in downsampling, and retention
policies. In 2026, the two most adopted TSDBs are TimescaleDB (extends
PostgreSQL with hypertables) and InfluxDB (purpose-built TSDB with its
own query language). The most common 2026 pattern is augmentation, not
replacement: InfluxDB handles real-time alerting with sub-millisecond
response, data flows through Kafka to ClickHouse for historical
analytics, while TimescaleDB handles transactional control systems
alongside time-series data.

## When to use a TSDB

```
Use a TSDB when:
  → Data is append-mostly (writes >> updates)
  → Queries are time-range-based (last hour, last 7 days)
  → You need automatic data lifecycle (retention, downsampling)
  → Ingestion rate is high (100K+ writes/sec)
  → Aggregation over time windows is the primary query pattern

Stay with PostgreSQL/MySQL when:
  → Time-series is a small part of the workload
  → You need complex joins with relational data
  → Write volume is low (<10K writes/sec)
  → Data requires frequent updates/deletes
```

## Comparison

| Feature | TimescaleDB | InfluxDB 3.0 | QuestDB |
|---|---|---|---|
| Base | PostgreSQL extension | Purpose-built (Apache DataFusion) | Custom (zero-GC Java + C++) |
| Query language | SQL | SQL (InfluxQL deprecated) | SQL |
| Joins | Full PostgreSQL joins | Limited | Limited |
| Ingestion | 100K-1M rows/sec | 1M+ rows/sec | 1M+ rows/sec |
| Compression | 90-95% | 90%+ columnar | 95%+ |
| Scale-to-zero | No | Cloud tier yes | No |
| Best for | SQL teams, relational + time-series | Pure metrics/IoT, real-time alerting | High-frequency financial data |

## TimescaleDB patterns

### Hypertable creation

```sql
-- Create a regular PostgreSQL table
CREATE TABLE metrics (
  time        TIMESTAMPTZ NOT NULL,
  device_id   TEXT NOT NULL,
  temperature DOUBLE PRECISION,
  humidity    DOUBLE PRECISION,
  battery     DOUBLE PRECISION
);

-- Convert to a hypertable (auto-partitions by time)
SELECT create_hypertable('metrics', by_range('time'));

-- Optional: add space partitioning for high-cardinality device_id
SELECT add_dimension('metrics', by_hash('device_id', 4));

-- Compression policy: compress chunks older than 7 days
ALTER TABLE metrics SET (
  timescaledb.compress,
  timescaledb.compress_segmentby = 'device_id',
  timescaledb.compress_orderby = 'time DESC'
);

SELECT add_compression_policy('metrics', INTERVAL '7 days');
```

### Continuous aggregates

```sql
-- Pre-compute hourly averages (materialized automatically)
CREATE MATERIALIZED VIEW metrics_hourly
WITH (timescaledb.continuous) AS
SELECT
  time_bucket('1 hour', time) AS bucket,
  device_id,
  AVG(temperature) AS avg_temp,
  MAX(temperature) AS max_temp,
  MIN(temperature) AS min_temp,
  AVG(humidity) AS avg_humidity,
  COUNT(*) AS sample_count
FROM metrics
GROUP BY bucket, device_id;

-- Refresh policy: update aggregate every 30 minutes
SELECT add_continuous_aggregate_policy('metrics_hourly',
  start_offset    => INTERVAL '3 hours',
  end_offset      => INTERVAL '1 hour',
  schedule_interval => INTERVAL '30 minutes'
);

-- Query the aggregate (fast — reads pre-computed data)
SELECT * FROM metrics_hourly
WHERE device_id = 'sensor-42'
  AND bucket >= NOW() - INTERVAL '7 days'
ORDER BY bucket DESC;
```

### Retention policy

```sql
-- Automatically drop data older than 90 days
SELECT add_retention_policy('metrics', INTERVAL '90 days');

-- Keep raw data 30 days, hourly aggregates 1 year
SELECT add_retention_policy('metrics', INTERVAL '30 days');
SELECT add_retention_policy('metrics_hourly', INTERVAL '365 days');
```

## InfluxDB 3.0 patterns

### Write (line protocol)

```
# Line protocol format: measurement,tags fields timestamp
cpu,host=server01,region=us-east usage=72.5,idle=27.5 1692201622000000000
mem,host=server01 used=8589934592,total=17179869184 1692201622000000000

# Write via API
curl -X POST "http://localhost:8086/api/v2/write?bucket=metrics" \
  -H "Authorization: Token $INFLUX_TOKEN" \
  -H "Content-Type: text/plain" \
  --data-raw 'cpu,host=server01 usage=72.5 1692201622000000000'
```

### Query (SQL)

```sql
-- InfluxDB 3.0 uses SQL (Apache DataFusion engine)
SELECT
  date_bin('1 hour', time) AS hour,
  host,
  AVG(usage) AS avg_usage,
  MAX(usage) AS max_usage
FROM cpu
WHERE time >= NOW() - INTERVAL '24 hours'
GROUP BY hour, host
ORDER BY hour DESC;
```

### Client SDK (Python)

```python
from influxdb_client_3 import InfluxDBClient3

client = InfluxDBClient3(
    host="https://us-east-1-1.aws.cloud2.influxdata.com",
    token=os.environ["INFLUX_TOKEN"],
    database="metrics",
)

# Write
client.write_file("data.csv", measurement_name="sensors")

# Query
table = client.query("SELECT * FROM cpu WHERE time > NOW() - INTERVAL '1 hour'")
df = table.to_pandas()
```

## Common query patterns

```sql
-- Last known value per device
SELECT DISTINCT ON (device_id)
  device_id, time, temperature
FROM metrics
ORDER BY device_id, time DESC;

-- Gap detection (missing readings)
SELECT
  time_bucket_gapfill('5 minutes', time) AS bucket,
  device_id,
  AVG(temperature) AS avg_temp
FROM metrics
WHERE time >= NOW() - INTERVAL '1 day'
  AND device_id = 'sensor-42'
GROUP BY bucket, device_id;

-- Rate of change
SELECT
  time,
  temperature - LAG(temperature) OVER (
    PARTITION BY device_id ORDER BY time
  ) AS temp_change
FROM metrics
WHERE device_id = 'sensor-42';

-- Percentile over time windows
SELECT
  time_bucket('1 hour', time) AS hour,
  percentile_cont(0.95) WITHIN GROUP (ORDER BY response_time) AS p95,
  percentile_cont(0.99) WITHIN GROUP (ORDER BY response_time) AS p99
FROM requests
GROUP BY hour;
```

## Anti-patterns

- **Using a TSDB for OLTP workloads** — time-series databases are
  optimized for append-mostly writes and time-range reads. Using
  them for transactional updates, deletes, or complex relational
  queries produces poor performance. Keep OLTP in PostgreSQL/MySQL.
- **High-cardinality tags** — using unique identifiers (user IDs,
  request IDs, session IDs) as tags/labels in InfluxDB or Prometheus
  causes index explosion. Tags should be low-cardinality dimensions
  (region, service name, host). Store high-cardinality values as
  fields, not tags.
- **No retention policy** — allowing time-series data to grow
  indefinitely. Raw sensor data at 1-second intervals generates
  86,400 rows per device per day. Set retention policies and use
  continuous aggregates to keep summaries of old data.
- **Querying raw data for dashboards** — running real-time aggregation
  queries on billions of raw rows for every dashboard load. Use
  continuous aggregates or materialized views to pre-compute the
  data dashboards need.

## Gotchas

- **TimescaleDB chunk size** — the default chunk interval (7 days)
  may not be optimal for your write rate. Too-large chunks slow
  compression and retention; too-small chunks create excessive
  metadata overhead. Tune based on your data volume.
- **InfluxDB 3.0 migration** — InfluxDB 3.0 is a ground-up rewrite
  using Apache DataFusion. InfluxQL is deprecated in favor of SQL.
  Existing Flux queries do not work in 3.0. Plan migration
  carefully.
- **Compression trade-offs** — compressed TimescaleDB chunks are
  read-only (inserts and updates are blocked). Ensure your
  compression policy gives enough buffer for late-arriving data.
- **Cross-database joins** — if time-series data lives in InfluxDB
  but relational data lives in PostgreSQL, joins require ETL or
  application-level logic. TimescaleDB avoids this by being a
  PostgreSQL extension (same database, same joins).

## Verification

- Time-series data uses a purpose-built TSDB or TimescaleDB extension.
- Continuous aggregates pre-compute common dashboard queries.
- Retention policies drop raw data after the defined window.
- Compression is enabled for chunks older than the write buffer.
- Tags/labels are low-cardinality; high-cardinality data uses fields.
- Ingestion throughput is benchmarked under expected load.

## Related

- `documentation/categories/monitoring/opentelemetry-collector-pipelines.md`
- `documentation/categories/performance/api-rate-limiting-algorithms.md`
- `documentation/categories/database/postgresql-row-level-security-multi-tenant.md`

## Source URLs (verified 2026-08-16)

- Time-Series Database Patterns: InfluxDB and TimescaleDB — https://medium.com/@artemkhrenov/time-series-database-patterns-influxdb-and-timescaledb-for-analytics-32daf132297f
- Best Time Series Databases for Real Time Workloads in 2026 — https://cratedb.com/blog/best-time-series-databases
- Best Time-Series Databases in 2026 and How to Choose — https://questdb.com/blog/best-time-series-databases/
- ClickHouse vs TimescaleDB vs InfluxDB 2026 Benchmarks — https://sanj.dev/post/clickhouse-timescaledb-influxdb-time-series-comparison/
