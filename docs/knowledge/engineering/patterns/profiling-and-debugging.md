# profiling-and-debugging

**Issue:** Profile slow code, debug production issues
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your code is slow. You look at the code. It looks fine. You
add a `console.log("here")`. The log shows up. You move
it. The log shows up later. The bug is in some other part
of the code. You spend 4 hours finding it. You wish you'd
had a profiler.

## Root cause
**Console.log debugging works but is slow.** A profiler
shows you exactly where time is spent, with no manual
instrumentation.

**Source:** Chrome DevTools Performance:
https://developer.chrome.com/docs/devtools/performance/

## The "profiling" toolset

### Chrome DevTools (browser)
For frontend code, Chrome DevTools has a Performance tab
that records CPU usage, JS execution, layout, paint, and
network.

```ts
// Add a marker
performance.mark('start-render');
// ... do work ...
performance.mark('end-render');
performance.measure('render', 'start-render', 'end-render');

// In DevTools, you see the measure
```

### Node.js profiler (backend)
For Node.js, use `--prof` flag or clinic.js:
```bash
node --prof dist/index.js
# Generates isolate-*.log
node --prof-process isolate-*.log > profile.txt
# Profile report
```

Or use clinic.js (more user-friendly):
```bash
clinic doctor -- node dist/index.js
clinic flame -- node dist/index.js
```

### CF Workers profiler
For CF Workers, the built-in profiler is in the dashboard:
- `wrangler dev` shows real-time CPU usage
- Production traces via Workers Analytics Engine
- Flame graphs in the CF dashboard

### Datadog / Honeycomb (production)
For production profiling, use a distributed tracing tool:
- Datadog APM
- Honeycomb
- New Relic

These show you the slow path across services.

## The "flame graph" pattern

A flame graph shows where time is spent:
```
Total: 1000ms
  - getUser: 800ms (80%)
    - DB query: 700ms (70% of total)
    - serialize: 50ms (5%)
    - parse: 50ms (5%)
  - logging: 100ms (10%)
  - other: 100ms (10%)
```

The wide bar shows the function; nested bars show its
callees. The widest bar is the bottleneck.

## The "CPU profile" pattern

For CPU-bound code:
```ts
// In a Worker
import { performance } from 'perf_hooks';

const t0 = performance.now();
const user = await db.query(...);
const t1 = performance.now();
console.log({ msg: 'db.query.duration_ms', duration: t1 - t0 });
```

In the CF dashboard, the durations aggregate across all
requests. The p99 is the worst-case.

## The "memory profile" pattern

For memory leaks:
```ts
// In Node.js
const used = process.memoryUsage();
console.log({ msg: 'memory.used', rss: used.rss, heapUsed: used.heapUsed });
```

In Chrome DevTools, the Memory tab shows heap snapshots. Take
two snapshots; compare. The growth is the leak.

## The "DB query profile" pattern

For slow DB queries, use the query planner:
```sql
EXPLAIN QUERY PLAN
SELECT * FROM users WHERE tenant_id = 't_123' AND email = 'a@x.test';
```

The plan shows:
- Which index is used
- The join order
- The estimated row count

If the plan says "FULL SCAN" on a 1M-row table, you need an
index.

For D1, EXPLAIN is supported.

## The "network profile" pattern

For slow network calls, use the Network tab in DevTools:
- The waterfall shows every request
- The size, time, and headers are visible
- Slow requests are highlighted

For production, use a tool that captures network traces
(Datadog, Sentry).

## The "hot path" identification

The hot path is the code that runs most often. Optimizing
the hot path has the biggest impact.

```ts
// Hot path: the inner loop
for (let i = 0; i < 1_000_000; i++) {
  // ... this runs 1M times; any optimization here is multiplied
}

// Cold path: error handling
try {
  // ... main code
} catch (err) {
  // ... this rarely runs
}
```

Optimize the hot path. Don't optimize the cold path.

## The "early return" pattern

For performance, return early:
```ts
// ❌ Bad: nested checks
function processUser(user: User) {
  if (user) {
    if (user.email) {
      if (user.isActive) {
        // ... do work
      }
    }
  }
}

// ✅ Good: early returns
function processUser(user: User) {
  if (!user) return;
  if (!user.email) return;
  if (!user.isActive) return;
  // ... do work
}
```

The early return reduces nesting and short-circuits faster.

## The "memoize" pattern

For pure functions with expensive computation:
```ts
const cache = new Map();

function expensiveOperation(input: string): number {
  if (cache.has(input)) return cache.get(input)!;

  const result = /* expensive computation */;
  cache.set(input, result);
  return result;
}
```

For per-request caching:
```ts
const perRequestCache = new Map();
async function handle(request: Request) {
  const cacheKey = new URL(request.url).pathname;
  if (perRequestCache.has(cacheKey)) return perRequestCache.get(cacheKey);

  const result = await expensiveOperation(cacheKey);
  perRequestCache.set(cacheKey, result);
  return result;
}
```

⚠️ **Memory leak risk:** Don't cache forever; cap the size.

## The "bottleneck" identification

The bottleneck is the slowest part. To find it:
1. **Measure end-to-end:** Total request time
2. **Measure each step:** DB, vendor, serialization, etc.
3. **Find the slowest step**
4. **Optimize the slowest step**
5. **Repeat**

The bottleneck moves as you optimize. The DB might be slow
now, but after you optimize the DB, the vendor API is the
new bottleneck.

## The "off-the-hot-path" pattern

For non-critical work, move it off the hot path:
```ts
// Hot path: response must include the user
const user = await db.getUser(userId);

// Off the hot path: analytics
ctx.waitUntil(sendAnalytics({ event: 'page_view', userId }));

// Hot path: log only the critical info
console.log({ msg: 'request', duration });

// Off the hot path: detailed log
ctx.waitUntil(flushLogs());
```

`ctx.waitUntil` runs after the response is sent. The user
doesn't wait for it.

## The "production debugging" anti-patterns

### 1. console.log in production
- **Issue:** A console.log can leak PII or secrets
- **Fix:** Use structured logging; mask PII

### 2. debugger in production
- **Issue:** `debugger` statements pause execution; in
  production, they may break the request
- **Fix:** Use logging + tracing; never use `debugger` in
  production

### 3. Hot-fixing in production
- **Issue:** You deploy a "fix" to production directly
- **Fix:** Always go through staging + CI

### 4. Sledgehammer "fixes"
- **Issue:** You add retries on everything to "fix"
  slowness
- **Fix:** Find the bottleneck; fix the cause

## Verification
- **Test:** `test/performance.test.ts > hot path is < 10ms` —
  passes
- **Live:** p99 latency is monitored
- **Audit:** Quarterly perf review

## Gotchas
- **Premature optimization is the root of all evil.** Don't
  optimize code that isn't on the hot path. Measure first.
- **The "fast code is always better" anti-pattern.** Fast
  code that's wrong is worse than slow code that's right.
- **The "single-threaded" assumption.** JS is single-threaded
  per isolate, but Workers are multi-isolate. CPU-bound
  code is per-isolate; I/O-bound is shared.
- **The "profile is the source of truth."** Don't optimize
  based on intuition; optimize based on data.
- **The "fast in dev, slow in prod" anti-pattern.** Dev
  has no network, no DB contention. Profile in production-
  like conditions.

## Related
- `observability-three-pillars-detail.md`
- `load-testing.md`
- `error-budget-slo.md`
- `safe-deploy-checklist.md`
- Chrome DevTools: https://developer.chrome.com/docs/devtools/performance/
- Clinic.js: https://clinicjs.org/
- CF profiling: https://developers.cloudflare.com/workers/observability/dev-tools/
