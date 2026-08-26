# Carrier CGNAT and Shared Mobile Egress IPs vs Per-IP Rate Limiting

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Mobile users on cellular data hit 429s on example project auth and posting
routes while desktop users on the same endpoints sail through. A
whole carrier's subscribers in one city report "can't log in" at the
same time. One abuser triggers an IP ban and support tickets spike
from thousands of innocent users on the same carrier. Login velocity
checks flag legitimate users as credential stuffers because "50
different accounts logged in from this IP in an hour" — which is
normal for a carrier egress IP. Fraud heuristics score mobile
traffic as riskier despite bot scores showing it is mostly human.

## Context

Mobile carriers do not have enough IPv4 addresses to give each
subscriber one. They deploy Carrier-Grade NAT (CGNAT): subscribers
get addresses from the RFC 6598 Shared Address Space
(100.64.0.0/10) inside the carrier network, and a CGN gateway
translates them to a small pool of public IPv4 egress addresses.
A single public IPv4 address may represent hundreds or even
thousands of concurrent users. Cloudflare's 2025 research found
that despite near-identical human/bot score distributions, CGNAT
IPs get rate limited about three times more often than non-CGNAT
IPs — pure collateral damage. For example project (anonymous-first, no
stable account identity pre-login, per-IP limits on 133+ Worker
routes) the IP is a tempting identity key, which makes this
asymmetry a direct product problem: entire carriers throttled on
mobile while home-broadband desktop users are unaffected.

## How CGNAT concentrates users behind one IP

```
Subscriber phone        Carrier network           Public internet
─────────────────────────────────────────────────────────────────
10.x / 100.64.0.0/10 →  CGN gateway (NAT44)  →   1 public IPv4
(RFC 6598 shared        port-block allocation     shared by
 address space)         per subscriber            100s-1000s users

Key numbers
─────────────────────────────────────────────────────────────────
100.64.0.0/10          ~4M addresses, reserved by RFC 6598 for
                       ISP-internal CGNAT numbering (not RFC 1918)
Users per public IP    hundreds to thousands (varies by carrier;
                       highest density in Africa, C/SE Asia)
Rate-limit disparity   CGNAT IPs limited ~3x more often than
                       non-CGNAT (Cloudflare, 2025) despite
                       equivalent human-likeness (bot score
                       medians 4.8% vs 4.7%)
Port allocation        each subscriber gets a source-port block;
                       the public IP:port pair is unique, but
                       your app only ever sees the IP
```

## The mobile vs desktop asymmetry

```
Property               Home broadband        Mobile carrier
─────────────────────────────────────────────────────────────────
Users per public IP    1 household           100s-1000s
IP stability           days-months           minutes-hours
                                             (rotates across pool)
Per-IP rate limit      one household's       aggregate of all
counts                 traffic               subscribers on egress
1 abuser's blast       1 household           every subscriber on
radius when banned                           that egress IP
Login velocity per IP  low, plausible        high, and NORMAL
Consequence: identical per-IP thresholds are strict for mobile
and lax for desktop. "Fair" per-IP limits are not fair.
```

An innocent aggregate trips limits: if 300 subscribers share one
egress IP and each makes 2 auth requests in 10 minutes, that IP
"made" 600 auth requests — past almost any credential-stuffing
threshold, with zero attackers present.

## IPv6: partial relief, new granularity trap

```
Carriers increasingly dual-stack: IPv6-native phone traffic
bypasses CGNAT entirely (each subscriber gets a unique prefix,
typically a /64). But:

  - IPv6 adoption still lags; CGNAT remains for v4-only paths
    and v4-only destinations. Serve AAAA records so dual-stack
    phones reach you over v6 and exit the shared-IP pool.

  - Per-address (/128) limiting on v6 is TOO FINE: one phone
    can rotate thousands of privacy addresses within its /64,
    trivially evading per-address limits while legit users churn
    counters. Key v6 limits on the /64 prefix (optionally add
    coarser /56 and /48 tiers with higher thresholds).

  - Per-IP on v4 is TOO COARSE for mobile (whole carrier egress).

Rule of thumb: v4 → per-IP is over-aggregated for mobile;
v6 → per-address is under-aggregated. Prefix/64 for v6,
session-keyed for v4.
```

## Better rate-limit keys on Cloudflare

Cloudflare rate limiting rules support counting characteristics
beyond `ip.src`: header value, cookie value, query param, ASN
(`ip.src.asnum`), JA3/JA4 (`cf.bot_management.ja3_hash`,
`cf.bot_management.ja4`), JWT claims, and `cf.unique_visitor_id`
("IP with NAT support", cookie-based). Availability varies by
plan; custom characteristics need Advanced Rate Limiting.

```
Route class        Prefer key                    Fallback sub-key
─────────────────────────────────────────────────────────────────
Authenticated API  session cookie / bearer sub   ip.src + JA4
Login (pre-auth)   per-username (form field or   ip.src + JA4
                   normalized body value)
Signup / anon      device_id cookie set at       ip.src + JA4,
                   first paint                   higher threshold
Payment webhooks   provider signature id — do    n/a (allowlist
                   NOT per-IP limit these        provider ASNs)
```

```js
// Workers-level token bucket in a Durable Object, keyed by
// session (falls back to ip+ja4 sub-key for anonymous traffic)
export default {
  async fetch(req, env) {
    const session = getCookie(req, "example project_session");
    const ja4 = req.cf?.botManagement?.ja4 ?? "noja4";
    const ip = req.headers.get("CF-Connecting-IP");
    // Session first; only anonymous traffic shares the IP key,
    // and JA4 splits one carrier IP into client-stack cohorts.
    const key = session ? `s:${session}` : `ip:${ip}:${ja4}`;
    const id = env.RATE_LIMITER.idFromName(key);
    const res = await env.RATE_LIMITER.get(id)
      .fetch("https://rl/take", { method: "POST" });
    if (res.status === 429)
      return new Response("slow down", { status: 429,
        headers: { "Retry-After": "30" } });
    return handle(req, env);
  },
};
```

## Detecting CGNAT cohorts and tuning thresholds

```
Detection signals in your logs / analytics
─────────────────────────────────────────────────────────────────
Sessions per IP        many distinct session/device IDs per IP
                       per hour → shared egress
ASN                    known mobile-carrier ASNs (T-Mobile,
                       Vodafone, Jio, ...); maintain a list from
                       ip.src.asnum in Workers Analytics Engine
User-Agent spread      one IP, dozens of distinct mobile UAs
Port behavior          n/a — you never see the source port map
Cloudflare research    detects CGNAT via traceroutes crossing
                       100.64.0.0/10, WHOIS/PTR keywords
                       ("cgnat", "lsn"), ML classifier

Tuning once identified
─────────────────────────────────────────────────────────────────
Mobile-carrier ASNs    separate rate limit rules with N×
                       higher per-IP thresholds, or skip per-IP
                       and rely on session/JA4 keys entirely
Blocks and bans        ban the session/account/device, never the
                       bare IP, on carrier ASNs; time-box any IP
                       block to minutes, not days
cf.threat_score /      do not hard-block on IP reputation for
IP reputation          carrier ASNs — one abuser poisons the
                       score for thousands; use it only as one
                       weak signal combined with per-session data
Challenges > blocks    managed challenge lets innocent cohort
                       members pass; a block stops all of them
```

## Anti-patterns

- **Per-IP limits on auth with one global threshold** — strict for
  carrier egress IPs, lax for desktop. Key on username/session and
  use IP only as a secondary, high-threshold guard.
- **Permanent IP bans for abuse** — on mobile carrier IPs this bans
  thousands of innocent users, and the abuser rotates to a new
  egress IP in minutes anyway. Ban the account/session/device.
- **"Many accounts from one IP = fraud ring"** — on CGNAT that is
  the baseline. Velocity heuristics must normalize by ASN type or
  by observed sessions-per-IP before scoring.
- **Rate limiting IPv6 by full /128 address** — evadable via
  privacy-address rotation within the user's /64; limit by prefix.
- **Treating IP as identity in an anonymous-first app** — for
  example project, mint a device/session identifier early (first response
  sets a cookie) so limits attach to something that is actually
  per-user.

## Gotchas

- **Cookie/header keys are spoofable pre-validation** — an attacker
  can randomize a session cookie to dodge session-keyed limits.
  Keep a coarse per-IP+JA4 backstop with a high threshold, and
  reject unknown session IDs at the origin before counting them.
- **JA4 is shared across identical client stacks** — all users of
  the same app version on the same OS share a JA4, so JA4 alone is
  a cohort key, not an identity; it only sub-divides an IP.
- **The same carrier IP rotates under a user mid-session** — CGNAT
  mappings churn, so a user's requests hop between egress IPs.
  IP-bound sessions or CSRF checks tied to IP will break mobile
  users; never pin sessions to an IP.
- **Payment webhooks arrive from provider IP ranges, not users** —
  a per-IP limit shared with user traffic can drop legitimate
  webhook retries. Verify signatures instead of counting IPs.
- **`cf.unique_visitor_id` requires cookies** — first request has
  none, and cookie-less clients (some in-app webviews, curl) fall
  back to shared counting; design the anonymous tier around that.
- **Age-verification and login flows cluster in time** — example project's
  21+ gate makes evening spikes from one carrier IP look like an
  attack; whitelist-tune those routes for carrier ASNs first.

## Verification

- Auth and posting routes keyed on session/username, with per-IP
  only as a high-threshold backstop combined with JA4.
- IPv6 enabled end-to-end; v6 limits keyed on /64 prefix, not
  /128 address.
- Dashboard tracks distinct sessions per IP per hour and flags IPs
  above a shared-egress threshold; top offenders map to known
  mobile-carrier ASNs, not to abuse.
- Separate rate limiting rules exist for mobile-carrier ASNs with
  raised thresholds or session-only keys.
- Abuse response bans accounts/devices, and any IP-level block on
  a carrier ASN is a short-TTL managed challenge, not a ban.
- 429 rate segmented mobile vs desktop is roughly equal; before
  tuning it was mobile-skewed.

## Related

- `documentation/categories/cloudflare/waf-rate-limiting-deep-dive.md`
- `documentation/categories/cloudflare/icloud-private-relay-geolocation-rate-limiting.md`
- `documentation/categories/security/x-forwarded-for-client-ip-spoofing.md`

## Source URLs (verified 2026-08-17)

- One IP address, many users: detecting CGNAT —
  https://blog.cloudflare.com/detecting-cgn-to-reduce-collateral-damage/
- Cloudflare rate limiting parameters —
  https://developers.cloudflare.com/waf/rate-limiting-rules/parameters/
- Introducing Advanced Rate Limiting —
  https://blog.cloudflare.com/advanced-rate-limiting/
- RFC 6598: Shared Address Space (100.64.0.0/10) —
  https://datatracker.ietf.org/doc/html/rfc6598
- The scary state of IPv6 rate-limiting —
  https://adam-p.ca/blog/2022/02/ipv6-rate-limiting/
