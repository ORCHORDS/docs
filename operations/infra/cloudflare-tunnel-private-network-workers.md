# Cloudflare Tunnel — Private Network Exposure to Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
You have an internal service (e.g. a legacy Postgres-backed API) running on a private network that is not publicly reachable. You need Cloudflare Workers to call it via a service binding or HTTP fetch without opening a firewall hole. Cloudflare Tunnel with a named tunnel lets you bridge that gap securely.

---

## Context
Cloudflare Tunnel (`cloudflared`) creates an outbound-only connection from your private network to Cloudflare's edge. A named tunnel is registered in your Cloudflare account and persists across restarts. Workers can reach the private origin through a `*.cfargotunnel.com` hostname or a custom hostname attached to the tunnel. D1 is used here to track tunnel health state and rotation events so an ops Worker can surface status without hitting the Cloudflare API on every request.

---

## Configuration — `cloudflared` connector
```toml
# config.yml (on the private host)
tunnel: my-private-tunnel
credentials-file: /etc/cloudflared/my-private-tunnel.json

ingress:
  - hostname: internal-api.example.com
    service: http://localhost:8080
    originRequest:
      connectTimeout: 5s
      noHappyEyeballs: false
  - service: http_status:404

warp-routing:
  enabled: true
```

## D1 Schema — tunnel state tracking
```sql
CREATE TABLE IF NOT EXISTS tunnel_events (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  tunnel_id   TEXT    NOT NULL,
  event_type  TEXT    NOT NULL, -- 'connected' | 'disconnected' | 'health_fail'
  connector   TEXT,
  recorded_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_tunnel_events_tunnel_id ON tunnel_events (tunnel_id, recorded_at DESC);
```

## Health-check Worker
```typescript
// src/tunnel-health.ts
export interface Env {
  DB: D1Database;
  TUNNEL_ID: string;
  INTERNAL_API_URL: string; // e.g. https://internal-api.example.com
}

interface TunnelEvent {
  tunnel_id: string;
  event_type: string;
  connector: string | null;
  recorded_at: string;
}

async function probeOrigin(url: string, timeoutMs = 3000): Promise<boolean> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const resp = await fetch(`${url}/health`, { signal: controller.signal });
    return resp.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // GET /status — return latest tunnel events
    if (url.pathname === '/status') {
      const rows = await env.DB
        .prepare(
          'SELECT * FROM tunnel_events WHERE tunnel_id = ? ORDER BY recorded_at DESC LIMIT 20'
        )
        .bind(env.TUNNEL_ID)
        .all<TunnelEvent>();

      return Response.json({ events: rows.results });
    }

    // GET /probe — active health check
    if (url.pathname === '/probe') {
      const healthy = await probeOrigin(env.INTERNAL_API_URL);
      const eventType = healthy ? 'connected' : 'health_fail';

      await env.DB
        .prepare(
          'INSERT INTO tunnel_events (tunnel_id, event_type, connector) VALUES (?, ?, ?)'
        )
        .bind(env.TUNNEL_ID, eventType, request.headers.get('CF-Worker-Id'))
        .run();

      return Response.json({ healthy, tunnel_id: env.TUNNEL_ID }, {
        status: healthy ? 200 : 503,
      });
    }

    return new Response('Not found', { status: 404 });
  },

  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const healthy = await probeOrigin(env.INTERNAL_API_URL);
    await env.DB
      .prepare(
        'INSERT INTO tunnel_events (tunnel_id, event_type) VALUES (?, ?)'
      )
      .bind(env.TUNNEL_ID, healthy ? 'connected' : 'health_fail')
      .run();
  },
};
```

## `wrangler.toml`
```toml
name = "tunnel-health"
main = "src/tunnel-health.ts"
compatibility_date = "2024-09-23"

[triggers]
crons = ["*/5 * * * *"]

[[d1_databases]]
binding = "DB"
database_name = "tunnel-state"
database_id = "<your-d1-database-id>"

[vars]
TUNNEL_ID = "my-private-tunnel"
INTERNAL_API_URL = "https://internal-api.example.com"
```

---

## Anti-patterns
- **Polling the Cloudflare API for tunnel status** — this burns API rate limits and adds latency; store state in D1 instead.
- **Using `http` instead of `https` for the tunnel hostname** — Workers enforce TLS; always configure the tunnel ingress with a valid certificate or use Cloudflare-managed certificates.
- **Single-connector tunnels in production** — run at least two `cloudflared` replicas for HA; a single connector is a single point of failure.

---

## Gotchas
- The tunnel credential JSON must be readable by the `cloudflared` process user; a common permission error is `permission denied` on the credentials file.
- Warp-routing requires the WARP connector feature to be enabled on the Cloudflare Zero Trust dashboard before traffic is routed.
- The `CF-Worker-Id` header is not available in production Workers by default; use `env.TUNNEL_ID` or a custom binding instead of relying on it for identity.

---

## Verification
```bash
# Check tunnel is registered
cloudflared tunnel list

# Run connector in foreground for debugging
cloudflared tunnel --config config.yml run my-private-tunnel

# Probe the health Worker
curl https://tunnel-health.<your-subdomain>.workers.dev/probe

# Query D1 for recent events
wrangler d1 execute tunnel-state --command \
  "SELECT * FROM tunnel_events ORDER BY recorded_at DESC LIMIT 10;"
```

---

## Related
- `workers-ip-allowlist-cloudflare-access-jwt.md`
- `cloudflare-load-balancer-health-check-workers.md`

---

## Sources
- Cloudflare Tunnel docs — https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/
- cloudflared ingress configuration — https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/configure-tunnels/local-management/ingress/
- D1 Workers binding — https://developers.cloudflare.com/d1/worker-api/
