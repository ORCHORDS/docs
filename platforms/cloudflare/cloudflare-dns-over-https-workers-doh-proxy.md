# Cloudflare Workers as a DNS-over-HTTPS (DoH) Proxy

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

You need a custom DNS-over-HTTPS endpoint — to filter domains, log queries for compliance,
rewrite responses for split-horizon DNS, or front a private resolver — without running
your own infrastructure. Alternatively you want to inspect or modify DNS queries at the
edge before forwarding to an upstream resolver such as `1.1.1.1` or your own private
recursive resolver over Cloudflare Tunnel.

## Context

DNS-over-HTTPS (RFC 8484) carries DNS wire-format messages inside HTTP/2 POST or GET
requests to `https://<host>/dns-query`. Browsers (Firefox, Chrome), operating systems
(macOS Ventura+, iOS 14+), and client tools (curl, dnscrypt-proxy) all support it
natively. A Cloudflare Worker can speak RFC 8484, decode the DNS message, apply
policy, and proxy to an upstream DoH endpoint entirely within the edge — zero origin
servers required.

Workers can parse DNS wire format in pure JavaScript using DataView, forward to
Cloudflare's `https://cloudflare-dns.com/dns-query`, and return the binary response
with `Content-Type: application/dns-message`. The entire round-trip stays within
Cloudflare's network.

## Decoding a DNS Wire-Format Query

A DoH GET request encodes the DNS message as base64url in the `?dns=` parameter.
A POST request sends the raw binary body with `Content-Type: application/dns-message`.

```typescript
// src/dns.ts
export interface DnsQuestion {
  name: string;
  type: number;
  class: number;
}

/** Parse the QNAME from a DNS wire-format message starting at offset 12. */
export function parseQuestion(buf: Uint8Array): DnsQuestion {
  let offset = 12; // skip header
  const labels: string[] = [];

  while (offset < buf.length) {
    const len = buf[offset++];
    if (len === 0) break;
    // handle compression pointer (0xC0 prefix) — not expected in question section
    labels.push(
      String.fromCharCode(...buf.slice(offset, offset + len))
    );
    offset += len;
  }

  const type  = (buf[offset] << 8) | buf[offset + 1];
  const cls   = (buf[offset + 2] << 8) | buf[offset + 3];

  return { name: labels.join('.').toLowerCase(), type, class: cls };
}

const DNS_TYPE_NAMES: Record<number, string> = {
  1: 'A', 2: 'NS', 5: 'CNAME', 6: 'SOA', 15: 'MX',
  16: 'TXT', 28: 'AAAA', 33: 'SRV', 65: 'HTTPS',
};

export function typeName(t: number): string {
  return DNS_TYPE_NAMES[t] ?? `TYPE${t}`;
}
```

## Worker Handler: RFC 8484 GET and POST

```typescript
// src/index.ts
import { parseQuestion, typeName } from './dns';

const UPSTREAM = 'https://cloudflare-dns.com/dns-query';

// Domains blocked at the edge (returned NXDOMAIN via upstream NOERROR workaround
// or synthesised REFUSED — simplest: return 0-TTL NXDOMAIN)
const BLOCKLIST = new Set([
  'malware.example.com',
  'ads.tracker.io',
]);

export interface Env {
  // Optional: KV for dynamic blocklist entries
  BLOCKLIST_KV?: KVNamespace;
  // Optional: Analytics Engine for query logging
  DNS_ANALYTICS?: AnalyticsEngineDataset;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname !== '/dns-query') {
      return new Response('Not found', { status: 404 });
    }

    // Resolve DNS message bytes
    let dnsMsg: Uint8Array;

    if (request.method === 'GET') {
      const param = url.searchParams.get('dns');
      if (!param) return new Response('Missing dns param', { status: 400 });
      // base64url → Uint8Array
      const b64 = param.replace(/-/g, '+').replace(/_/g, '/');
      const binary = atob(b64);
      dnsMsg = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) dnsMsg[i] = binary.charCodeAt(i);
    } else if (request.method === 'POST') {
      const ct = request.headers.get('content-type') ?? '';
      if (!ct.includes('application/dns-message')) {
        return new Response('Unsupported Content-Type', { status: 415 });
      }
      dnsMsg = new Uint8Array(await request.arrayBuffer());
    } else {
      return new Response('Method not allowed', { status: 405 });
    }

    // Parse question for policy enforcement
    let question = { name: '', type: 0, class: 0 };
    try {
      question = parseQuestion(dnsMsg);
    } catch {
      // Malformed — pass through and let upstream reject it
    }

    // Log to Analytics Engine (fire-and-forget)
    if (env.DNS_ANALYTICS && question.name) {
      ctx.waitUntil(
        Promise.resolve(
          env.DNS_ANALYTICS.writeDataPoint({
            blobs: [question.name, typeName(question.type)],
            indexes: [question.name],
          })
        )
      );
    }

    // Blocklist check (static + optional KV override)
    const isBlocked =
      BLOCKLIST.has(question.name) ||
      (env.BLOCKLIST_KV
        ? !!(await env.BLOCKLIST_KV.get(`block:${question.name}`))
        : false);

    if (isBlocked) {
      // Synthesise REFUSED response (RCODE=5) by flipping bits in the header
      const refused = new Uint8Array(dnsMsg.length);
      refused.set(dnsMsg);
      // Byte 2: QR=1(response), Opcode=0, AA=0, TC=0, RD=1
      refused[2] = 0x81;
      // Byte 3: RA=1, Z=0, RCODE=5 (REFUSED)
      refused[3] = 0x85;
      return new Response(refused, {
        status: 200,
        headers: { 'Content-Type': 'application/dns-message', 'Cache-Control': 'no-store' },
      });
    }

    // Forward to upstream
    const upstreamResp = await fetch(UPSTREAM, {
      method: 'POST',
      headers: { 'Content-Type': 'application/dns-message', 'Accept': 'application/dns-message' },
      body: dnsMsg,
    });

    if (!upstreamResp.ok) {
      return new Response('Upstream error', { status: 502 });
    }

    const responseBody = await upstreamResp.arrayBuffer();

    return new Response(responseBody, {
      status: 200,
      headers: {
        'Content-Type': 'application/dns-message',
        // Cache positive answers; DoH clients respect this
        'Cache-Control': upstreamResp.headers.get('cache-control') ?? 'max-age=30',
      },
    });
  },
};
```

## wrangler.toml Configuration

```toml
name       = "doh-proxy"
main       = "src/index.ts"
compatibility_date = "2025-09-01"

[[kv_namespaces]]
binding  = "BLOCKLIST_KV"
id       = "<your-kv-namespace-id>"

[[analytics_engine_datasets]]
binding  = "DNS_ANALYTICS"
dataset  = "dns_queries"

[observability]
enabled = true
```

Deploy to a custom domain such as `doh.yourdomain.com` so clients can point to
`https://doh.yourdomain.com/dns-query`.

## Configuring Clients to Use Your DoH Endpoint

**Firefox** (about:config):
```
network.trr.mode       = 3          # TRR-only (strict)
network.trr.uri        = https://doh.yourdomain.com/dns-query
network.trr.custom_uri = https://doh.yourdomain.com/dns-query
```

**Chrome / Chromium** (Settings → Privacy → Security → Use secure DNS):
Select "Custom" and enter `https://doh.yourdomain.com/dns-query`.

**curl**:
```bash
curl --doh-url https://doh.yourdomain.com/dns-query https://example.com
```

**iOS 14+** — deploy a `.mobileconfig` with `DNSSettings` key pointing to
`ServerURL = "https://doh.yourdomain.com/dns-query"`.

## Anti-patterns

- **Caching DNS responses in Workers KV** — DNS TTLs can be seconds; KV has a minimum
  1-second write cost and eventual consistency. Let HTTP `Cache-Control` from the upstream
  handle caching at the Cloudflare CDN layer instead.
- **Parsing the full DNS response** — You rarely need to decode the answer section in
  the Worker. Parse only the question section for policy decisions; forward the binary
  response blob untouched.
- **Using `fetch()` with `GET + ?dns=` to upstream** — Some upstreams have URL length
  limits. Always POST binary bodies for reliability.
- **Blocking by returning a non-2xx HTTP status** — DoH clients interpret HTTP errors
  as network failures, not DNS failures. Return HTTP 200 with a synthetically crafted
  REFUSED or NXDOMAIN DNS response inside the body.

## Gotchas

- **EDNS Client Subnet (ECS)** — Cloudflare's upstream strips ECS by default for
  privacy. If your use-case requires geo-aware DNS answers, use a resolver that
  preserves ECS and accept the privacy trade-off.
- **Workers subrequest budget** — Each DoH query consumes one subrequest. The default
  limit is 50 subrequests per invocation; a single DoH request uses exactly 1, so
  you're safe unless you fan out to multiple upstreams for redundancy.
- **Binary response integrity** — Do not run the upstream response through
  `response.text()` or `response.json()`. Use `response.arrayBuffer()` to preserve
  the binary wire format.
- **`Expect: 100-continue`** — Some DNS clients send this header. Workers transparently
  handle it; the upstream fetch ignores it. No action required.
- **Workers free tier CPU limit** — Each query parses a small binary blob; CPU usage
  is under 1 ms. Even at high QPS the free 10 ms CPU limit per invocation is not a
  concern, but subrequest latency to the upstream (~5-15 ms) dominates.
- **HTTPS record type (65)** — Modern browsers query HTTPS records before A/AAAA.
  Your blocklist should also block HTTPS queries for blocked domains to prevent
  fallback resolution paths.

## Verification

```bash
# Test GET method (base64url-encode a minimal A query for example.com)
DNS_MSG=$(python3 -c "
import base64, struct
# Header: ID=0xABCD, QR=0, OPCODE=0, RD=1, QDCOUNT=1
hdr = struct.pack('!HHHHHH', 0xABCD, 0x0100, 1, 0, 0, 0)
# QNAME: 7example3com0
qname = b'\x07example\x03com\x00'
qtype = struct.pack('!HH', 1, 1)  # A IN
msg = hdr + qname + qtype
print(base64.urlsafe_b64encode(msg).rstrip(b'=').decode())
")

curl -s "https://doh.yourdomain.com/dns-query?dns=$DNS_MSG" \
  -H "Accept: application/dns-message" | xxd | head -4

# Test POST method
dig +short example.com @cloudflare-dns.com \
  | head -1   # baseline

# Full POST test via kdig (knot-dnsutils)
kdig example.com @https://doh.yourdomain.com/dns-query +https
```

Expected: a valid DNS wire-format response with RCODE=0 and one or more A records.

```bash
# Check Analytics Engine for logged queries (via GraphQL)
curl -s https://api.cloudflare.com/client/v4/graphql \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  --data-raw '{
    "query": "{ viewer { accounts(filter:{accountTag:\"<ACCOUNT_ID>\"}) { analyticsEngineAdaptiveGroups(table:\"dns_queries\" limit:5 filter:{datetimeGeq:\"2026-08-23T00:00:00Z\"}) { count dimensions { blob1 blob2 } } } } }"
  }'
```

## Related

- `cloudflare-workers-cron-triggers-scheduling.md` — scheduling periodic blocklist refreshes
- `workers-kv-bulk-operations-list-pagination.md` — managing large KV blocklists
- `cloudflare-tunnel-private-service-ingress.md` — forwarding DoH to an internal resolver
- `cloudflare-workers-analytics-engine-custom-metrics.md` — query logging and analytics
- `workers-tcp-sockets-connect-api.md` — DNS-over-TLS (DoT) alternative via TCP sockets

## Sources

- RFC 8484 — DNS Queries over HTTPS (DoH): https://datatracker.ietf.org/doc/html/rfc8484
- Cloudflare DoH endpoint documentation: https://developers.cloudflare.com/1.1.1.1/encryption/dns-over-https/
- Workers Fetch API: https://developers.cloudflare.com/workers/runtime-apis/fetch/
- Workers Analytics Engine: https://developers.cloudflare.com/analytics/analytics-engine/
- Workers KV: https://developers.cloudflare.com/kv/
