# Workers Cold Start Regression — Silent Deploy Postmortem

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare Workers deployment introduced a 400ms cold start regression that went undetected for 3 days. End users on infrequently hit routes experienced noticeably higher first-response latency. No alerting fired. No deploy health check caught it. The regression was identified only after a weekly p95 tail-latency review flagged anomalous cold start numbers in Tail Workers telemetry.

---

## Context

The affected Worker handles product detail page rendering for an e-commerce storefront. It uses a WASM image-processing module to generate responsive `srcset` strings server-side. Before the incident, the WASM module was loaded lazily on first use within a request. A routine refactor moved the `WebAssembly.instantiateStreaming` call to module scope to "simplify" initialization and share the instance across requests more cleanly. The intent was reasonable; the effect was not.

Cloudflare Workers isolates are cold-started in a pool before a request arrives, but module-scope top-level `await` still executes during isolate instantiation. A heavy WASM module (1.2 MB, ~380ms parse + compile on first init) moved from lazy to eager initialization directly bloated isolate startup time.

**Stack:**
- Cloudflare Workers (ESM format)
- WASM image module bundled via `wasm` import in `wrangler.toml`
- Tail Workers for observability (custom Analytics Engine sink)
- CI via GitHub Actions + `wrangler deploy`

---

## Incident Timeline

### Day 0 — Deploy

- `14:32 UTC` — PR merged: refactor moves `wasmModule` instantiation from inside request handler to module scope.
- `14:38 UTC` — `wrangler deploy` completes. Canary traffic check passes (HTTP 200s, no error rate spike).
- `14:45 UTC` — Deploy marked healthy. Engineer closes ticket.

### Day 0–2 — Silent regression

- Standard monitors (uptime, error rate, p50 response time on warm requests) show no deviation.
- Cold starts are rare on high-traffic routes; the affected routes are product detail pages for long-tail SKUs hit infrequently.
- Tail Workers are emitting `cf.cold_start` boolean and `duration_ms` but no p95 aggregation alert was configured on cold-start cohort specifically.

### Day 3 — Detection

- `09:15 UTC` — Weekly infra review compares Tail Workers Analytics Engine query:
  ```sql
  SELECT
    quantilesTDigest(0.5, 0.95)(duration_ms) AS percentiles
  FROM tail_events
  WHERE cf_cold_start = true
    AND timestamp > now() - INTERVAL '7 days'
  ```
- p95 cold start: `612ms` (up from `~210ms` the prior week).
- Correlation to deploy confirmed by filtering `timestamp > '2026-08-21 14:38:00'`.

### Day 3 — Remediation

- `10:02 UTC` — Root cause identified: WASM instantiated at module scope.
- `10:45 UTC` — Fix deployed (lazy singleton getter, see below).
- `11:05 UTC` — p95 cold start returns to `208ms` confirmed via Tail Workers.

---

## Root Cause

Moving `WebAssembly.instantiateStreaming(fetch('/wasm/imgproc.wasm'), imports)` to module-scope top-level `await` forced the runtime to compile and instantiate a 1.2 MB WASM binary during every cold isolate start, even for requests that never invoke image processing.

```typescript
// BEFORE (module scope — caused regression)
import wasmUrl from './imgproc.wasm';
const wasmInstance = await WebAssembly.instantiateStreaming(
  fetch(wasmUrl),
  importObject
);

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // wasmInstance already available
    return handleRequest(request, env, wasmInstance);
  }
};
```

---

## Fix — Lazy WASM Init with Singleton Getter

```typescript
// AFTER (lazy singleton — correct pattern)
import wasmUrl from './imgproc.wasm';

let _wasmInstance: WebAssembly.Instance | null = null;

async function getWasm(): Promise<WebAssembly.Instance> {
  if (_wasmInstance) return _wasmInstance;
  const result = await WebAssembly.instantiateStreaming(
    fetch(wasmUrl),
    importObject
  );
  _wasmInstance = result.instance;
  return _wasmInstance;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    // Only pay the WASM cost on routes that need it
    if (url.pathname.startsWith('/img/')) {
      const wasm = await getWasm();
      return handleImageRequest(request, wasm);
    }
    return handleRequest(request, env);
  }
};
```

The singleton is warm on subsequent requests within the same isolate lifetime. Cold starts that never invoke image processing pay zero WASM cost.

---

## Anti-patterns / What Went Wrong

1. **Module-scope top-level `await` for heavy resources.** Any `await` at module scope executes during isolate initialization. A 1.2 MB WASM binary is not a small config fetch — it is compilation work. Even a small WASM module adds latency for routes that never use it.

2. **Cold start excluded from deploy health checks.** The post-deploy canary checked HTTP status and p50 duration on warm requests only. Cold starts were not sampled or compared before/after deploy.

3. **No p95 cold start alert configured.** Tail Workers emitted the `cf.cold_start` flag for months without a threshold alert on the cold-start cohort's p95.

4. **Equating "warm isolate correctness" with "deploy health".** A Worker can be 100% functionally correct and still carry a serious latency regression visible only in cold start behavior.

---

## Gotchas

- **Cold starts are invisible in standard HTTP monitors.** Uptime robots and synthetic monitors typically hit warm isolates after the first probe. Use Tail Workers with explicit `cf.cold_start` filtering.
- **WASM compile cost is paid per isolate, not per request.** Once compiled, the instance is reused within the isolate. The cold start budget includes compilation.
- **`wrangler tail` in production does not give you a p95.** You need Analytics Engine or an external sink to aggregate tail events for percentile calculations.
- **ESM Workers boot faster than Service Workers format.** If you are still on Service Workers format, migrating to ESM is a free cold start reduction before optimizing module scope.
- **Isolate reuse is not guaranteed.** Cloudflare may discard and recreate isolates under memory pressure. A Worker with a 600ms cold start will pay that cost repeatedly on high-variance traffic.

---

## Prevention Measures Adopted

### CI Cold Start Budget Gate

A new CI step runs before production deploy:

```yaml
# .github/workflows/deploy.yml (excerpt)
- name: Cold start budget check
  run: |
    # Deploy to a staging worker
    wrangler deploy --env staging
    # Tail for 60s, capturing cold start durations
    node scripts/cold-start-sample.js \
      --worker my-worker-staging \
      --samples 20 \
      --p95-budget-ms 300
    # Fails CI if p95 cold start exceeds budget
```

```javascript
// scripts/cold-start-sample.js (excerpt)
// Fires synthetic requests against staging, measures cold start durations
// via Tail Workers webhook, asserts p95 <= budget
const coldStarts = events
  .filter(e => e.outcome === 'ok' && e.coldStart === true)
  .map(e => e.wallTimeMs);
const p95 = percentile(95, coldStarts);
if (p95 > budgetMs) {
  console.error(`Cold start p95 ${p95}ms exceeds budget ${budgetMs}ms`);
  process.exit(1);
}
```

### Alert Added to Tail Workers Sink

```sql
-- Analytics Engine alert rule (pseudo-SQL, configured via API)
SELECT quantileTDigest(0.95)(duration_ms)
FROM tail_events
WHERE cf_cold_start = true
  AND timestamp > now() - INTERVAL '10 minutes'
HAVING quantileTDigest(0.95)(duration_ms) > 350
-- Alert: PagerDuty P3
```

---

## Verification

- p95 cold start confirmed at 208ms post-fix (vs 612ms during regression, 210ms pre-regression baseline).
- CI cold start gate: red on the regression branch, green on the fix branch.
- Tail Workers dashboard shows no cold start anomalies in the 7 days following the fix deploy.

---

## Related

- `d1-missing-index-full-table-scan-viral-traffic.md`
- Cloudflare Workers: [Optimizing Cold Start Performance](https://developers.cloudflare.com/workers/learning/cold-starts/)
- Tail Workers: [Analytics Engine sink](https://developers.cloudflare.com/analytics/analytics-engine/)

---

## Sources

- Internal postmortem ticket `INC-2026-0819`
- Cloudflare Workers ESM module documentation
- Tail Workers event schema reference
- `wrangler tail` output captured during investigation
