# Cloudflare Radar API Threat Intelligence in Workers

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
You want to enrich every inbound request with real-time Cloudflare Radar threat data — AS reputation, IP risk score, or country-level traffic anomaly signals — and make routing or blocking decisions at the edge without calling an external API from inside your origin.

## Context
Cloudflare Radar exposes a public REST API (`https://api.cloudflare.com/client/v4/radar/...`) that requires a Cloudflare API token with `Cloudflare Radar:Read` permissions. Workers can call this API as a subrequest, cache results in KV or the Cache API to avoid per-request latency, and combine Radar signals with the built-in `cf` object already available on every `Request`. The pattern below builds a lightweight threat-enrichment middleware layer.

## API Token & Bindings

`wrangler.toml`:
```toml
name = "threat-intel-middleware"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[[kv_namespaces]]
binding = "RADAR_CACHE"
id = "<kv-namespace-id>"

[vars]
RADAR_BASE = "https://api.cloudflare.com/client/v4/radar"
RADAR_CACHE_TTL = "300"   # seconds

[[secrets]]
# Set with: wrangler secret put RADAR_TOKEN
```

Create a scoped API token in the Cloudflare dashboard:
- Permissions: **Cloudflare Radar → Read**
- Token name: `workers-radar-readonly`

## Radar Cache Layer

```typescript
// src/radar.ts
export interface RadarASNInfo {
  asn: number;
  name: string;
  country: string;
  spamScore?: number;   // 0–100, higher = more spam
  maliciousScore?: number;
}

export interface RadarIPInfo {
  ip: string;
  asn: RadarASNInfo;
  isTor: boolean;
  isProxy: boolean;
  isHosting: boolean;
  threatScore: number; // synthesised 0–100
}

async function fetchFromRadar<T>(
  path: string,
  token: string,
  cacheKey: string,
  ttl: number,
  kv: KVNamespace
): Promise<T | null> {
  // Check KV cache first
  const cached = await kv.get(cacheKey, "json");
  if (cached !== null) return cached as T;

  const res = await fetch(`https://api.cloudflare.com/client/v4/radar${path}`, {
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    cf: { cacheTtl: ttl, cacheEverything: true },
  });

  if (!res.ok) {
    console.error(`Radar API ${path} returned ${res.status}`);
    return null;
  }

  const body = (await res.json()) as { result: T; success: boolean };
  if (!body.success) return null;

  // Persist to KV for cross-isolate sharing
  await kv.put(cacheKey, JSON.stringify(body.result), { expirationTtl: ttl });
  return body.result;
}

export async function getASNInfo(
  asn: number,
  token: string,
  kv: KVNamespace
): Promise<RadarASNInfo | null> {
  return fetchFromRadar<RadarASNInfo>(
    `/entities/asns/${asn}?format=json`,
    token,
    `radar:asn:${asn}`,
    3600, // ASN data changes slowly
    kv
  );
}

export async function getIPInfo(
  ip: string,
  token: string,
  kv: KVNamespace
): Promise<RadarIPInfo | null> {
  return fetchFromRadar<RadarIPInfo>(
    `/entities/ip?ip=${encodeURIComponent(ip)}&format=json`,
    token,
    `radar:ip:${ip}`,
    300,
    kv
  );
}
```

## Threat-Enrichment Middleware

```typescript
// src/index.ts
import { getIPInfo, getASNInfo, type RadarIPInfo } from "./radar";

export interface Env {
  RADAR_CACHE: KVNamespace;
  RADAR_TOKEN: string;
  RADAR_CACHE_TTL: string;
  UPSTREAM: Fetcher; // service binding to origin
}

interface ThreatContext {
  ip: string;
  asn: number | null;
  country: string;
  isTor: boolean;
  isProxy: boolean;
  isHosting: boolean;
  threatScore: number;
  blocked: boolean;
  reason: string;
}

const BLOCK_THRESHOLD = 75; // threatScore above this → block
const HIGH_RISK_ASNS = new Set([/* add known bad ASNs */]);

function buildThreatContext(
  req: Request,
  ipInfo: RadarIPInfo | null
): ThreatContext {
  const cf = req.cf as IncomingRequestCfProperties;
  const ip = req.headers.get("CF-Connecting-IP") ?? "0.0.0.0";
  const asn = cf.asn ? Number(cf.asn) : null;
  const country = cf.country ?? "XX";

  if (!ipInfo) {
    // Fallback to cf object signals only
    return {
      ip, asn, country,
      isTor: false, isProxy: false, isHosting: false,
      threatScore: 0, blocked: false, reason: "radar_unavailable",
    };
  }

  const blocked =
    ipInfo.threatScore >= BLOCK_THRESHOLD ||
    ipInfo.isTor ||
    (asn !== null && HIGH_RISK_ASNS.has(asn));

  return {
    ip, asn, country,
    isTor: ipInfo.isTor,
    isProxy: ipInfo.isProxy,
    isHosting: ipInfo.isHosting,
    threatScore: ipInfo.threatScore,
    blocked,
    reason: blocked
      ? ipInfo.isTor
        ? "tor_exit_node"
        : "high_threat_score"
      : "allowed",
  };
}

export default {
  async fetch(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const ip = req.headers.get("CF-Connecting-IP") ?? "";
    const ttl = parseInt(env.RADAR_CACHE_TTL, 10);

    // Fire IP lookup; do not block request if Radar is slow
    const ipInfoPromise = ip
      ? getIPInfo(ip, env.RADAR_TOKEN, env.RADAR_CACHE)
      : Promise.resolve(null);

    // Race: if Radar takes > 200 ms, continue without enrichment
    const ipInfo = await Promise.race([
      ipInfoPromise,
      new Promise<null>((resolve) => setTimeout(() => resolve(null), 200)),
    ]);

    const threat = buildThreatContext(req, ipInfo);

    if (threat.blocked) {
      // Log to Analytics Engine (optional binding omitted for brevity)
      console.warn(`Blocked ${threat.ip} reason=${threat.reason} score=${threat.threatScore}`);
      return new Response(
        JSON.stringify({ error: "Access denied", reason: threat.reason }),
        {
          status: 403,
          headers: { "Content-Type": "application/json" },
        }
      );
    }

    // Forward to origin with enrichment headers
    const enriched = new Request(req, {
      headers: new Headers({
        ...Object.fromEntries(req.headers),
        "X-Threat-Score": String(threat.threatScore),
        "X-Is-Tor": String(threat.isTor),
        "X-Is-Proxy": String(threat.isProxy),
        "X-Radar-Country": threat.country,
      }),
    });

    // Fire-and-forget: warm cache for next request
    ctx.waitUntil(
      ip && !ipInfo
        ? getIPInfo(ip, env.RADAR_TOKEN, env.RADAR_CACHE)
        : Promise.resolve()
    );

    return env.UPSTREAM.fetch(enriched);
  },
} satisfies ExportedHandler<Env>;
```

## Country-Level Anomaly Detection

```typescript
// Radar also exposes aggregate traffic stats by country
interface RadarTrafficAnomaly {
  timestamp: string;
  country: string;
  type: "ANOMALY" | "OUTAGE";
  status: "VERIFIED" | "UNVERIFIED";
}

async function getCountryAnomalies(
  country: string,
  env: Env
): Promise<RadarTrafficAnomaly[]> {
  const cacheKey = `radar:anomaly:${country}`;
  const cached = await env.RADAR_CACHE.get(cacheKey, "json");
  if (cached) return cached as RadarTrafficAnomaly[];

  const url = `https://api.cloudflare.com/client/v4/radar/traffic_anomalies?location=${country}&status=VERIFIED&limit=10&format=json`;
  const res = await fetch(url, {
    headers: { Authorization: `Bearer ${env.RADAR_TOKEN}` },
  });
  if (!res.ok) return [];

  const data = (await res.json()) as { result: { trafficAnomalies: RadarTrafficAnomaly[] } };
  const anomalies = data.result.trafficAnomalies ?? [];
  await env.RADAR_CACHE.put(cacheKey, JSON.stringify(anomalies), { expirationTtl: 600 });
  return anomalies;
}
```

## Anti-patterns
- **Calling Radar synchronously on every request without a cache** — each lookup adds 50–200 ms of latency and quickly exhausts rate limits (10,000 req/day on free tier).
- **Blocking the response path waiting for Radar** — use `Promise.race()` with a short timeout (150–250 ms) so Radar slowness never degrades user experience.
- **Storing the API token in `[vars]`** — use `wrangler secret put RADAR_TOKEN`; vars appear in plaintext in the dashboard.
- **Treating `isTor = true` as an unconditional block** — legitimate Tor users exist; prefer a CAPTCHA challenge (Turnstile) over a hard 403 unless your threat model demands it.
- **Caching per-IP data for too long** — IP reputation changes; 5 minutes (300 s) is a safe KV TTL for IP-level data; ASN data can be cached for hours.

## Gotchas
- The Radar `/entities/ip` endpoint returns `null` for RFC-1918 private addresses; always guard with `if (!ipInfo)`.
- `cf.asn` on the `Request` object is a string in Workers, not a number — coerce with `Number(cf.asn)`.
- Radar API rate limits are per account, shared across all Workers that use the same token; add KV caching aggressively.
- The `cf` object is only populated on real inbound requests; it is absent on subrequests you construct with `new Request(url)`.
- `threatScore` is a Cloudflare-internal synthesis field — its scale and composition are not publicly documented; treat it as a relative signal, not an absolute measure.

## Verification
1. `curl -H "CF-Connecting-IP: 8.8.8.8" https://<worker>/` — should pass through with `X-Threat-Score: 0`.
2. Set `BLOCK_THRESHOLD = 0` temporarily and confirm the Worker returns 403 for any IP.
3. Inspect KV namespace for `radar:ip:<ip>` entries after a few requests to confirm caching is working.
4. Check Cloudflare dashboard → Radar → API usage to ensure rate-limit headroom.

## Related
- `workers-bot-management-score-routing.md`
- `ddos-managed-rulesets-configuration.md`
- `cloudflare-workers-subrequests-fanout.md`
- `workers-tail-workers.md`
- `cloudflare-turnstile-invisible-widget-server-validation.md`

## Sources
- https://developers.cloudflare.com/radar/
- https://developers.cloudflare.com/radar/get-started/
- https://developers.cloudflare.com/fundamentals/api/reference/permissions/
