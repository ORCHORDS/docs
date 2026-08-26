# Multi-Environment Status Dashboard

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your application runs in both staging and production environments, each backed by its own D1 database. You want a single status dashboard that aggregates health checks from both, serves a JSON API for programmatic consumption, caches the last result in KV to avoid hammering D1, and renders an HTML view via HTMLRewriter for human inspection.

## Context

Cloudflare Workers can hold multiple D1 bindings pointing at different databases — one per environment. A status Worker reads a `health_checks` table from each binding, merges the results, writes them to KV with a short TTL, and uses `HTMLRewriter` to inject live status badges into a static HTML template stored in a Worker Asset.

---

## Section 1 — D1 health-check schema (applied to both databases)

```sql
-- migrations/0001_health_checks.sql
CREATE TABLE IF NOT EXISTS health_checks (
  id          TEXT    PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
  service     TEXT    NOT NULL,
  status      TEXT    NOT NULL CHECK(status IN ('ok','degraded','down')),
  latency_ms  INTEGER,
  message     TEXT,
  checked_at  INTEGER NOT NULL DEFAULT (unixepoch() * 1000)
);

CREATE INDEX idx_hc_service ON health_checks(service, checked_at DESC);
```

## Section 2 — Worker: JSON status API

```typescript
// status-worker/src/index.ts
export interface Env {
  STATUS_CACHE:    KVNamespace;   // cached aggregate result
  STAGING_DB:      D1Database;
  PRODUCTION_DB:   D1Database;
  CACHE_TTL_SEC:   string;        // default "30"
}

interface CheckRow {
  service:    string;
  status:     'ok' | 'degraded' | 'down';
  latency_ms: number | null;
  message:    string | null;
  checked_at: number;
}

interface EnvStatus {
  environment: string;
  overall:     'ok' | 'degraded' | 'down';
  services:    CheckRow[];
  fetched_at:  number;
}

async function fetchEnvStatus(
  db: D1Database,
  envName: string
): Promise<EnvStatus> {
  // Grab the most recent check per service
  const { results } = await db.prepare(`
    SELECT service, status, latency_ms, message, checked_at
    FROM health_checks
    WHERE checked_at = (
      SELECT MAX(checked_at) FROM health_checks hc2
      WHERE hc2.service = health_checks.service
    )
    ORDER BY service
  `).all<CheckRow>();

  const overall = results.some((r) => r.status === 'down')
    ? 'down'
    : results.some((r) => r.status === 'degraded')
    ? 'degraded'
    : 'ok';

  return { environment: envName, overall, services: results, fetched_at: Date.now() };
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url    = new URL(request.url);
    const accept = request.headers.get('Accept') ?? '';
    const ttl    = parseInt(env.CACHE_TTL_SEC ?? '30', 10);

    if (url.pathname === '/status' || url.pathname === '/') {
      // Try KV cache first
      const cached = await env.STATUS_CACHE.get('aggregate', 'json') as
        { environments: EnvStatus[]; generated_at: number } | null;

      let data: { environments: EnvStatus[]; generated_at: number };

      if (cached && Date.now() - cached.generated_at < ttl * 1000) {
        data = cached;
      } else {
        const [staging, production] = await Promise.all([
          fetchEnvStatus(env.STAGING_DB, 'staging'),
          fetchEnvStatus(env.PRODUCTION_DB, 'production'),
        ]);
        data = { environments: [staging, production], generated_at: Date.now() };
        await env.STATUS_CACHE.put('aggregate', JSON.stringify(data), {
          expirationTtl: ttl,
        });
      }

      if (accept.includes('text/html')) {
        return renderHtml(data);
      }

      return new Response(JSON.stringify(data, null, 2), {
        headers: { 'Content-Type': 'application/json', 'Cache-Control': `max-age=${ttl}` },
      });
    }

    return new Response('Not Found', { status: 404 });
  },
};
```

## Section 3 — HTMLRewriter dashboard renderer

```typescript
// status-worker/src/html.ts
const HTML_TEMPLATE = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Status Dashboard</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 800px; margin: 2rem auto; }
    .badge { display:inline-block; padding:.25rem .6rem; border-radius:4px; font-weight:bold; }
    .ok { background:#d1fae5; color:#065f46; }
    .degraded { background:#fef3c7; color:#92400e; }
    .down { background:#fee2e2; color:#991b1b; }
    table { border-collapse:collapse; width:100%; margin-top:1rem; }
    th,td { text-align:left; padding:.5rem; border-bottom:1px solid #e5e7eb; }
  </style>
</head>
<body>
  <h1>Status Dashboard</h1>
  <div id="environments"></div>
</body>
</html>`;

type AggregateData = {
  environments: Array<{
    environment: string;
    overall: string;
    services: Array<{ service: string; status: string; latency_ms: number | null; message: string | null; checked_at: number }>;
    fetched_at: number;
  }>;
  generated_at: number;
};

export function renderHtml(data: AggregateData): Response {
  // Build the inner HTML string and inject it via HTMLRewriter
  const inner = data.environments.map((env) => {
    const rows = env.services.map((svc) =>
      `<tr>
        <td>${escHtml(svc.service)}</td>
        <td><span class="badge ${svc.status}">${svc.status.toUpperCase()}</span></td>
        <td>${svc.latency_ms != null ? svc.latency_ms + ' ms' : '—'}</td>
        <td>${escHtml(svc.message ?? '')}</td>
       </tr>`
    ).join('');

    return `<section>
      <h2>${escHtml(env.environment)}
        <span class="badge ${env.overall}">${env.overall.toUpperCase()}</span>
      </h2>
      <table>
        <thead><tr><th>Service</th><th>Status</th><th>Latency</th><th>Message</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
      <p><small>Fetched at ${new Date(env.fetched_at).toISOString()}</small></p>
    </section>`;
  }).join('');

  const rewriter = new HTMLRewriter().on('#environments', {
    element(el) { el.setInnerContent(inner, { html: true }); },
  });

  return rewriter.transform(
    new Response(HTML_TEMPLATE, { headers: { 'Content-Type': 'text/html; charset=utf-8' } })
  );
}

function escHtml(s: string): string {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
```

## Section 4 — wrangler.toml

```toml
# status-worker/wrangler.toml
name = "status-worker"
main = "src/index.ts"
compatibility_date = "2025-10-01"

[vars]
CACHE_TTL_SEC = "30"

[[kv_namespaces]]
binding = "STATUS_CACHE"
id      = "<your-kv-id>"

[[d1_databases]]
binding       = "STAGING_DB"
database_name = "app-staging"
database_id   = "<staging-d1-id>"

[[d1_databases]]
binding       = "PRODUCTION_DB"
database_name = "app-production"
database_id   = "<production-d1-id>"
```

```bash
# Deploy
wrangler deploy --config status-worker/wrangler.toml

# Seed a test health check in staging
wrangler d1 execute app-staging --remote \
  --command "INSERT INTO health_checks (service, status, latency_ms) VALUES ('api', 'ok', 45);"

# Fetch JSON status
curl -s https://status-worker.example.com/status | jq .

# Fetch HTML dashboard
curl -s -H 'Accept: text/html' https://status-worker.example.com/status | grep -o '<title>.*</title>'
```

## Anti-patterns

- **Querying D1 on every request** — status pages are hit frequently by uptime monitors; always cache in KV for at least 15 seconds.
- **Using a single D1 binding for both environments** — changes to the staging schema will affect production queries. Keep bindings separate.
- **Building HTML with string concatenation without escaping** — always escape user-controlled content with `escHtml()` even in an internal dashboard.
- **Returning 200 OK regardless of overall status** — HTTP monitors expect non-200 for failures. Return 503 when `overall === 'down'`.

## Gotchas

- `HTMLRewriter` streams the response — mutations must be applied synchronously in element handlers; you cannot `await` inside them.
- KV `get` with `'json'` type returns `null` for cache misses, not `undefined` — check for `null` explicitly.
- `Promise.all` for two D1 databases is safe: each binding is independent. If one fails, the whole aggregate fails — add individual try/catch if you want partial results.
- Workers cannot hold more than 10 D1 bindings per Worker at the time of writing.

## Verification

```bash
# Check KV cache entry
wrangler kv key get --namespace-id=<id> "aggregate"

# Force cache miss by deleting the key
wrangler kv key delete --namespace-id=<id> "aggregate"

# Confirm 503 when a service is down
wrangler d1 execute app-production --remote \
  --command "INSERT INTO health_checks (service, status) VALUES ('payments', 'down');"
curl -o /dev/null -s -w "%{http_code}" https://status-worker.example.com/status
```

## Related

- `workers-dead-man-switch-cron-alert.md` — proactive alerting when services go silent
- `workers-real-user-monitoring-beacon.md` — client-side health signals
- Cloudflare HTMLRewriter: https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/kv/
