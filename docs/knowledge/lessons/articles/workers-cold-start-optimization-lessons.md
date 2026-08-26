# Workers Cold Start Optimization Lessons

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

P99 request latency spikes to 800–1200 ms on the first request after a period of inactivity. Warm requests complete in 15–30 ms. Users on mobile or in regions with low traffic density experience the cold start disproportionately. Lighthouse and RUM dashboards show sporadic first-byte-time outliers that inflate the p95/p99 spread and obscure real regressions.

## Context

Cloudflare Workers are isolated V8 contexts. When a new isolate is provisioned — either because no warm isolate is available or because a new code version was deployed — the runtime must:

1. Deserialize and compile the worker script bundle.
2. Execute all module-scope JavaScript (top-level `import` side-effects, `const` initialisations, etc.).
3. Route the first request into the newly warmed isolate.

Steps 1–2 are the "cold start" window. CPU time consumed here is real CPU budget deducted from the first request. Bundle size, amount of module-scope work, and which platform APIs are called during startup all affect how long this window is.

## Solution

```typescript
// ─── wrangler.toml ───────────────────────────────────────────────────────────
// compatibility_date = "2024-09-23"
// compatibility_flags = ["nodejs_compat"]

import { Env } from './types';

// ❌ BAD: expensive work at module scope — runs on every cold start
// const DB_SCHEMA = JSON.parse(fs.readFileSync('./schema.json', 'utf8'));
// const COMPILED_REGEX = buildMegaRegex(5000);
// const crypto = require('node:crypto');
// const key = crypto.createSecretKey(Buffer.from(process.env.SECRET!, 'hex'));

// ✅ GOOD: module-scope constants must be pure literals or tiny initialisations
const REGION_MAP: Record<string, string> = {
  'IAD': 'us-east',
  'SJC': 'us-west',
  'LHR': 'eu-west',
  'NRT': 'ap-northeast',
};

// ─── Lazy initialisation pattern ─────────────────────────────────────────────
// Wrap anything that touches platform bindings or does real work in a
// once-initialised singleton. The first warm request pays the cost; subsequent
// requests in the same isolate get the cached result.

let _preparedStatements: PreparedStatements | null = null;

interface PreparedStatements {
  getUserById: D1PreparedStatement;
  listSessionsByUser: D1PreparedStatement;
  insertAuditLog: D1PreparedStatement;
}

function getPreparedStatements(db: D1Database): PreparedStatements {
  if (_preparedStatements) return _preparedStatements;
  // D1 .prepare() compiles the SQL plan; doing this once per isolate
  // rather than per request saves ~2–5 ms on warm paths and avoids
  // repeated plan-cache misses inside the D1 engine.
  _preparedStatements = {
    getUserById:         db.prepare('SELECT id, email, role FROM users WHERE id = ?1'),
    listSessionsByUser:  db.prepare('SELECT token, expires_at FROM sessions WHERE user_id = ?1 ORDER BY created_at DESC LIMIT 20'),
    insertAuditLog:      db.prepare('INSERT INTO audit_log (user_id, action, meta, ts) VALUES (?1, ?2, ?3, unixepoch())'),
  };
  return _preparedStatements;
}

// ─── Lazy crypto key import ───────────────────────────────────────────────────
// SubtleCrypto.importKey() is async and relatively cheap, but calling it at
// module scope forces it into the cold-start path and makes the first isolate
// provision fail-loud if the secret is missing.

let _signingKey: CryptoKey | null = null;

async function getSigningKey(secret: string): Promise<CryptoKey> {
  if (_signingKey) return _signingKey;
  const raw = Uint8Array.from(atob(secret), c => c.charCodeAt(0));
  _signingKey = await crypto.subtle.importKey(
    'raw', raw, { name: 'HMAC', hash: 'SHA-256' }, false, ['sign', 'verify']
  );
  return _signingKey;
}

// ─── Measuring cold vs warm latency with Analytics Engine ────────────────────

interface Metrics {
  AE: AnalyticsEngineDataset;
}

let _isolateStartMs: number | null = null;

export default {
  async fetch(request: Request, env: Env & Metrics): Promise<Response> {
    const requestStart = performance.now();

    // Detect cold start: _isolateStartMs is null only on the very first
    // invocation of this isolate.
    const isColdStart = _isolateStartMs === null;
    if (isColdStart) _isolateStartMs = requestStart;

    // ── Lazy init (paid once per isolate, not per request) ───────────────
    const stmts = getPreparedStatements(env.DB);
    const signingKey = await getSigningKey(env.SIGNING_SECRET);

    // ── Business logic ───────────────────────────────────────────────────
    const url = new URL(request.url);
    const userId = url.searchParams.get('user');
    if (!userId) return new Response('Bad Request', { status: 400 });

    const { results } = await stmts.getUserById.bind(userId).all();
    const user = results[0];
    if (!user) return new Response('Not Found', { status: 404 });

    // ── Emit telemetry ────────────────────────────────────────────────────
    const totalMs = performance.now() - requestStart;
    env.AE.writeDataPoint({
      blobs:   [request.cf?.colo as string ?? 'UNK', isColdStart ? 'cold' : 'warm'],
      doubles: [totalMs, requestStart - (_isolateStartMs ?? requestStart)],
      indexes: ['worker-latency'],
    });

    return Response.json(user);
  },
};

// ─── Bundle-size discipline ───────────────────────────────────────────────────
// The V8 bytecode compilation cost scales roughly linearly with bundle size.
// Every extra KB of JavaScript adds ~0.1–0.3 ms to cold start.
//
// Strategies:
//   1. Use wrangler's built-in tree-shaking (ESM + rollup).
//   2. Audit bundle with: npx wrangler deploy --dry-run --outdir dist && ls -lh dist/
//   3. Replace lodash/fp with native equivalents.
//   4. Avoid importing entire SDK packages when only one function is needed.
//
// npx wrangler deploy --dry-run --outdir dist
// du -sh dist/*.js   # target < 500 KB uncompressed for < 50 ms cold start
```

## Implementation Details

**Module-scope vs handler-scope cost.** Anything at module scope runs synchronously during isolate initialisation. Every millisecond spent there is a millisecond added to the cold start. Even a `.map()` over a 10 000-entry array at module scope can add 5–10 ms.

**D1 prepared statement pre-compilation.** `db.prepare()` compiles the SQL query into an internal plan. Calling it once per isolate (via the lazy singleton above) rather than once per request saves 2–5 ms per hot path and prevents the plan cache from being evicted between requests in different isolates.

**SubtleCrypto key import timing.** `importKey` with HMAC/SHA-256 over a 32-byte key takes about 0.3 ms. Trivial individually, but if you import three keys at module scope, plus parse two JSON configs, plus build a regex, the total can push past 10 ms before a single line of business logic runs.

**Bundle size impact.** Internal Cloudflare benchmarks suggest roughly 0.15 ms per 10 KB of uncompressed bundle for bytecode compilation. A 1 MB bundle adds ~15 ms to cold start baseline. The 1 MB script size limit also applies, so large bundles are doubly penalised.

**Analytics Engine cold/warm split.** The `isColdStart` flag in the example above lets you build an AE SQL query that separates the two populations:
```sql
SELECT
  blob2 AS start_type,
  quantileWeighted(0.50)(double1, 1) AS p50_ms,
  quantileWeighted(0.95)(double1, 1) AS p95_ms,
  quantileWeighted(0.99)(double1, 1) AS p99_ms
FROM workers_latency
WHERE timestamp > now() - INTERVAL '1' HOUR
GROUP BY blob2
```

## Anti-patterns

- **`import { everything } from 'some-sdk'` at top level.** Even if tree-shaking removes the dead code, large transitive dependency graphs inflate parse time.
- **Top-level `await` that calls an external service.** This gates every cold start on a network round-trip and can cause timeouts during isolate provisioning.
- **`crypto.getRandomValues()` in a module-scope initialiser.** Triggers the CSPRNG initialisation cost on every cold start.
- **Constructing `RegExp` from long strings at module scope.** Complex regexes with backtracking are compiled by V8 during cold start.
- **Reading `env.*` bindings outside the `fetch` / `scheduled` handler.** Bindings are not available at module scope — they are injected per-request. Accessing them outside a handler throws and crashes the cold start.

## Gotchas

- **Smart Placement changes cold-start geography.** When Smart Placement moves your worker closer to your D1 database, the isolate pool may be colder in that region since less traffic hits it. Measure cold start rates per colo, not globally.
- **New deployments always trigger cold starts.** Every `wrangler deploy` invalidates the isolate pool. Canary rollouts and gradual deploys don't help here — every new script version needs at least one cold start per colo.
- **Lazy singletons are not shared across concurrent requests.** If two requests hit the same fresh isolate simultaneously, both may execute the lazy initialiser. Add a promise-based mutex if the work is not idempotent.
- **`_isolateStartMs` is reset when the isolate is evicted.** Cloudflare evicts idle isolates after minutes of inactivity. The singleton resets to `null` on the next cold start.
- **`performance.now()` measures wall-clock time, not CPU time.** I/O waits (KV, D1, fetch) are not counted against CPU budget but are counted in wall-clock. Use separate instrumentation to isolate CPU-bound hot spots.

## Verification

```typescript
// Smoke test: call the endpoint 10 times after a 5-minute pause, inspect AE
// for cold vs warm split. Cold p50 should be < 100 ms; warm p50 < 30 ms.

// In wrangler dev (local), simulate cold start by restarting the dev server
// between calls. In production, use a Cloudflare Cron Trigger to emit
// synthetic canary requests every minute per target colo.

// Load-test warm path with:
// npx autocannon -c 50 -d 30 https://your-worker.example.com/user?user=123
// and check AE that "warm" bucket p99 stays under 50 ms.
```

## Related

- `workers-cold-start-latency-lessons.md`
- `workers-cold-start-traffic-surge-postmortem.md`
- `workers-module-scope-global-state-mutation-bug.md`
- `d1-prepared-statement-plan-cache-invalidation-regression.md`
- `analytics-engine-data-point-limit-exceeded.md`

## Sources

- Cloudflare Workers Runtime — Cold Starts: https://developers.cloudflare.com/workers/platform/limits/
- Cloudflare Blog — "How we built the Cloudflare Workers runtime": https://blog.cloudflare.com/workers-open-source-announcement/
- D1 — Prepared Statements: https://developers.cloudflare.com/d1/worker-api/prepared-statements/
- Analytics Engine SQL API: https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- V8 Blog — Lazy Compilation: https://v8.dev/blog/lazy-compilation
