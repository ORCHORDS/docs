# Load Balancing Session Affinity (Sticky Sessions)

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Requests from the same user end up on different origin servers across a session, causing cart loss, in-progress file uploads to fail, or WebSocket upgrades to land on an origin that doesn't have the connection state. Standard round-robin or least-connections balancing distributes each request independently and doesn't help. You need the same client to return to the same origin for the lifetime of a session.

## Context

Cloudflare Load Balancing supports session affinity through a cookie-based mechanism: the first response sets a `__cf_bm` or custom affinity cookie containing an encrypted origin reference; subsequent requests from the same client carry that cookie and are routed to the same origin pool member. Session affinity is configured at the load balancer level, not in Workers code, but Workers can interact with — and extend — affinity behaviour via the `CF-Cache-Status` header, `waitUntil`, and service bindings. Affinity does not bypass health checks: if the sticky origin goes down, Cloudflare re-establishes affinity to a healthy origin.

---

## Enabling Session Affinity via Wrangler / Terraform

Session affinity is a property of the Load Balancer resource. Using the Cloudflare Terraform provider:

```hcl
resource "cloudflare_load_balancer" "app_lb" {
  zone_id          = var.zone_id
  name             = "app.example.com"
  fallback_pool_id = cloudflare_load_balancer_pool.primary.id
  default_pool_ids = [cloudflare_load_balancer_pool.primary.id]

  session_affinity = "cookie"

  session_affinity_attributes {
    samesite               = "Strict"
    secure                 = "Always"
    drain_duration         = 300  # seconds before evicting sticky session on drain
    zero_downtime_failover = "sticky" # re-pin to new origin vs "none"
  }

  # TTL for the affinity cookie (seconds); 0 = browser session cookie
  session_affinity_ttl = 86400
}
```

`zero_downtime_failover = "sticky"` means Cloudflare attempts to route to the same geographic pool first; set to `"temporary"` to allow any healthy pool on failover.

---

## Reading Affinity State in a Worker (Observing Stickiness)

A Worker sitting in front of the load balancer can inspect which origin served a request via the `CF-Connecting-IP`-equivalent headers Cloudflare exposes, and log affinity events:

```typescript
export default {
  async fetch(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const res = await fetch(req); // passes through to LB → sticky origin

    // Cloudflare sets this on the *first* sticky response
    const affinityCookie = res.headers.get('Set-Cookie') ?? '';
    const isNewSession = affinityCookie.includes('__cflb');

    if (isNewSession) {
      ctx.waitUntil(
        env.DB.prepare(
          `INSERT INTO affinity_events (client_ip, ts) VALUES (?, ?)`
        ).bind(req.headers.get('CF-Connecting-IP'), Date.now()).run()
      );
    }

    return res;
  },
};
```

`__cflb` is the Cloudflare load balancer affinity cookie. It is HttpOnly and Secure by default; the Worker cannot read its value, but can detect its presence in `Set-Cookie`.

---

## Custom Affinity Cookie for Application-Level Control

When Cloudflare's built-in cookie isn't sufficient (e.g., you need to encode the tenant or origin pool name in a readable cookie for debugging), implement application-level affinity in a Worker with the load balancer in DNS-only mode:

```typescript
interface Env {
  ORIGIN_A: Fetcher; // service binding to origin-a Worker
  ORIGIN_B: Fetcher; // service binding to origin-b Worker
  KV: KVNamespace;   // maps sessionId → originKey
}

const ORIGINS: Record<string, Fetcher | undefined> = {};

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    // Build the map at runtime (can't reference `env` at module scope)
    const originMap: Record<string, Fetcher> = {
      'origin-a': env.ORIGIN_A,
      'origin-b': env.ORIGIN_B,
    };

    const cookie = parseCookie(req.headers.get('Cookie') ?? '');
    let sessionId = cookie['app_session'];
    let originKey = sessionId ? await env.KV.get(`affinity:${sessionId}`) : null;

    if (!originKey) {
      // Pick least-loaded origin (simplistic: random for demo)
      originKey = Math.random() < 0.5 ? 'origin-a' : 'origin-b';
    }

    const origin = originMap[originKey];
    if (!origin) return new Response('No healthy origin', { status: 503 });

    const res = await origin.fetch(req);
    const headers = new Headers(res.headers);

    if (!sessionId) {
      sessionId = crypto.randomUUID();
      await env.KV.put(`affinity:${sessionId}`, originKey, { expirationTtl: 86400 });
      headers.append(
        'Set-Cookie',
        `app_session=${sessionId}; Path=/; SameSite=Strict; Secure; HttpOnly; Max-Age=86400`
      );
    }

    return new Response(res.body, { status: res.status, headers });
  },
};

function parseCookie(header: string): Record<string, string> {
  return Object.fromEntries(
    header.split(';').map((s) => s.trim().split('=').map((p) => decodeURIComponent(p.trim())))
  );
}
```

---

## Health-Check–Aware Drain with Workers

When taking an origin out of rotation, use the load balancer drain feature rather than removing the pool member immediately. A Worker can signal an in-progress drain to clients:

```typescript
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    // Check if this origin is being drained (set by your deploy pipeline in KV)
    const draining = await env.KV.get('origin:drain:this-pod');

    if (draining) {
      // Tell the LB to re-establish affinity elsewhere by clearing the cookie
      const res = await fetch(req);
      const headers = new Headers(res.headers);
      headers.append(
        'Set-Cookie',
        '__cflb=; Path=/; Max-Age=0; Secure; HttpOnly'
      );
      return new Response(res.body, { status: res.status, headers });
    }

    return fetch(req);
  },
};
```

Set `origin:drain:this-pod` in KV with a TTL equal to the LB drain duration before removing the origin from the pool.

---

## WebSocket Session Affinity

WebSocket connections require the upgrade and all subsequent frames to hit the same origin. Ensure the load balancer's affinity cookie is set on the initial HTTP upgrade request:

```typescript
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    if (req.headers.get('Upgrade') === 'websocket') {
      // Do NOT buffer the response — WebSocket upgrades must stream
      // Cloudflare LB affinity cookie is set on the upgrade response
      const res = await fetch(req, {
        headers: {
          ...Object.fromEntries(req.headers),
          // Forward the existing affinity cookie so LB routes to same origin
          Cookie: req.headers.get('Cookie') ?? '',
        },
      });

      if (res.status === 101) {
        return res; // Switching Protocols — must pass through unchanged
      }
    }

    return fetch(req);
  },
};
```

Do not wrap the `101 Switching Protocols` response in a `new Response()` — it must be returned as-is or the WebSocket handshake fails.

---

## Anti-patterns

- **Relying on IP-based affinity** — Cloudflare offers `ip_cookie` mode but CGNAT and mobile networks share IPs across many users; cookie-based affinity is more accurate.
- **Setting `session_affinity_ttl` to 0 (session cookie) for long-lived apps** — browser session cookies are lost when the tab closes; returning users get a new origin assignment.
- **Implementing affinity in a Worker without KV/Durable Object backing** — a Worker with no state store cannot be consistent across Cloudflare's 300+ PoPs.
- **Removing a pool member immediately without drain** — in-flight requests and active WebSocket connections are dropped; always drain first.

---

## Gotchas

- Session affinity only works within the same pool. If your primary pool fails and requests fall back to the secondary pool, affinity is re-established on a new origin in that pool.
- The `__cflb` cookie is not scoped to a path by default; it applies to the whole domain. If you run multiple apps on subpaths, they will share affinity state.
- `zero_downtime_failover = "sticky"` adds latency on origin failure (Cloudflare retries the sticky origin before failing over); set it to `"none"` for latency-sensitive paths.
- In Enterprise plans, session affinity can be configured per-rule using Page Rules or Transform Rules. On Free/Pro, it applies to the entire load balancer.

---

## Verification

```bash
# First request — confirm affinity cookie is set
curl -c /tmp/cf_cookies.txt -I https://app.example.com/
# Look for: Set-Cookie: __cflb=...

# Second request — confirm same origin responds (check a custom X-Origin header)
curl -b /tmp/cf_cookies.txt -I https://app.example.com/
# X-Served-By: origin-a (should match first response)

# Drain test — remove affinity cookie and confirm re-assignment
curl -I https://app.example.com/
# Should get a new __cflb value and potentially a different X-Served-By
```

---

## Related

- `load-balancing-workers-health-checks.md`
- `durable-objects-websocket-hibernation.md`
- `cloudflare-waiting-room-event-queue-workers.md`
- `workers-websocket-upgrade.md`

---

## Sources

- Cloudflare Load Balancing — Session Affinity: https://developers.cloudflare.com/load-balancing/understand-basics/session-affinity/
- Cloudflare Terraform provider — cloudflare_load_balancer: https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/load_balancer
- Zero-downtime failover: https://developers.cloudflare.com/load-balancing/understand-basics/session-affinity/#zero-downtime-failover
