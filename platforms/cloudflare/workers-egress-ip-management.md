# Workers Egress IP Management

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Workers make outbound `fetch()` calls to third-party APIs or internal services that have IP allowlists. The request arrives from an unpredictable Cloudflare IP each time, so the downstream service rejects it. You need either a predictable egress IP, a way to route Worker traffic through a known IP range, or a way to declare outbound connectivity constraints so Cloudflare's network honours them.

## Context

By default, a Worker's outbound `fetch()` exits from whichever Cloudflare data centre serves the request — one of 300+ PoPs, each with a large pool of IPs. Cloudflare publishes its full IP ranges at `https://www.cloudflare.com/ips/`, but these spans cover millions of IPs and no downstream service can practically allowlist them all. The practical solutions are: (1) route Worker egress through a Cloudflare Tunnel to a fixed-IP origin, (2) use a Magic WAN connector or Warp Connector that gives a predictable private IP at the egress, (3) for Workers with paid plans, use **Smart Placement** combined with a service binding to a collocated origin, or (4) use a proxy Worker with a fixed-IP VPS as an intermediary hop.

---

## Option 1: Egress via Cloudflare Tunnel (cloudflared)

Run `cloudflared` on a server that has a static IP or sits behind a NAT gateway with a fixed IP. Traffic flows: Worker → Tunnel → your server → downstream API. The downstream API sees your server's fixed IP.

```typescript
// Worker — calls internal service through tunnel hostname
interface Env {
  // Tunnel exposes the service at a private hostname via wrangler.toml:
  // [[services]]
  // binding = "INTERNAL_API"
  // service = "internal-api-worker"
  //
  // Or use a regular fetch to the tunnel's public hostname:
  TUNNEL_HOSTNAME: string; // e.g. "my-service.internal.example.com"
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    // This fetch exits through the Tunnel to your fixed-IP server
    const res = await fetch(`https://${env.TUNNEL_HOSTNAME}/api/action`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        // Internal auth token — the tunnel enforces mTLS, so this is not the
        // only authentication layer
        Authorization: `Bearer ${env.INTERNAL_TOKEN}`,
      },
      body: JSON.stringify(await req.json()),
    });

    return new Response(res.body, {
      status: res.status,
      headers: { 'Content-Type': 'application/json' },
    });
  },
};
```

Your `cloudflared` tunnel config (`~/.cloudflared/config.yml`) maps the hostname to `localhost:3000` on the fixed-IP server.

---

## Option 2: Proxy Worker on a Fixed-IP VPS

Deploy a lightweight Worker-compatible proxy on a VPS with an Elastic IP (AWS) or Reserved IP (DigitalOcean) and have the Cloudflare Worker route outbound calls through it. The downstream API allowlists the VPS IP:

```typescript
// egress-proxy-worker (deployed on fixed-IP VPS running workerd or a plain HTTP server)
// This is the proxy target — a simple Node/Bun server on the fixed-IP machine:

// proxy-server.ts (Bun)
Bun.serve({
  port: 8080,
  fetch: async (req) => {
    const target = req.headers.get('X-Target-URL');
    if (!target) return new Response('Missing X-Target-URL', { status: 400 });

    // Validate the secret to prevent open proxy abuse
    const secret = <redacted-secret>'X-Proxy-Secret');
    if (secret !== process.env.PROXY_SECRET) {
      return new Response('Forbidden', { status: 403 });
    }

    const proxied = new Request(target, {
      method: req.method,
      headers: new Headers(
        [...req.headers.entries()].filter(
          ([k]) => !['x-target-url', 'x-proxy-secret', 'host'].includes(k.toLowerCase())
        )
      ),
      body: req.body,
    });

    return fetch(proxied);
  },
});
```

Cloudflare Worker side:

```typescript
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const thirdPartyUrl = 'https://api.partner.com/v1/data';

    // Route through fixed-IP proxy
    const res = await fetch(`https://${env.PROXY_HOST}/`, {
      method: 'POST',
      headers: {
        'X-Target-URL': thirdPartyUrl,
        'X-Proxy-Secret': env.PROXY_SECRET,
        'Content-Type': 'application/json',
        Authorization: `Bearer ${env.PARTNER_API_KEY}`,
      },
      body: JSON.stringify(await req.json()),
    });

    return new Response(res.body, { status: res.status });
  },
};
```

---

## Option 3: Warp Connector for Private Network Egress

When the downstream service is on a private network (on-prem, VPC), use a Cloudflare Warp Connector on that network. The Worker makes a `fetch()` to a private IP/hostname, and Cloudflare routes it through the Warp Connector without leaving the Cloudflare network:

```typescript
// wrangler.toml — enable outbound connectivity to private network
// (requires Zero Trust account and Warp Connector enrollment)
//
// No special Worker code is needed once routing is configured in Zero Trust.
// The Worker simply fetches the private hostname:

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    // 10.0.0.5 is a host on your private network reachable via Warp Connector
    const res = await fetch('http://10.0.0.5:8080/internal-api', {
      headers: { 'X-Internal-Auth': env.INTERNAL_SECRET },
    });

    return new Response(res.body, { status: res.status });
  },
};
```

Configure the Zero Trust **Split Tunnel** and **Private Routes** to tell Cloudflare to route `10.0.0.0/8` through the Warp Connector. This requires the `workers_vpc` capability enabled on the Worker (contact Cloudflare support or use the API).

---

## Declaring Egress Restrictions in wrangler.toml

Limit which hostnames a Worker is allowed to call with `outbound` configuration. This prevents Workers from becoming open relay proxies and helps audit egress at deploy time:

```toml
# wrangler.toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[env.production]
# Not yet a stable wrangler feature for arbitrary egress — use outbound Workers
# for WfP, or enforce at the application level with an allowlist

# For Workers for Platforms outbound enforcement, see:
# workers-for-platforms-tenant-isolation.md
```

For non-WfP Workers, enforce an egress allowlist in code:

```typescript
const ALLOWED_EGRESS_HOSTS = new Set([
  'api.partner.com',
  'internal.mycompany.com',
]);

async function safeFetch(url: string | URL, init?: RequestInit): Promise<Response> {
  const parsed = new URL(url);
  if (!ALLOWED_EGRESS_HOSTS.has(parsed.hostname)) {
    throw new Error(`Egress to ${parsed.hostname} is not allowed`);
  }
  return fetch(url, init);
}
```

---

## Inspecting Egress IPs via Tail Workers

Log the actual source IP your Worker's `fetch()` uses by having a Tail Worker capture the outbound request's originating IP via a test endpoint:

```typescript
// tail-worker/src/index.ts
export default {
  async tail(events: TraceItem[]): Promise<void> {
    for (const event of events) {
      for (const log of event.logs) {
        // Look for any log entries that capture outbound IP
        if (typeof log.message[0] === 'string' && log.message[0].includes('egress_ip')) {
          await fetch('https://logs.example.com/ingest', {
            method: 'POST',
            body: JSON.stringify({ egressLog: log.message }),
          });
        }
      }
    }
  },
};
```

Use `https://api.ipify.org/?format=json` in a test Worker to capture the actual outbound IP for a given PoP:

```typescript
// diagnostics only — do not run in production
export default {
  async fetch(): Promise<Response> {
    const res = await fetch('https://api.ipify.org/?format=json');
    const { ip } = await res.json<{ ip: string }>();
    return Response.json({ outboundIp: ip, colo: 'check CF-RAY header' });
  },
};
```

---

## Anti-patterns

- **Allowlisting all of `https://www.cloudflare.com/ips/`** — this is 100M+ addresses; most partners will not do it, and it does not meaningfully restrict the surface.
- **Using a plain open proxy on the VPS** — adds a security liability; always require a shared secret and validate the target URL against an allowlist on the proxy.
- **Assuming Smart Placement delivers a fixed IP** — Smart Placement co-locates the Worker near the origin but still uses Cloudflare's IP pool; it does not produce a single predictable IP.
- **Rotating API keys instead of fixing the IP** — solves the authentication problem but not the IP-reputation problem if the downstream uses IP-based rate limiting.

---

## Gotchas

- `fetch()` in Workers follows redirects by default (`redirect: 'follow'`). If the redirect target is not in your egress allowlist, the `safeFetch` wrapper above will block it even though the initial host was allowed. Add `redirect: 'manual'` and handle `3xx` explicitly.
- Cloudflare Tunnel traffic still originates from Cloudflare's network on its way to your `cloudflared` daemon; the *downstream API* sees your VPS/server IP, but the tunnel itself transits Cloudflare infrastructure.
- Workers TCP Sockets (`connect()`) follow the same egress routing as `fetch()` — there is no separate fixed-IP mechanism for raw TCP.
- The `CF-Connecting-IP` header is the **inbound** client IP — not the egress IP used by the Worker's outbound `fetch()`. Confusing these is a common mistake.

---

## Verification

```bash
# Check current egress IP from a specific Cloudflare PoP
curl "https://your-diagnostic-worker.example.com/" \
  -H "Accept: application/json" | jq .outboundIp

# Verify Tunnel connectivity
curl -I https://my-service.internal.example.com/health
# Expected: HTTP/2 200 from your origin server

# Confirm downstream API sees the VPS IP
# On the downstream server's access log:
tail -f /var/log/nginx/access.log | grep "YOUR_VPS_IP"
```

---

## Related

- `cloudflare-tunnel-private-service-ingress.md`
- `workers-tcp-sockets-connect-api.md`
- `workers-mtls-certificates.md`
- `workers-vpc-least-privilege-design.md`
- `zero-trust-warp-client-policies.md`
- `warp-connector-site-to-site-zero-trust.md`

---

## Sources

- Cloudflare IP ranges: https://www.cloudflare.com/ips/
- Cloudflare Tunnel documentation: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/
- Warp Connector private routing: https://developers.cloudflare.com/cloudflare-one/connections/connect-devices/warp/warp-connector/
- Workers TCP Sockets: https://developers.cloudflare.com/workers/runtime-apis/tcp-sockets/
- Smart Placement: https://developers.cloudflare.com/workers/configuration/smart-placement/
