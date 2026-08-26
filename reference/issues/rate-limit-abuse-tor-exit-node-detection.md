# Rate-Limit Abuse and Tor Exit-Node Detection

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

Authenticated and anonymous endpoints on example.com receive coordinated bursts of
requests originating from Tor exit nodes, shared VPN egress IPs, and rotating
residential proxies.  Standard IP-based rate limits are trivially bypassed because
each circuit hop presents a different IP address.  Legitimate EU users behind Tor
trigger GDPR-sensitive signals (`cf.isEUCountry = true`) that must be handled
differently from non-EU traffic even when the underlying network is abusive.

## Context

example project is an anonymous 21+ social platform served entirely from Cloudflare Pages +
Workers.  The platform cannot rely on account-level session cookies for unauthenticated
discovery pages, meaning abuse mitigation must live at the Worker edge.  Cloudflare
exposes per-request intelligence fields in `request.cf` that can be combined with KV
sliding-window counters keyed on Autonomous System Number (ASN) rather than on IP.
This is resistant to IP rotation within the same hosting network while remaining fair
to legitimate residential users on large ISPs.

## Cloudflare `request.cf` Tor and Network Signals

The `request.cf` object available inside every Worker request provides the following
fields relevant to exit-node and proxy detection.

```
┌─────────────────────────────┬───────────────────────────────────────────────┐
│ Field                       │ Description                                   │
├─────────────────────────────┼───────────────────────────────────────────────┤
│ cf.asn                      │ Autonomous System Number of the client IP     │
│ cf.asOrganization           │ Human-readable ASN name                       │
│ cf.isEUCountry              │ "1" when country is in EU/EEA                 │
│ cf.country                  │ ISO-3166-1 alpha-2 country code               │
│ cf.botManagement.score      │ 1 (bot) – 99 (human); requires Bot Management │
│ cf.botManagement.verifiedBot│ true for known-good crawlers                  │
│ cf.threat                   │ 0–100 legacy threat score; ≥14 = suspicious   │
│ cf.clientTrustScore         │ 0–99; present only with Advanced Bot Mgmt     │
└─────────────────────────────┴───────────────────────────────────────────────┘
```

Tor exit nodes are not individually enumerable by Cloudflare in a public API, but they
cluster in a small set of well-known ASNs (Mullvad, Tor Project, Quintex Alliance,
various .onion hosting providers).  A hardcoded deny-list of ASN numbers covers the
majority of exit traffic without touching the Tor Browser fingerprint at all.

```ts
// worker/lib/torDetection.ts
const TOR_EXIT_ASNS = new Set([
  60729,  // Quintex Alliance Consulting
  4224,   // Tor Project exit relay cluster (illustrative)
  209588, // Flyservers S.A. – popular exit hosting
]);

export function isTorLike(cf: IncomingRequestCfProperties): boolean {
  if (TOR_EXIT_ASNS.has(cf.asn)) return true;
  // cf.threat >= 14 is Cloudflare's own "suspicious" threshold
  if ((cf.threat ?? 0) >= 14) return true;
  return false;
}
```

## KV Sliding-Window Rate Limit per ASN

Instead of keying the counter on the client IP (trivially rotated), key it on ASN.
A 60-second sliding window stored in Workers KV allows burst inspection without a
database round-trip.

```ts
// worker/lib/asnRateLimit.ts
export interface RateLimitResult {
  allowed: boolean;
  remaining: number;
  resetAt: number;
}

export async function checkAsnRateLimit(
  kv: KVNamespace,
  asn: number,
  limit: number,
  windowSecs: number,
): Promise<RateLimitResult> {
  const now = Math.floor(Date.now() / 1000);
  const windowKey = Math.floor(now / windowSecs);
  const key = `rl:asn:${asn}:${windowKey}`;

  const raw = await kv.get(key);
  const count = raw ? parseInt(raw, 10) : 0;

  if (count >= limit) {
    return { allowed: false, remaining: 0, resetAt: (windowKey + 1) * windowSecs };
  }

  // Increment; TTL is 2× the window so the previous bucket lingers for debugging
  await kv.put(key, String(count + 1), { expirationTtl: windowSecs * 2 });
  return { allowed: true, remaining: limit - count - 1, resetAt: (windowKey + 1) * windowSecs };
}
```

Recommended limits per endpoint class:

```
┌─────────────────────────────┬──────────┬─────────────────┬──────────────────┐
│ Endpoint                    │ Window   │ Limit (normal)  │ Limit (Tor-like) │
├─────────────────────────────┼──────────┼─────────────────┼──────────────────┤
│ POST /api/posts             │ 60 s     │ 30              │ 5                │
│ GET  /api/feed              │ 60 s     │ 120             │ 20               │
│ POST /api/auth/verify-age   │ 300 s    │ 5               │ 1                │
│ POST /api/reports           │ 3600 s   │ 10              │ 2                │
│ GET  /api/search            │ 60 s     │ 60              │ 10               │
└─────────────────────────────┴──────────┴─────────────────┴──────────────────┘
```

## EU-Country Handling with `cf.isEUCountry`

GDPR Article 22 prohibits purely automated decisions that produce legal or similarly
significant effects on EU data subjects without a human review mechanism.  Blocking an
EU user's request solely because they use Tor may constitute such a decision.  The
recommended approach is response shaping rather than hard blocking.

```ts
// worker/middleware/abuseGate.ts
export async function abuseGate(
  request: Request,
  env: Env,
  ctx: ExecutionContext,
): Promise<Response | null> {
  const cf = request.cf as IncomingRequestCfProperties;
  const tor = isTorLike(cf);
  const eu  = cf.isEUCountry === "1";

  const rl = await checkAsnRateLimit(env.KV_RATE_LIMIT, cf.asn, tor ? 5 : 30, 60);

  if (!rl.allowed) {
    if (eu) {
      // Shape: serve a degraded read-only response, never a hard block
      return new Response(JSON.stringify({ error: "rate_limited", readOnly: true }), {
        status: 429,
        headers: {
          "Retry-After": String(rl.resetAt - Math.floor(Date.now() / 1000)),
          "X-RateLimit-Reason": "asn-window",
          "Content-Type": "application/json",
        },
      });
    }
    // Non-EU: hard block with Cloudflare challenge page
    return new Response(null, { status: 403 });
  }

  return null; // allow
}
```

## Response Shaping Strategy

Hard-blocking Tor users degrades legitimate whistleblowers and privacy-conscious adults
who are the core audience for an anonymous platform.  A tiered response approach
preserves access while raising the cost of abuse.

```
┌──────────────────────────┬────────────────────────────────────────────────────┐
│ Abuse Signal Strength    │ Response Shape                                     │
├──────────────────────────┼────────────────────────────────────────────────────┤
│ None                     │ Normal response, full API                          │
│ Tor-like ASN only        │ Normal response, reduced rate limit                │
│ Tor-like + cf.threat≥14  │ 429 with Retry-After; read endpoints pass through │
│ Tor-like + bot score <20 │ Managed Challenge (Turnstile) injected             │
│ All three combined       │ 403 for write ops; GET feed still served           │
│ POST /auth + any Tor     │ 1 req / 5 min + mandatory Turnstile token          │
└──────────────────────────┴────────────────────────────────────────────────────┘
```

Turnstile can be triggered server-side by returning a `cf-mitigated: challenge`
response header, which Cloudflare intercepts and replaces with a managed challenge page
before the client sees it — no client-side JS changes needed.

## Anti-patterns

- Keying rate limits on `request.headers.get("CF-Connecting-IP")` — rotates per Tor
  circuit, approximately every 10 minutes per default Tor Browser settings.
- Storing sliding window state in Durable Objects per IP — creates unbounded DO
  namespace growth; KV with short TTLs is cheaper for transient counters.
- Blocking all `cf.threat >= 1` — Cloudflare assigns non-zero threat scores to many
  clean residential IPs; the "suspicious" threshold documented by Cloudflare is ≥ 14.
- Setting `expirationTtl = windowSecs` exactly — the counter disappears before the
  window ends if the initial write happened mid-window; use 2× as a buffer.
- Treating `cf.isEUCountry` as a privacy-safe pass: it is a network-layer heuristic
  based on IP geolocation, not a verified identity signal.

## Gotchas

- `cf.asn` is `0` for requests originating from Cloudflare's own infrastructure
  (Pages Functions calling Workers, Durable Objects, etc.).  Guard with
  `if (!cf.asn || cf.asn === 0) return null;` before rate-limiting.
- KV `get` returns `null`, not `"0"`, for a missing key.  Parsing `null` as an
  integer gives `NaN`; always default with `parseInt(raw ?? "0", 10)`.
- `cf.isEUCountry` is the string `"1"` (not boolean `true`) per Cloudflare docs.
  Strict equality `=== "1"` is required; `== true` will pass on the string.
- The `cf.botManagement` namespace is only populated on plans with Bot Management
  enabled.  Accessing `cf.botManagement.score` on a plan without it returns
  `undefined`, not a numeric value.  Guard with optional chaining.
- Workers KV has eventual-consistency guarantees; in very high-traffic scenarios two
  simultaneous requests to the same ASN+window key may both read `0` and both set `1`.
  For example project's scale this is acceptable; for stricter enforcement use Durable Objects.

## Verification

```bash
# 1. Simulate a Tor exit-node ASN in wrangler dev
curl -H "CF-Connecting-IP: 1.2.3.4" \
     -H "X-Forwarded-For: 1.2.3.4" \
     http://localhost:8787/api/feed
# Expect: 200 with reduced X-RateLimit-Remaining

# 2. Trigger the ASN rate limit (loop 6 times for Tor tier limit of 5)
for i in $(seq 1 6); do
  curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8787/api/posts
done
# Expect: 200 200 200 200 200 429

# 3. Verify EU shaping returns readOnly flag
curl -v http://localhost:8787/api/posts 2>&1 | grep readOnly
# Expect: "readOnly":true in body when rate limited from EU country

# 4. Check KV counter in wrangler dashboard or via:
wrangler kv key get --namespace-id=$KV_RATE_LIMIT_ID "rl:asn:60729:$(date +%s | xargs -I{} expr {} / 60)"
```

## Related

- `platform-trust-score-cloudflare-signals.md`
- `anonymous-platform-abuse-prevention.md`
- `anonymous-content-reporting-worker-pipeline.md`
- `age-verification-cloudflare-workers-kyc.md`
- `worker-subrequest-limit.md`

## Sources

- Cloudflare Workers `request.cf` reference — developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
- Cloudflare Bot Management overview — developers.cloudflare.com/bots/
- Cloudflare Turnstile server-side validation — developers.cloudflare.com/turnstile/
- Workers KV — developers.cloudflare.com/kv/
- GDPR Article 22 — eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32016R0679
- Tor Project exit relay list — metrics.torproject.org/exonerator.html
