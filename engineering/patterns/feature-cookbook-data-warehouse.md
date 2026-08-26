# feature-cookbook-data-warehouse

**Issue:** Data warehouse — analytics, ETL, OLAP
**Date:** 2026-08-09
**Status:** documented

## Symptom
You want to know "how many users signed up in the last
30 days, broken down by country, segmented by source."
You run a SQL query on the production DB. It's slow.
The team complains. You wish you had a data warehouse.

## Root cause
**Production DB is for OLTP, not OLAP.** Use a
warehouse for analytics.

**Source:** Kimball — Data Warehouse Toolkit.

## OLTP vs OLAP

| Aspect | OLTP (DB) | OLAP (Warehouse) |
|---|---|---|
| **Purpose** | Transactions | Analytics |
| **Schema** | Normalized | Star/snowflake |
| **Data** | Current | Historical |
| **Query** | Point lookups | Aggregations |
| **Volume** | Small + frequent | Large + infrequent |

Use a separate warehouse for analytics.

## The "data warehouse" options

- **CF R2 + D1:** Cheap, but limited analytics
- **ClickHouse:** Open-source, fast OLAP
- **Snowflake:** Managed, expensive
- **BigQuery:** Google, serverless
- **Redshift:** AWS, columnar
- **DuckDB:** Embedded, fast

For most apps, **BigQuery or ClickHouse** is the right
balance.

## The "ETL" pattern

For ETL (Extract, Transform, Load):
```ts
// 1. Extract: read from the source
const users = await env.DB!.prepare(
  `SELECT * FROM users WHERE updated_at > ?`
).bind(lastSyncTime).all();

// 2. Transform: clean + reshape
const transformed = users.results.map(user => ({
  user_id: user.id,
  email: user.email.toLowerCase(),
  country: user.country ?? 'unknown',
  signed_up_at: user.created_at,
}));

// 3. Load: write to the warehouse
for (const row of transformed) {
  await warehouse.insert('users', row);
}
```

The data is extracted, transformed, loaded.

## The "incremental" pattern

For incremental sync:
```ts
async function syncUsers(env: Env): Promise<void> {
  // 1. Get the last sync time
  const lastSync = await env.KV.get<string>('last_sync:users');

  // 2. Query only the changed rows
  const query = lastSync
    ? `SELECT * FROM users WHERE updated_at > ?`
    : `SELECT * FROM users`;

  const users = lastSync
    ? await env.DB!.prepare(query).bind(lastSync).all()
    : await env.DB!.prepare(query).all();

  // 3. Sync to the warehouse
  await warehouse.upsert('users', users.results);

  // 4. Update the last sync time
  await env.KV.put('last_sync:users', new Date().toISOString());
}
```

Only the changed rows are synced.

## The "star schema" pattern

For analytics, use a star schema:
```sql
-- Fact table (the events)
CREATE TABLE fact_orders (
  order_id TEXT,
  user_id TEXT,
  product_id TEXT,
  quantity INTEGER,
  total_amount DECIMAL,
  order_date DATE
);

-- Dimension tables (the context)
CREATE TABLE dim_users (
  user_id TEXT,
  country TEXT,
  signup_date DATE,
  source TEXT
);

CREATE TABLE dim_products (
  product_id TEXT,
  category TEXT,
  name TEXT
);

CREATE TABLE dim_dates (
  date DATE,
  year INTEGER,
  month INTEGER,
  day_of_week TEXT
);
```

Star schema = fast aggregations.

## The "data quality" pattern

For data quality:
- **Completeness:** All required fields are present
- **Accuracy:** Values are correct
- **Consistency:** Same data across systems
- **Timeliness:** Data is fresh

```ts
function validateUser(user: any): boolean {
  return user.id && user.email && user.country;
}

const valid = users.filter(validateUser);
const invalid = users.filter(u => !validateUser(u));

if (invalid.length > 0) {
  logEvent('data.invalid', 'warn', { count: invalid.length, sample: invalid[0] });
}
```

The data is validated.

## The "metrics" pattern

For metrics, use the warehouse:
```sql
-- DAU
SELECT
  date(order_date) AS day,
  COUNT(DISTINCT user_id) AS dau
FROM fact_orders
WHERE order_date >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY day
ORDER BY day;

-- Conversion
SELECT
  source,
  COUNT(DISTINCT user_id) AS signups,
  COUNT(DISTINCT CASE WHEN order_id IS NOT NULL THEN user_id END) AS converted
FROM dim_users
LEFT JOIN fact_orders USING (user_id)
GROUP BY source;
```

The warehouse is the source of analytics truth.

## The "CF R2 + ClickHouse" pattern

For a cost-effective setup:
- **CF R2:** Store raw events (Parquet)
- **ClickHouse Cloud:** Query the data
- **CF Worker:** ETL pipeline

```ts
// 1. Write events to R2
const events = await env.R2!.put(`events/${date}.parquet`, parquetBuffer);

// 2. ETL to ClickHouse
async function etlToClickHouse(env: Env): Promise<void> {
  const dates = await getDatesToSync(env);
  for (const date of dates) {
    const obj = await env.R2!.get(`events/${date}.parquet`);
    const rows = parseParquet(obj!.body);
    await clickhouse.insert('events', rows);
  }
}
```

A simple + cheap stack.

## The "BigQuery" pattern

For BigQuery:
```ts
// Insert
await bigQuery.dataset('my_dataset').table('events').insert([
  { user_id: 'u_1', event: 'signup', timestamp: new Date().toISOString() },
]);

// Query
const [rows] = await bigQuery.query(`
  SELECT
    DATE(timestamp) AS day,
    COUNT(DISTINCT user_id) AS users
  FROM events
  WHERE event = 'signup'
  GROUP BY day
  ORDER BY day DESC
  LIMIT 30
`);
```

BigQuery is serverless + scales.

## The "denormalization" pattern

For the warehouse, denormalize:
- **Fact table:** Events, transactions
- **Dimension table:** Users, products, dates

A star schema denormalizes the data.

## The "data retention" pattern

For retention:
- **Production DB:** Keep all data
- **Warehouse:** Hot 90 days, cold 3 years, archive
  > 3 years

```sql
-- Partition by date for fast queries + retention
CREATE TABLE events (
  user_id TEXT,
  event TEXT,
  timestamp TIMESTAMP
)
PARTITION BY DATE(timestamp);
```

Partitioning allows easy retention.

## The "data observability" pattern

For observability:
- **Row count:** How many rows are in the table?
- **Freshness:** When was the last sync?
- **Null rate:** Are required fields filled?
- **Anomalies:** Is the data unusual?

```ts
async function checkDataHealth(warehouse: Warehouse): Promise<void> {
  const rowCount = await warehouse.query(`SELECT COUNT(*) FROM users`);
  const lastSync = await warehouse.query(`SELECT MAX(updated_at) FROM users`);

  if (rowCount < expectedMin) {
    logEvent('data.low_count', 'warn', { table: 'users', count: rowCount });
  }

  if (Date.now() - lastSync > 24 * 60 * 60 * 1000) {
    logEvent('data.stale', 'warn', { table: 'users', lastSync });
  }
}
```

The data health is monitored.

## The "warehouse anti-pattern" anti-patterns

### 1. Analytics on production
- **Issue:** Slow queries, lock contention
- **Fix:** Use a warehouse

### 2. No incremental sync
- **Issue:** Daily full sync is slow
- **Fix:** Incremental sync

### 3. No data quality check
- **Issue:** Bad data in the warehouse
- **Fix:** Validate + alert

### 4. No partitioning
- **Issue:** Queries are slow
- **Fix:** Partition by date

### 5. No retention
- **Issue:** Storage grows forever
- **Fix:** Define retention policy

## Verification
- **Test:** ETL is correct
- **Test:** Data quality is enforced
- **Test:** Queries are fast
- **Live:** Data health is monitored
- **Audit:** Quarterly warehouse review

## Gotchas
- **The "analytics on production" anti-pattern.** Use a
  warehouse.
- **The "no incremental sync" anti-pattern.** Slow
  syncs.
- **The "no data quality check" anti-pattern.** Bad data
  in the warehouse.

## Related
- `feature-cookbook-analytics.md`
- `feature-cookbook-monitoring.md`
- `database-migration-strategy.md`
- `database-index-strategies.md`
- `cost-optimization-cloudflare.md`
- `cloudflare/r2-large-file-patterns.md`
- Kimball: https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/
- BigQuery: https://cloud.google.com/bigquery
- ClickHouse: https://clickhouse.com/
