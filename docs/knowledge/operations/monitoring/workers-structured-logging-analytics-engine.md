# Structured Logging from Workers to Analytics Engine

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

You need queryable, low-latency logs from Cloudflare Workers without egressing data to a third-party log aggregator. Standard `console.log` output is ephemeral and not queryable. You want to correlate requests by trace ID, filter by log level, and run SQL queries for error rate and p95 latency.

## Context

Cloudflare Analytics Engine provides a write-once time-series data store accessible via the Workers Binding API. Each event accepts up to 20 indexed string fields (`indexes[]`), 20 numeric double fields (`doubles[]`), and a single opaque blob. Writes are fire-and-forget and do not block the response path. Analytics Engine is designed for observability workloads where you write millions of rows and query via the Analytics Engine SQL API (`https://api.cloudflare.com/client/v4/accounts/{account_id}/analytics_engine/sql`).

## Solution

### wrangler.toml binding

```toml
[[analytics_engine_datasets]]
binding = "LOG_DATASET"
dataset = "workers_structured_logs"
```

### Log schema design

```typescript
// src/logger.ts

export type LogLevel = 'debug' | 'info' | 'warn' | 'error';

export interface LogRecord {
  level: LogLevel;
  message: string;
  correlationId: string;
  service: string;
  route?: string;
  statusCode?: number;
  durationMs?: number;
  errorCode?: string;
  userId?: string;
}

// Analytics Engine field layout (indexes = strings, doubles = numbers)
// indexes[0]  => log level
// indexes[1]  => correlation ID
// indexes[2]  => service name
// indexes[3]  => route
// indexes[4]  => error code
// indexes[5]  => user ID
// doubles[0]  => status code (HTTP)
// doubles[1]  => duration in milliseconds
// blob        => full JSON message payload

export function buildDataPoint(
  record: LogRecord
): AnalyticsEngineDataPoint {
  return {
    indexes: [
      record.level,
      record.correlationId,
      record.service,
      record.route ?? '',
      record.errorCode ?? '',
      record.userId ?? '',
    ],
    doubles: [
      record.statusCode ?? 0,
      record.durationMs ?? 0,
    ],
    blobs: [
      JSON.stringify({ message: record.message, ts: Date.now() }),
    ],
  };
}
```

### Logger class with level filtering and batch writes

```typescript
// src/logger.ts (continued)

const LEVEL_RANK: Record<LogLevel, number> = {
  debug: 0,
  info: 1,
  warn: 2,
  error: 3,
};

export class StructuredLogger {
  private queue: AnalyticsEngineDataPoint[] = [];
  private minLevel: LogLevel;

  constructor(
    private dataset: AnalyticsEngineDataset,
    private defaults: Pick<LogRecord, 'service' | 'correlationId'>,
    minLevel: LogLevel = 'info'
  ) {
    this.minLevel = minLevel;
  }

  private enqueue(record: LogRecord) {
    if (LEVEL_RANK[record.level] < LEVEL_RANK[this.minLevel]) return;
    this.queue.push(buildDataPoint(record));
  }

  debug(message: string, extras?: Partial<LogRecord>) {
    this.enqueue({ ...this.defaults, ...extras, level: 'debug', message });
  }

  info(message: string, extras?: Partial<LogRecord>) {
    this.enqueue({ ...this.defaults, ...extras, level: 'info', message });
  }

  warn(message: string, extras?: Partial<LogRecord>) {
    this.enqueue({ ...this.defaults, ...extras, level: 'warn', message });
  }

  error(message: string, extras?: Partial<LogRecord>) {
    this.enqueue({ ...this.defaults, ...extras, level: 'error', message });
  }

  // Call flush() in ctx.waitUntil() so writes don't block response
  flush(): void {
    for (const point of this.queue) {
      this.dataset.writeDataPoint(point);
    }
    this.queue = [];
  }
}
```

### Request correlation ID propagation

```typescript
// src/index.ts

import { StructuredLogger } from './logger';

interface Env {
  LOG_DATASET: AnalyticsEngineDataset;
}

function getOrCreateCorrelationId(request: Request): string {
  return (
    request.headers.get('x-correlation-id') ??
    request.headers.get('x-request-id') ??
    crypto.randomUUID()
  );
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const correlationId = getOrCreateCorrelationId(request);
    const start = Date.now();

    const logger = new StructuredLogger(
      env.LOG_DATASET,
      { service: 'api-gateway', correlationId },
      'info'
    );

    logger.info('request received', {
      route: new URL(request.url).pathname,
    });

    let response: Response;
    try {
      response = await handleRequest(request, env, logger);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'unknown error';
      logger.error('unhandled exception', {
        errorCode: 'UNHANDLED_EXCEPTION',
        message,
        statusCode: 500,
        durationMs: Date.now() - start,
      });
      response = new Response('Internal Server Error', { status: 500 });
    }

    logger.info('request complete', {
      statusCode: response.status,
      durationMs: Date.now() - start,
      route: new URL(request.url).pathname,
    });

    // Flush after response is sent
    ctx.waitUntil(Promise.resolve(logger.flush()));

    return response;
  },
} satisfies ExportedHandler<Env>;

async function handleRequest(
  request: Request,
  env: Env,
  logger: StructuredLogger
): Promise<Response> {
  logger.debug('entering handleRequest');
  // business logic here
  return new Response('OK', { status: 200 });
}
```

### SQL query examples

```sql
-- Error rate over the last 1 hour
SELECT
  toStartOfInterval(timestamp, INTERVAL '5' MINUTE) AS bucket,
  countIf(index1 = 'error') AS errors,
  count() AS total,
  round(countIf(index1 = 'error') / count() * 100, 2) AS error_rate_pct
FROM workers_structured_logs
WHERE timestamp > NOW() - INTERVAL '1' HOUR
  AND index3 = 'api-gateway'
GROUP BY bucket
ORDER BY bucket DESC;

-- p95 latency per route (last 24 hours)
SELECT
  index4 AS route,
  quantileExact(0.50)(double2) AS p50_ms,
  quantileExact(0.95)(double2) AS p95_ms,
  quantileExact(0.99)(double2) AS p99_ms,
  count() AS requests
FROM workers_structured_logs
WHERE timestamp > NOW() - INTERVAL '24' HOUR
  AND index1 IN ('info', 'warn', 'error')
  AND double2 > 0
GROUP BY route
ORDER BY p95_ms DESC
LIMIT 20;

-- Trace reconstruction by correlation ID
SELECT
  timestamp,
  index1 AS level,
  index3 AS service,
  index4 AS route,
  double1 AS status_code,
  double2 AS duration_ms,
  blob1 AS payload
FROM workers_structured_logs
WHERE index2 = 'YOUR-CORRELATION-ID'
ORDER BY timestamp ASC;
```

## Implementation Details

- **Index field mapping**: Analytics Engine `index1` corresponds to `indexes[0]` in the binding API. Confirm the 1-based offset in SQL vs 0-based in the DataPoint object.
- **Blob size limit**: The single blob field is capped at 5 KB. Keep structured metadata in index/double fields and put large payloads (stack traces) in the blob.
- **Write throughput**: Each Worker invocation can write up to 25 data points per request. For high-throughput services, use the batch queue pattern above rather than writing on every log call.
- **Retention**: Analytics Engine retains data for 90 days by default. Plan archival to R2 for longer retention requirements.
- **Cost**: Writes are billed per data point written. Avoid debug-level writes in production unless behind an environment variable gate.

## Anti-patterns

- **Blocking on write**: Never `await dataset.writeDataPoint()` — it returns void and is fire-and-forget by design. Awaiting it adds unnecessary latency.
- **Logging inside loops**: Accumulate log context and emit a single summary log per loop, not one per iteration.
- **Storing PII in indexed fields**: Indexed fields appear directly in SQL. Store hashed or anonymised identifiers; put raw PII only in encrypted blobs if at all.
- **Skipping `ctx.waitUntil`**: Without `ctx.waitUntil`, the Worker runtime may terminate before writes are flushed when using deferred logging.

## Gotchas

- Analytics Engine SQL does not support `JOIN`. Cross-reference log data with D1 in application code, not in the query layer.
- `timestamp` in Analytics Engine is set by the runtime at write time; you cannot backfill historical data with a custom timestamp.
- The dataset name in `wrangler.toml` must match the dataset queried via the REST API exactly (case-sensitive).
- `quantileExact` is available; `percentile` syntax from standard SQL is not.

## Verification

```bash
# Send a test request and check for the log
curl -X GET https://your-worker.example.com/ping \
  -H 'x-correlation-id: test-corr-001'

# Query Analytics Engine via REST API
curl -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "SELECT * FROM workers_structured_logs WHERE index2 = \'test-corr-001\' LIMIT 10"}'
```

## Related

- `documentation/docs/policies/monitoring/workers-anomaly-detection-analytics-engine.md`
- `documentation/docs/policies/monitoring/workers-distributed-trace-propagation.md`
- `documentation/docs/policies/monitoring/workers-error-budget-tracking-d1.md`

## Sources

- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- https://developers.cloudflare.com/workers/runtime-apis/bindings/analytics-engine/
