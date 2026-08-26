# iCloud Private Relay: Geolocation and Rate-Limit Skew on Safari

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

iPhone Safari users on example project intermittently hit 429s on auth and
posting routes that desktop users never see. Support tickets show
users in permitted regions being bounced by the 21+ geo-compliance
gate, or shown the wrong region's content. Audit logs record the
same client IP for dozens of unrelated accounts, and velocity/fraud
rules flag "many signups from one IP" bursts that are actually
legitimate, unrelated iPhone users. The skew is mobile-only and
Safari-only — Chrome on the same iPhone behaves normally.

## Context

iCloud Private Relay is Apple's two-hop proxy for iCloud+
subscribers (iOS 15+, iPadOS 15+, macOS Monterey+). It covers
Safari browsing, DNS queries, and insecure HTTP app traffic — so in
practice it is a mobile-Safari-skewed phenomenon: a large slice of
iPhone traffic arrives from relay egress IPs instead of the user's
real address. The first hop (ingress) is run by Apple and sees the
user's IP but not the destination; the second hop (egress) is run
by partner CDNs — Cloudflare itself, Akamai, and Fastly — and sees
the destination but not the user. Your Worker's `cf.ipcountry`,
per-IP rate limits, and audit IPs all observe the egress IP, which
is shared by many users and geolocated only to a coarse city or
region derived from a geohash of the user's real location.

## How the two-hop relay works

```
iPhone Safari                Apple ingress            CDN egress
(iCloud+ user)               (sees user IP,           (Cloudflare /
                             not destination)         Akamai / Fastly)
      │  QUIC/MASQUE tunnel        │                        │
      ├───────────────────────────►├───────────────────────►├──► example.com
      │                            │  coarse geohash only   │    (Worker sees
      │                            │                        │     egress IP)
──────────────────────────────────────────────────────────────
  What each party knows:
    Apple ingress   user IP            NOT the destination
    CDN egress      destination host   NOT the user IP
    Your Worker     egress IP only     never the real client IP

  Egress IPs prefer IPv6 when AAAA records exist; IPv6 egress
  is geolocated more precisely than IPv4. Relay IP is stable
  within a browsing session but rotates across sessions.
```

## Egress IPs and Apple's published geo feed

```
Apple publishes every egress range, updated regularly:

  https://mask-api.icloud.com/egress-ip-ranges.csv

  Format: CIDR, country, region, city
  ─────────────────────────────────────────────
  172.224.226.0/27,GB,GB-EN,London,
  172.224.226.32/31,GB,GB-SC,Aberdeen,
  172.224.226.36/31,GB,GB-EN,Luton,

Detection options (best to worst):
  1. Match request IP against the CSV ranges (refresh daily)
  2. Geo-IP DB org field = "iCloud Private Relay", or flags
     like is_relay / privacy_proxy / privacy_service
  3. Heuristic: relay range + Safari UA (relay IP with a
     non-Safari UA is itself an anomaly signal)

Note the location in the feed is the EGRESS location Apple
assigns — a coarse city/region near the user, not the user's
address. Country is generally preserved; city can be off.
```

## Impact on cf.ipcountry and geo-compliance gates

```
What breaks                      Why
──────────────────────────────────────────────────────────────
cf.ipcountry / cf.city checks    Reflect egress mapping, not
                                 the user's true location
Region gating (21+ states,       User near a border or in a
sanctioned regions)              small region may egress from
                                 a neighboring city/region
"Impossible travel" checks       Relay IP rotates between
                                 sessions → user "teleports"
Audit-log IP attribution         One egress IP = thousands of
                                 users; IP is not an identity

Country-level accuracy is usually maintained (Apple works
with geo providers to register mappings), so country gates
mostly hold. City/region gates are where mismatches surface.
Users can also pick "country and time zone" granularity in
iCloud settings, making city data deliberately coarser.
```

## Impact on per-IP rate limits and velocity rules

```
A single Private Relay egress IP concentrates traffic from
many unrelated iPhones behind one address — the same failure
mode as carrier-grade NAT, but affecting a wealthier, heavily
mobile-Safari demographic.

  Per-IP limit of 10 req/min on /api/auth/login:
    50 relay users behind one egress IP at peak
    → limit trips on aggregate traffic
    → random legitimate iPhone users get 429s
    → desktop users (no relay) never notice

  Velocity/fraud rules equally skewed:
    "N signups from one IP in an hour"  → false positives
    "IP seen with M distinct accounts"  → meaningless
    IP reputation scores               → diluted to noise

Treat relay ranges like CGNAT: expect high legitimate
per-IP request density and account density.
```

## Mitigations in a Worker

```javascript
// Rate-limit on better keys than bare IP.
const RELAY_RANGES = await getRelayRanges(env); // cached CSV

function rateLimitKey(request) {
  const ip = request.headers.get('CF-Connecting-IP');
  const session = getSessionId(request); // cookie / bearer sub
  if (session) return `s:${session}`;    // best: per-user
  if (isPrivateRelay(ip, RELAY_RANGES)) {
    // Shared IP: widen the key so one egress IP doesn't
    // pool all users into one bucket.
    const ja4 = request.cf.botManagement?.ja4 ?? 'na';
    return `r:${ip}:${ja4}:${request.cf.colo}`;
  }
  return `ip:${ip}`;
}

function geoDecision(request) {
  const { country, regionCode } = request.cf;
  const relay = isPrivateRelay(
    request.headers.get('CF-Connecting-IP'), RELAY_RANGES);
  // Country gates: keep enforcing (country is preserved).
  // Region/city gates: don't hard-fail relay users on IP
  // alone — fall back to declared region + secondary check.
  return { country, regionCode, ipAuthoritative: !relay };
}
```

For unauthenticated abuse control, prefer Private Access Tokens
(iOS 16+, Privacy Pass) or Turnstile over raw IP counting; for
velocity rules, raise per-IP thresholds inside relay ranges and
key on account/device signals instead.

## Anti-patterns

- **Hard-failing region compliance on IP geo alone** — for relay
  ranges the IP proves only the egress city Apple picked. Keep
  country-level enforcement, but back region-level gates with a
  declared-region attestation or secondary signal.
- **Blanket-blocking Private Relay ranges** — blocks a large,
  legitimate, paying-iPhone demographic; determined fraudsters
  just move elsewhere. Apple explicitly advises treating relay
  IPs like enterprise NAT, not like a hostile VPN.
- **Per-IP rate limits sized for one-user-per-IP** — on auth and
  posting routes this silently throttles whoever shares the
  egress IP. Key limits on session/user ID first, IP last.
- **Treating audit-log IPs as user identity** — one relay IP maps
  to thousands of users and rotates per session. Log the IP plus
  a relay flag, and attribute actions to accounts, not addresses.

## Gotchas

- **The egress can be Cloudflare's own IP space** — relay traffic
  to your Cloudflare-fronted zone may arrive from Cloudflare-run
  egress nodes. Never allowlist "Cloudflare IPs" as trusted
  clients; relay egress is client traffic, not proxy traffic.
- **IPv6 changes the picture** — relay prefers IPv6 when you
  publish AAAA records, and IPv6 egress geolocates more
  precisely. Enabling IPv6 on example.com improves relay geo
  accuracy for free.
- **The CSV churns** — Apple updates egress ranges frequently.
  A stale cached copy misclassifies new ranges as normal IPs.
  Refresh at least daily (cron Worker + KV).
- **Relay IP is stable per session, not per user** — session-long
  stability makes it look like a normal client; cross-session
  rotation breaks "known IP" trust and impossible-travel logic.
- **Users can lower granularity** — the "country and time zone"
  setting makes city fields even coarser, so city-level content
  targeting for these users is best-effort at most.

## Verification

- Relay ranges fetched from mask-api.icloud.com and cached with
  a daily refresh; requests tagged with an `is_relay` flag.
- Rate limits on auth/posting keyed on session/user ID, with a
  widened composite key (IP + JA4 + colo) for relay ranges.
- Region-level compliance gates degrade to secondary checks for
  relay traffic instead of hard-failing on IP geo.
- Velocity/fraud rules use relay-aware per-IP thresholds and
  account-level signals, not raw IP counts.
- Audit logs record the relay flag alongside the IP so incident
  review does not over-trust relay addresses.
- 429 rate and geo-gate bounce rate compared across iPhone
  Safari vs desktop segments after rollout — the gap closes.

## Related

- `documentation/categories/security/x-forwarded-for-client-ip-spoofing.md`
- `documentation/categories/cloudflare/waf-rate-limiting-deep-dive.md`
- `documentation/categories/compliance/age-gating.md`

## Source URLs (verified 2026-08-17)

- iCloud Private Relay: What Cloudflare Customers Need to Know —
  https://blog.cloudflare.com/icloud-private-relay/
- Prepare Your Network or Web Server for iCloud Private Relay —
  https://developer.apple.com/support/prepare-your-network-for-icloud-private-relay/
- Apple egress IP ranges feed —
  https://mask-api.icloud.com/egress-ip-ranges.csv
- Detecting iCloud Private Relay traffic (Fingerprint) —
  https://fingerprint.com/blog/icloud-private-relay-detection/
