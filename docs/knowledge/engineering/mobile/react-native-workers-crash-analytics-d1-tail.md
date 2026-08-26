# React Native Workers Crash Analytics with D1 and Tail Workers

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

You want to capture React Native JS crashes, unhandled promise rejections, and native
exceptions, then funnel them through Cloudflare Tail Workers into D1 for long-term
storage and query without paying for a third-party crash service. You need stack traces
symbolicated server-side, grouped by bundle version, and queryable via SQL.

---

## Context

Cloudflare Tail Workers receive a stream of every invocation log and exception from
Workers in the same account. Combined with a dedicated crash-ingestion Worker, you can:
1. Accept symbolicated or raw crash payloads from the mobile app.
2. Write them to D1 via the Tail Worker.
3. Query crash frequency, impacted users, and error messages with standard SQL.

Stack:
- React Native 0.75+ (New Architecture)
- Cloudflare Workers (TypeScript) + D1 + Tail Workers

---

## 1. Global JS Error Boundary and Crash Handler (React Native)

```typescript
// src/crashReporter.ts
import { ErrorUtils } from 'react-native'

const CRASH_ENDPOINT = 'https://api.example.com/crashes'

interface CrashPayload {
  type: 'js_error' | 'unhandled_rejection' | 'native_crash'
  message: string
  stack: string | null
  bundleVersion: string
  platform: 'ios' | 'android'
  deviceModel: string
  osVersion: string
  sessionId: string
  timestamp: string
}

async function sendCrash(payload: CrashPayload): Promise<void> {
  try {
    await fetch(CRASH_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      keepalive: true,  // survives page unload / app background
    })
  } catch {
    // Fire-and-forget — do not throw on crash reporting failure
  }
}

export function initCrashReporter(sessionId: string) {
  const previousHandler = ErrorUtils.getGlobalHandler()

  ErrorUtils.setGlobalHandler((error: Error, isFatal?: boolean) => {
    sendCrash({
      type: 'js_error',
      message: error.message,
      stack: error.stack ?? null,
      bundleVersion: require('../package.json').version,
      platform: require('react-native').Platform.OS,
      deviceModel: require('react-native-device-info').getModel(),
      osVersion: require('react-native-device-info').getSystemVersion(),
      sessionId,
      timestamp: new Date().toISOString(),
    })
    if (isFatal) previousHandler(error, isFatal)
  })

  // Unhandled promise rejections
  const tracking = require('promise/setimmediate/rejection-tracking')
  tracking.enable({
    allRejections: true,
    onUnhandled: (_id: number, error: unknown) => {
      const err = error instanceof Error ? error : new Error(String(error))
      sendCrash({
        type: 'unhandled_rejection',
        message: err.message,
        stack: err.stack ?? null,
        bundleVersion: require('../package.json').version,
        platform: require('react-native').Platform.OS,
        deviceModel: require('react-native-device-info').getModel(),
        osVersion: require('react-native-device-info').getSystemVersion(),
        sessionId,
        timestamp: new Date().toISOString(),
      })
    },
  })
}
```

---

## 2. Crash Ingestion Worker

```typescript
// workers/src/crash-ingest.ts
import { Hono } from 'hono'

interface Env {
  CRASHES: D1Database
}

const app = new Hono<{ Bindings: Env }>()

app.post('/crashes', async (c) => {
  const payload = await c.req.json<CrashPayload>()

  // Basic field validation
  if (!payload.message || !payload.type) {
    return c.json({ error: 'invalid_payload' }, 400)
  }

  await c.env.CRASHES.prepare(
    `INSERT INTO crashes
       (type, message, stack, bundle_version, platform, device_model, os_version, session_id, occurred_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`
  ).bind(
    payload.type,
    payload.message.slice(0, 2048),           // guard against enormous strings
    (payload.stack ?? '').slice(0, 16384),
    payload.bundleVersion,
    payload.platform,
    payload.deviceModel,
    payload.osVersion,
    payload.sessionId,
    payload.timestamp,
  ).run()

  return c.json({ ok: true }, 201)
})

// Query endpoint for internal dashboard
app.get('/crashes/summary', async (c) => {
  const { results } = await c.env.CRASHES.prepare(
    `SELECT bundle_version, platform, COUNT(*) AS count, COUNT(DISTINCT session_id) AS impacted_sessions
       FROM crashes
      WHERE occurred_at >= datetime('now', '-7 days')
      GROUP BY bundle_version, platform
      ORDER BY count DESC
      LIMIT 50`
  ).all()
  return c.json(results)
})

interface CrashPayload {
  type: string; message: string; stack: string | null
  bundleVersion: string; platform: string; deviceModel: string
  osVersion: string; sessionId: string; timestamp: string
}

export default app
```

---

## 3. D1 Schema

```sql
-- workers/schema/crashes.sql
CREATE TABLE IF NOT EXISTS crashes (
  id              TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  type            TEXT NOT NULL,
  message         TEXT NOT NULL,
  stack           TEXT,
  bundle_version  TEXT NOT NULL,
  platform        TEXT NOT NULL CHECK (platform IN ('ios', 'android')),
  device_model    TEXT NOT NULL,
  os_version      TEXT NOT NULL,
  session_id      TEXT NOT NULL,
  occurred_at     DATETIME NOT NULL,
  created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_crashes_version   ON crashes(bundle_version);
CREATE INDEX IF NOT EXISTS idx_crashes_occurred  ON crashes(occurred_at);
CREATE INDEX IF NOT EXISTS idx_crashes_session   ON crashes(session_id);
CREATE INDEX IF NOT EXISTS idx_crashes_type      ON crashes(type);
```

---

## 4. Tail Worker — Secondary Fan-out

```typescript
// workers/src/crash-tail.ts
// wrangler.toml: [[tail_consumers]] binding = "crash-ingest"

export default {
  async tail(events: TraceItem[], env: { ANALYTICS: AnalyticsEngineDataset }): Promise<void> {
    for (const event of events) {
      for (const log of event.logs) {
        if (log.level === 'error') {
          // Fan error logs to Analytics Engine for real-time alerting
          env.ANALYTICS.writeDataPoint({
            blobs: [event.scriptName ?? 'unknown', log.message?.[0] ?? ''],
            indexes: [event.outcome],
          })
        }
      }
    }
  },
}
```

---

## 5. Symbolication with Source Maps on Workers

```typescript
// workers/src/symbolicate.ts  (called by crash-ingest before D1 write)
import SourceMap from 'source-map'

interface Env { SOURCE_MAPS: R2Bucket }

export async function symbolicateStack(
  rawStack: string,
  bundleVersion: string,
  env: Env
): Promise<string> {
  const mapKey = `sourcemaps/${bundleVersion}/main.jsbundle.map`
  const obj = await env.SOURCE_MAPS.get(mapKey)
  if (!obj) return rawStack  // no map available, return as-is

  const rawMap = await obj.text()
  const consumer = await new SourceMap.SourceMapConsumer(rawMap)

  const lines = rawStack.split('\n')
  const symbolicated = lines.map((line) => {
    const match = line.match(/:(\d+):(\d+)/)
    if (!match) return line
    const pos = consumer.originalPositionFor({
      line: parseInt(match[1], 10),
      column: parseInt(match[2], 10),
    })
    return pos.source
      ? `${pos.source}:${pos.line}:${pos.column} (${pos.name ?? 'anonymous'})`
      : line
  })

  consumer.destroy()
  return symbolicated.join('\n')
}
```

---

## Anti-patterns

- **Crashing the crash reporter**: wrap all code inside `sendCrash` in try/catch;
  a failure inside the error handler causes an infinite loop or silent swallowing.
- **Synchronous crash sends**: `fetch` with `keepalive: true` is the correct approach;
  using `XMLHttpRequest` synchronously on the main thread blocks the JS runtime.
- **Storing full stack traces in KV**: KV is not queryable by content; use D1 for
  all crash data that needs filtering or aggregation.
- **Missing rate limiting on `/crashes`**: bots can flood D1; add Cloudflare Rate
  Limiting rules or a Workers `RateLimiter` binding.

---

## Gotchas

- React Native New Architecture (JSI) errors may not propagate through
  `ErrorUtils.setGlobalHandler`; also instrument native modules with
  `NativeExceptionHandler` on both platforms.
- D1 has a 100,000 row write limit per day on the Free plan; batch crash writes
  or upgrade to Workers Paid.
- `keepalive: true` is limited to requests with a body ≤64 KB; truncate stack
  traces before sending.
- Tail Workers receive logs asynchronously; there is no guarantee of delivery
  order relative to D1 writes from the primary Worker.

---

## Verification

```bash
# Deploy schema
wrangler d1 execute CRASHES --remote --file workers/schema/crashes.sql

# Send a test crash
curl -X POST https://api.example.com/crashes \
  -H "Content-Type: application/json" \
  -d '{"type":"js_error","message":"Test error","stack":"Error\n  at foo.js:1:1",
       "bundleVersion":"1.2.3","platform":"ios","deviceModel":"iPhone 16",
       "osVersion":"18.1","sessionId":"abc123","timestamp":"2026-08-23T10:00:00Z"}'

# Query crash summary
curl https://api.example.com/crashes/summary

# Verify D1 row count
wrangler d1 execute CRASHES --remote --command "SELECT COUNT(*) FROM crashes"
```

---

## Related

- `mobile-crash-reporting.md`
- `mobile-crash-symbolication.md`
- `mobile-crash-free-rate-slos.md`
- `react-native-hermes-performance-profiling.md`
- `flutter-workers-error-reporting-analytics-engine.md`

---

## Sources

- Cloudflare D1: https://developers.cloudflare.com/d1/
- Cloudflare Tail Workers: https://developers.cloudflare.com/workers/observability/tail-workers/
- Analytics Engine: https://developers.cloudflare.com/analytics/analytics-engine/
- React Native ErrorUtils: https://reactnative.dev/docs/debugging
- source-map npm: https://www.npmjs.com/package/source-map
