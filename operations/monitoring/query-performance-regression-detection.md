# Database Query Performance Regression Detection

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A code change that touches an ORM model, adds a new query, or alters a schema
can silently slow down a query that previously ran in 2 ms to 200 ms. Without
automated detection, the regression surfaces only when users complain about
slowness days or weeks later — long after the causative commit is buried in
history. Teams need a pipeline that catches query performance regressions
before or immediately after deployment, not at the next quarterly performance
review.

## Context

Query performance regression detection differs from general slow query logging
(catching queries that are slow in absolute terms) in one key way: it tracks
*relative change* across deployments. A query taking 150 ms may be acceptable
for a batch job but a regression if it previously ran in 10 ms. The pipeline
requires:

- A **baseline** of query performance at a known good reference point
  (pre-deployment, last release tag, or rolling 7-day average).
- **Query fingerprinting** to group structurally identical queries regardless
  of parameter values.
- **Comparison logic** that flags queries whose p50/p95/p99 latency has
  increased by more than a configured threshold.
- An **output channel** that blocks CI or triggers an alert at deploy time.

This article covers three complementary detection stages: pre-deploy (CI),
canary (real traffic), and post-deploy (continuous).

## Query Fingerprinting

Raw query text includes parameter values, which differ per call. Fingerprinting
normalizes parameters to produce a stable identifier:

```typescript
// fingerprint.ts
export function fingerprintQuery(sql: string): string {
  return sql
    .replace(/\b\d+\b/g, "?")           // numeric literals
    .replace(/'[^']*'/g, "?")            // string literals
    .replace(/\s+/g, " ")               // normalize whitespace
    .trim()
    .toLowerCase();
}

// Examples:
// "SELECT * FROM users WHERE id = 42"
//   -> "select * from users where id = ?"
// "INSERT INTO events (name, value) VALUES ('click', 'button')"
//   -> "insert into events (name, value) values (?, ?)"
```

Store the fingerprint alongside each timing observation. Aggregate by
fingerprint when computing baselines and comparing regressions.

## Stage 1: Pre-deploy Regression Detection in CI

Run your query benchmark suite against a production-replica database (or a
populated staging database) and compare against the stored baseline.

### Benchmark Runner

```typescript
// query-benchmark.ts
import Database from "better-sqlite3";

interface QueryBenchmark {
  name: string;
  sql: string;
  params: unknown[];
  iterations: number;
}

interface BenchmarkResult {
  name: string;
  fingerprint: string;
  p50Ms: number;
  p95Ms: number;
  p99Ms: number;
  iterations: number;
}

export async function runBenchmarks(
  dbPath: string,
  benchmarks: QueryBenchmark[]
): Promise<BenchmarkResult[]> {
  const db = new Database(dbPath);
  const results: BenchmarkResult[] = [];

  for (const bench of benchmarks) {
    const stmt = db.prepare(bench.sql);
    const timings: number[] = [];

    // Warm up
    for (let i = 0; i < 5; i++) stmt.all(...bench.params);

    // Measure
    for (let i = 0; i < bench.iterations; i++) {
      const start = performance.now();
      stmt.all(...bench.params);
      timings.push(performance.now() - start);
    }

    timings.sort((a, b) => a - b);
    results.push({
      name: bench.name,
      fingerprint: fingerprintQuery(bench.sql),
      p50Ms: timings[Math.floor(timings.length * 0.50)],
      p95Ms: timings[Math.floor(timings.length * 0.95)],
      p99Ms: timings[Math.floor(timings.length * 0.99)],
      iterations: bench.iterations,
    });
  }

  db.close();
  return results;
}
```

### Comparison Against Baseline

```typescript
// compare-baselines.ts
interface RegressionReport {
  query: string;
  metric: "p50" | "p95" | "p99";
  baselineMs: number;
  currentMs: number;
  changePercent: number;
}

const REGRESSION_THRESHOLDS = {
  p50: 0.20,   // 20% increase in p50
  p95: 0.30,   // 30% increase in p95
  p99: 0.50,   // 50% increase in p99
};

export function detectRegressions(
  baseline: BenchmarkResult[],
  current: BenchmarkResult[]
): RegressionReport[] {
  const baselineMap = new Map(baseline.map((r) => [r.fingerprint, r]));
  const regressions: RegressionReport[] = [];

  for (const curr of current) {
    const base = baselineMap.get(curr.fingerprint);
    if (!base) continue; // new query, skip

    const checks: Array<["p50" | "p95" | "p99", number, number]> = [
      ["p50", base.p50Ms, curr.p50Ms],
      ["p95", base.p95Ms, curr.p95Ms],
      ["p99", base.p99Ms, curr.p99Ms],
    ];

    for (const [metric, baseMs, currMs] of checks) {
      const change = (currMs - baseMs) / baseMs;
      if (change > REGRESSION_THRESHOLDS[metric]) {
        regressions.push({
          query: curr.name,
          metric,
          baselineMs: baseMs,
          currentMs: currMs,
          changePercent: change * 100,
        });
      }
    }
  }

  return regressions;
}
```

Add a CI step that fails the build if regressions are found:

```yaml
# .github/workflows/query-regression.yml
name: Query Performance Regression
on: [pull_request]

jobs:
  benchmark:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Restore baseline
        run: |
          aws s3 cp s3://ci-artifacts/query-baseline.json ./baseline.json
      - name: Run benchmarks
        run: npx tsx scripts/run-benchmarks.ts --output current.json
      - name: Compare
        run: |
          npx tsx scripts/compare-baselines.ts \
            --baseline baseline.json \
            --current current.json \
            --fail-on-regression
      - name: Update baseline on merge
        if: github.event_name == 'push' && github.ref == 'refs/heads/main'
        run: |
          aws s3 cp ./current.json s3://ci-artifacts/query-baseline.json
```

## Stage 2: Canary Regression Detection (Real Traffic)

The benchmark approach catches known queries. Real traffic surfaces unknown
ones introduced by new code paths. Capture query timings from production and
compare canary vs stable:

### D1 / SQLite Query Timing (Cloudflare Workers)

```typescript
// d1-instrumented.ts
export function wrapD1(db: D1Database, analytics: AnalyticsEngineDataset) {
  return new Proxy(db, {
    get(target, prop) {
      if (prop === "prepare") {
        return (sql: string) => {
          const stmt = target.prepare(sql);
          const fingerprint = fingerprintQuery(sql);

          return new Proxy(stmt, {
            get(stmtTarget, stmtProp) {
              if (stmtProp === "first" || stmtProp === "all" || stmtProp === "run") {
                return async (...args: unknown[]) => {
                  const start = Date.now();
                  const result = await (stmtTarget as any)stmtProp;
                  const durationMs = Date.now() - start;

                  analytics.writeDataPoint({
                    blobs: [fingerprint, String(stmtProp)],
                    doubles: [durationMs],
                    indexes: [fingerprint.slice(0, 64)],
                  });

                  return result;
                };
              }
              return (stmtTarget as any)[stmtProp];
            },
          });
        };
      }
      return (target as any)[prop];
    },
  });
}
```

### Canary Comparison Query

Query Analytics Engine for canary vs stable percentiles:

```sql
-- Compare canary (last 1h) vs stable (previous 24h)
SELECT
  blob1 AS query_fingerprint,
  quantileWeighted(0.95)(double1, 1) AS p95_ms,
  IF(max(timestamp) > now() - INTERVAL '1' HOUR, 'canary', 'stable') AS cohort
FROM analytics_engine_dataset('query_timings')
WHERE timestamp >= now() - INTERVAL '25' HOUR
GROUP BY query_fingerprint, cohort
HAVING count() >= 50
ORDER BY p95_ms DESC
```

## Stage 3: Continuous Post-deploy Monitoring

After full deployment, monitor for regressions that emerge over time due to
data growth or usage pattern changes:

```typescript
// continuous-regression-monitor.ts  (scheduled Worker)
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const regressions = await queryAnalyticsForRegressions(env);

    if (regressions.length > 0) {
      await env.ANALYTICS.writeDataPoint({
        blobs: ["regression_detected", regressions[0].fingerprint],
        doubles: [regressions.length],
        indexes: ["query_regression"],
      });

      await notifySlack(
        env.SLACK_WEBHOOK,
        formatRegressionMessage(regressions)
      );
    }
  },
};

function formatRegressionMessage(
  regressions: Array<{ fingerprint: string; changePercent: number; p95Ms: number }>
): string {
  const lines = regressions
    .slice(0, 5)
    .map(
      (r) =>
        `• \`${r.fingerprint.slice(0, 60)}\` — ` +
        `p95 ${r.p95Ms.toFixed(0)}ms (+${r.changePercent.toFixed(0)}%)`
    );
  return `*Query Performance Regressions Detected*\n${lines.join("\n")}`;
}
```

## Anti-patterns

**Benchmarking on an empty or tiny dataset.** Query plans change dramatically
with data volume. Benchmark against a database seeded with at least 10 % of
production row counts, or use EXPLAIN-based analysis as a proxy.

**Comparing absolute times across different environments.** Staging hardware
differs from production. Use relative % change as the regression signal, not
absolute milliseconds, when comparing across environments.

**Single threshold for all query types.** A 50 % regression on a 2 ms lookup
(now 3 ms) is usually fine. A 50 % regression on a 100 ms report query (now
150 ms) may be fine too. Weight regressions by the query's baseline latency
and call volume.

**Not storing the baseline with schema version.** A schema migration may
legitimately change a query's performance (adding a column, changing an
index). Store the baseline keyed to the schema migration version, not just
a timestamp.

**Alerting on every detected regression continuously.** After a regression is
detected and a ticket is opened, suppress further alerts for that fingerprint
until the ticket is resolved. Implement a suppression list in KV or a
Durable Object.

## Gotchas

- **Warm vs cold query plan cache.** SQLite's page cache is cold after a
  restart. Always warm the cache with a few iterations before measuring.
- **Parameter value cardinality affects plans.** A query for `id = 1` may
  use an index while `id > 1000` causes a full scan. Benchmark with
  parameter values representative of production distributions.
- **D1 row read billing.** Instrumenting every query in production adds
  Analytics Engine write calls. Write data points sampled at 10 % for
  high-frequency queries (> 1,000 calls/min).
- **Flaky baselines from infrastructure events.** If the baseline was recorded
  during a period of I/O contention, it may be artificially high. Sanity-check
  baseline p99 values before treating them as ground truth.

## Verification

1. Introduce a deliberate regression by removing an index on a frequently
   queried column in the benchmark database. Confirm the CI step catches the
   regression and fails.
2. Restore the index. Confirm CI passes and the baseline is updated.
3. Deploy to a canary with the regressed query. Confirm the Analytics Engine
   query identifies the regression within 30 minutes of traffic.
4. Trigger the scheduled monitoring Worker manually and confirm the Slack
   notification includes the correct fingerprint and percentage change.

## Related

- `d1-explain-query-plan-slow-query-automation.md`
- `slow-query-logging.md`
- `database-query-monitoring.md`
- `cloudflare-analytics-engine-custom-metrics.md`
- `deployment-event-tracking.md`

## Sources

- SQLite EXPLAIN QUERY PLAN documentation
- Cloudflare D1 documentation (2025)
- Cloudflare Analytics Engine SQL API documentation
- "Automated Query Performance Regression Detection" — Percona Blog, 2024
- "Database CI/CD: Testing Performance" — PlanetScale Blog, 2024
