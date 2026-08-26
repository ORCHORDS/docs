# Cloudflare Spectrum — TCP Proxy with Workers and Analytics Engine

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
You run a custom binary TCP protocol (e.g. a game server or proprietary messaging bus) and want Cloudflare Spectrum to front it for DDoS protection and geo-routing. You also need a companion Worker to handle the HTTP upgrade path, bridge the TCP socket to your origin via `connect()`, and emit per-connection metadata to Analytics Engine for observability.

---

## Context
Cloudflare Spectrum proxies arbitrary TCP/UDP traffic through Cloudflare's network. When the client speaks HTTP and then upgrades, a Worker can intercept via `fetch` before handing the raw socket to the origin. The Workers `connect()` API opens a raw TCP socket to a backend. Analytics Engine lets you write structured data points (data sets) directly from a Worker without an external sink; each `writeDataPoint` call is non-blocking and survives Worker termination via the internal queue.

---

## Spectrum App configuration (Cloudflare Dashboard / API)
```toml
# Equivalent Terraform for reference
resource "cloudflare_spectrum_application" "tcp_proxy" {
  zone_id  = var.zone_id
  protocol = "tcp/4222"      # NATS port as example
  dns {
    type = "CNAME"
    name = "nats.example.com"
  }
  origin_direct = ["tcp://10.0.0.5:4222"]
  ip_firewall   = true
  tls           = "off"
  proxy_protocol = "v1"
}
```

## HTTP Upgrade + `connect()` Worker
```typescript
// src/tcp-proxy.ts
import { connect } from 'cloudflare:sockets';

export interface Env {
  ORIGIN_HOST: string; // e.g. "10.0.0.5"
  ORIGIN_PORT: string; // e.g. "4222"
  CONNECTION_ANALYTICS: AnalyticsEngineDataset;
}

function emitConnectionEvent(
  dataset: AnalyticsEngineDataset,
  clientIp: string,
  country: string | null,
  connected: boolean,
  durationMs: number
): void {
  dataset.writeDataPoint({
    blobs: [clientIp, country ?? 'unknown', connected ? 'ok' : 'error'],
    doubles: [durationMs],
    indexes: [clientIp],
  });
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const upgradeHeader = request.headers.get('Upgrade');
    if (!upgradeHeader || upgradeHeader.toLowerCase() !== 'tcp') {
      return new Response('Expected TCP upgrade', { status: 426 });
    }

    const clientIp = request.headers.get('CF-Connecting-IP') ?? 'unknown';
    const country = request.headers.get('CF-IPCountry');
    const startMs = Date.now();

    // Establish outbound TCP socket to origin
    const originSocket = connect({
      hostname: env.ORIGIN_HOST,
      port: parseInt(env.ORIGIN_PORT, 10),
    });

    // WebSocket pair bridges the HTTP upgrade to raw bytes
    const { 0: clientSide, 1: serverSide } = new WebSocketPair();
    const response = new Response(null, {
      status: 101,
      webSocket: serverSide,
    });

    serverSide.accept();

    // Pipe WebSocket messages to TCP origin
    const writer = originSocket.writable.getWriter();
    serverSide.addEventListener('message', (event) => {
      const data =
        typeof event.data === 'string'
          ? new TextEncoder().encode(event.data)
          : new Uint8Array(event.data as ArrayBuffer);
      writer.write(data).catch(() => serverSide.close(1011, 'write error'));
    });

    // Pipe TCP origin bytes back to WebSocket client
    ctx.waitUntil(
      (async () => {
        let connected = false;
        try {
          const reader = originSocket.readable.getReader();
          connected = true;
          while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            serverSide.send(value);
          }
        } catch {
          connected = false;
        } finally {
          serverSide.close(1000, 'origin closed');
          emitConnectionEvent(
            env.CONNECTION_ANALYTICS,
            clientIp,
            country,
            connected,
            Date.now() - startMs
          );
        }
      })()
    );

    serverSide.addEventListener('close', () => {
      writer.close().catch(() => {});
    });

    return response;
  },
};
```

## `wrangler.toml`
```toml
name = "tcp-proxy"
main = "src/tcp-proxy.ts"
compatibility_date = "2024-09-23"
compatibility_flags = ["nodejs_compat"]

[vars]
ORIGIN_HOST = "10.0.0.5"
ORIGIN_PORT = "4222"

[[analytics_engine_datasets]]
binding = "CONNECTION_ANALYTICS"
dataset = "tcp_connections"
```

---

## Anti-patterns
- **Buffering the entire TCP stream in memory** — stream chunk-by-chunk using the readable/writable pipe; buffering exhausts the Worker's 128 MB memory limit on long-lived connections.
- **Using `fetch()` instead of `connect()` for raw TCP** — `fetch()` speaks HTTP; only `connect()` from `cloudflare:sockets` gives you a raw TCP socket.
- **Ignoring backpressure on the writable writer** — always `await writer.write()` or implement a queue; fire-and-forget drops data under load.

---

## Gotchas
- `connect()` from `cloudflare:sockets` is only available in Workers; it is not available in Pages Functions or the local Miniflare dev server without the `--experimental-local` flag.
- Spectrum is an Enterprise-tier feature; the Worker-based upgrade path described here is a complementary pattern for HTTP clients, not a replacement for the Spectrum TCP proxy for binary clients.
- Analytics Engine `writeDataPoint` silently discards data points that exceed the schema limits (20 blobs, 20 doubles, 1 index); validate field counts before shipping.

---

## Verification
```bash
# Deploy Worker
wrangler deploy

# Test HTTP upgrade locally with websocat
websocat --binary ws://localhost:8787 -H "Upgrade: tcp"

# Query Analytics Engine via GraphQL
curl -X POST https://api.cloudflare.com/client/v4/graphql \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  --data '{"query": "{ viewer { accounts(filter: {accountTag: \"$ACCOUNT_ID\"}) { tcpConnectionsAdaptiveGroups(limit: 10, filter: {datetime_geq: \"2026-08-24T00:00:00Z\"}) { count } } } }"}'
```

---

## Related
- `cloudflare-tunnel-private-network-workers.md`
- `cloudflare-load-balancer-health-check-workers.md`

---

## Sources
- Cloudflare Spectrum — https://developers.cloudflare.com/spectrum/
- Workers `connect()` TCP sockets — https://developers.cloudflare.com/workers/runtime-apis/tcp-sockets/
- Analytics Engine — https://developers.cloudflare.com/analytics/analytics-engine/
