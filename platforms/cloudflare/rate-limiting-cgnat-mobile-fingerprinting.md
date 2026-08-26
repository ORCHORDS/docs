# Rate Limiting Under CGNAT: Protecting Anonymous Mobile Traffic

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Legitimate mobile users receive HTTP 429 responses
disproportionately on cellular data (T-Mobile, Verizon, AT&T)
rather than Wi-Fi. A single scraper sharing a carrier CGNAT pool
trips the per-IP threshold; the 429 then lands on every other
subscriber egressing through that pool. Support tickets say
"I keep getting blocked" from users who are clearly not bots.
Tightening the threshold worsens false positives; loosening it
removes the protection. The abuser and victims share one counter.

## Context

example project is an anonymous platform: users interact without accounts,
so no application-layer user ID is available by default. The
platform runs on Cloudflare Workers and Pages with a large mobile
share. Carrier-grade NAT (CGNAT) places hundreds to tens of
thousands of real subscribers behind a single egress IPv4. Per-IP
rate limiting assumes one IP = one user — a structural falsehood
for carrier traffic. Cloudflare's 2025 research found CGNAT IPs
are rate-limited three times more often than non-CGNAT IPs despite
lower bot activity, confirming the collateral-damage pattern. On
an anonymous platform that cannot track by account, this is the
primary abuse-vs-access tension.

## Why IP-only counters collapse under CGNAT

Carrier IPs are not like residential IPs:

```
Traffic source         Approx. concurrent users per IPv4
──────────────────────────────────────────────────────────
Residential broadband  1–5   (one household/building)
Corporate office NAT   20–500
Mobile carrier CGNAT   1,000–50,000 (regional P-GW/UPF)
```

Well-known US mobile carrier ASNs (non-exhaustive):

```
AS21928  T-Mobile USA
AS22394  Verizon Wireless
AS20057  AT&T Mobility
AS5765   AT&T (additional ranges)
```

When one rule counts on IP alone, a single scraper in a CGNAT
pool fills the shared counter bucket; the mitigation window then
drops every other subscriber in that pool for its entire
duration. RFC 6598 defines 100.64.0.0/10 as CGNAT shared space;
some carriers leak internal CGNAT addresses on traceroute hops,
which is a reliable detector, but the simplest signal in
Cloudflare's stack is the carrier ASN.

## Per-session identity: JA4, _cfuvid, Turnstile, and cookies

Cloudflare offers several characteristics beyond bare IP:

```
Characteristic        Caveats / plan
──────────────────────────────────────────────────────────
IP with NAT support   Sets _cfuvid cookie; fails for cookie-
(cf.unique_visitor_   rejecting clients, private browsing,
id)                   native apps. All paid plans.
JA4 fingerprint       Enterprise Bot Management required;
                      absent over plain HTTP; shared through
                      corporate proxies.
Session/app cookie    example project is anonymous — no app cookie
(named cookie value)  by default; only useful post-login.
Turnstile token       One-time-use; must be extracted in
                      Worker logic, not a native WAF field.
JWT claim             API Shield token validation (Enterprise)
                      in WAF; Workers RateLimit binding for
                      all plans.
```

For example project's anonymous context, the practical options are:
- **IP with NAT** on browser-facing routes.
- **JA4** as a secondary key if Bot Management is active.
- **Turnstile + Workers RateLimit** on high-risk write
  endpoints where a session token can identify the user.

## Per-session vs per-IP WAF rate limit rule design

Layer rules so CGNAT users get per-device counters on routes
where a browser (and therefore the _cfuvid cookie) is expected:

```
Rule  Path / method          Characteristic       Action
──────────────────────────────────────────────────────────
1     POST /api/submit/*     IP with NAT + Path   Block 429
                                                  20 req/60 s
2     /api/* all methods     IP + Country + Path  Managed
                                                  Challenge
                                                  200 req/60 s
3     entire zone (catch)    IP only              Block 429
                                                  500 req/60 s
```

Rule 1 uses `cf.unique_visitor_id`; Cloudflare sets _cfuvid
automatically when "IP with NAT support" is chosen as a
characteristic. Rule 3 is a coarse IP backstop for API
clients that never accept cookies.

WAF match expression for rule 1:

```
(http.request.uri.path wildcard "/api/submit/*"
  and http.request.method eq "POST")
```

Characteristics: `cf.unique_visitor_id` + `http.request.uri.path`

Note: _cfuvid is absent on the first request; that request
uses the IP-only bucket. Single-request bursts are not
individualised by the cookie.

## Workers RateLimit binding: JWT-claim-based limiting

The Workers RateLimit binding (GA September 2025) accepts any
string key, making it immune to CGNAT: extract the JWT `sub`
claim (or a Turnstile token hash) and rate-limit on that
identity instead of the IP.

wrangler.jsonc + Worker handler:

```jsonc
// wrangler.jsonc
{ "ratelimits": [{ "name": "SUBMIT_LIMITER",
    "namespace_id": "1001",
    "simple": { "limit": 20, "period": 60 } }] }
```

```typescript
// src/index.ts
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const auth = req.headers.get("Authorization") ?? "";
    const token = auth.replace(/^Bearer\s+/i, "");
    const sub = extractSubClaim(token, env); // verify+return sub
    const ip =
      req.headers.get("CF-Connecting-IP") ?? "unknown";
    // JWT identity when present; bare IP as fallback
    const key = sub ? `jwt:${sub}` : `ip:${ip}`;

    const { success } =
      await env.SUBMIT_LIMITER.limit({ key });
    if (!success) {
      return Response.json(
        { error: "rate_limited" }, { status: 429 }
      );
    }
    return handleRequest(req, env);
  },
};
```

Constraints:
- Period: exactly 10 s or 60 s — no other values.
- Counters are per-PoP, not global. For global quotas,
  use Durable Objects with SQLite storage instead.
- Counter updates are async; near-zero added latency.

## WAF actions, plan tiers, and CGNAT carrier detection

WAF rate limit actions by plan:

```
Action             Plans            Behaviour
──────────────────────────────────────────────────────────
Log                All              Record only; no block.
Managed Challenge  All              Cloudflare picks type;
                                    best mobile pass rate.
Block (429)        All              Drop request; custom
                                    JSON body supported.
Throttle           Enterprise only  Pass traffic below the
                                    limit; block surplus.
```

Use **Block** on API/webhook routes where a browser is never
expected. Use **Managed Challenge** on HTML routes where a
real mobile user might be caught by CGNAT collateral; the
managed variant auto-passes most humans and is Cloudflare's
recommended action for WAF rules targeting suspect browser
traffic.

Detecting CGNAT vs residential in Workers and WAF:

```typescript
// Workers — request.cf fields
const asn = req.cf?.asn;            // integer e.g. 21928
const org = req.cf?.asOrganization; // string "T-Mobile USA"

const CARRIER_ASNS = new Set([21928, 22394, 20057]);
const isMobileCarrier = CARRIER_ASNS.has(asn ?? 0);

// Apply a looser limit or different key strategy
const key = isMobileCarrier && sub
  ? `jwt:${sub}`
  : `ip:${req.headers.get("CF-Connecting-IP")}`;
```

In WAF rule expressions, use `ip.src.asnum` (integer):

```
ip.src.asnum in {21928 22394 20057}
```

`cf.asOrganization` is available in Workers as
`request.cf.asOrganization` but is **not** available as a
field in WAF ruleset expressions — use `ip.src.asnum` there.

## Anti-patterns

- **IP-only rule zone-wide.** One CGNAT abuser 429's thousands
  of legitimate subscribers. Use `cf.unique_visitor_id` on
  browser paths.
- **Blocking the entire carrier ASN.** `ip.src.asnum eq 21928`
  blocks all T-Mobile subscribers. Use Managed Challenge or a
  raised threshold scoped to specific paths instead.
- **_cfuvid on native-app or API paths.** Native clients reject
  cookies; the shared IP fallback bucket exhausts immediately.
- **JA4 without Bot Management.** The characteristic silently
  falls back to IP when the field is absent.
- **Workers RateLimit key = bare IP on CGNAT traffic.** Same
  collateral damage as WAF IP-only, different layer.
- **mitigation_timeout > 0 with a challenge action on
  Free/Pro/Business.** The API requires timeout = 0 for
  challenge actions on those plans.

## Gotchas

- **_cfuvid absent on first request.** IP-only bucket handles
  it; cookie counting starts from request two. Single-request
  bursts are not individualised.
- **Workers RateLimit periods: 10 s or 60 s only.** Other
  windows require Durable Objects.
- **PoP-local counters.** The Workers binding counts per
  Cloudflare location, not globally — cross-PoP users get
  fresh counters.
- **`ip.src.asnum` is an integer in WAF expressions.** Write
  `ip.src.asnum in {21928 22394}`, not string-quoted values.
- **Turnstile tokens are single-use.** The same response
  token cannot be a rate-limit key across requests.
- **CGNAT IPs are rate-limited 3x more than non-CGNAT IPs**
  even without deliberate abuse (Cloudflare research, 2025).
  Baseline before tuning thresholds.

## Verification

- After enabling "IP with NAT support", confirm _cfuvid
  appears in browser dev-tools after the first request to a
  rate-limited endpoint.
- curl (no cookie jar) to the same endpoint should exhaust
  the IP-fallback bucket independently of the cookie bucket.
  Verify the two counters are isolated.
- Send 21 requests in 60 s from a single JWT `sub` claim
  via the Workers binding; confirm request 21 returns 429
  while a distinct `sub` value continues to pass through.
- In Security → Events, filter by ASN 21928/22394/20057.
  Confirm "Block" action rate is below 1% on those ASNs
  for non-abusive traffic after switching to per-session
  characteristics.
- Logpush `http_requests` dataset: cross-reference
  `ClientASN` (carrier ASNs) against `EdgeRateLimitAction`
  to quantify collateral damage before and after the change.

## Related

- `documentation/categories/cloudflare/waf-rate-limiting-deep-dive.md`
- `documentation/categories/cloudflare/bot-fingerprinting-native-app-traffic-false-positives.md`
- `documentation/categories/cloudflare/managed-challenge-mobile-browser-pass-rates.md`
- `documentation/categories/cloudflare/geolocation-accuracy-mobile-carrier-roaming.md`
- `documentation/categories/cloudflare/turnstile-best-practices.md`

## Source URLs (verified 2026-08-17)

- Rate limiting parameters (characteristics, plan tiers) —
  https://developers.cloudflare.com/waf/rate-limiting-rules/parameters/
- Rate limiting best practices —
  https://developers.cloudflare.com/waf/rate-limiting-rules/best-practices/
- Workers RateLimit binding (GA September 2025) —
  https://developers.cloudflare.com/workers/runtime-apis/bindings/rate-limit/
- Cloudflare Blog: One IP address, many users — detecting
  CGNAT to reduce collateral effects (October 2025) —
  https://blog.cloudflare.com/detecting-cgn-to-reduce-collateral-damage/
- Cloudflare Blog: Multi-User IP Address Detection —
  https://blog.cloudflare.com/multi-user-ip-address-detection/
- Cloudflare Blog: Introducing Advanced Rate Limiting —
  https://blog.cloudflare.com/advanced-rate-limiting/
