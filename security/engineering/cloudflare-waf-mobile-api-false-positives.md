# cloudflare-waf-mobile-api-false-positives

**Issue:** Cloudflare WAF custom rules blocking legitimate mobile
API traffic due to JA4 fingerprint mismatches and overly broad
User-Agent expressions
**Date:** 2026-08-22
**Author:** example.com
**Status:** documented — example project project (mobile API, Workers)

## Symptom

Mobile clients (iOS 17 / Android 14) receive `403 Forbidden`
from the Cloudflare WAF on `/api/*` endpoints. Browser clients
on the same network hit the same endpoints without error. Ray IDs
in the response confirm a managed ruleset or custom rule fired,
not an origin 403.

```
HTTP/2 403
cf-ray: 8f1a2b3c4d5e6f70-LHR
content-type: text/plain; charset=UTF-8

error code: 1020
```

## Context

example project deploys a Next.js static export on Cloudflare Pages with
a Worker handling all `/api/*` traffic. WAF rules evaluate before
the Worker receives the request. Mobile SDK HTTP clients present
TLS fingerprints (JA4) and User-Agent strings that differ from
browsers, triggering bot-management and custom WAF expressions
that were written with desktop browsers in mind.

## JA4 fingerprint differences on mobile

JA4 hashes the TLS ClientHello — cipher suites, extensions,
ALPN — into a sortable fingerprint. Mobile HTTP stacks diverge
from desktop browsers:

| Client                  | JA4 prefix  | Notable difference            |
|-------------------------|-------------|-------------------------------|
| Chrome 124 (desktop)    | t13d1516h2  | GREASE extensions, TLS 1.3   |
| iOS URLSession 17.4     | t13d1414h2  | Fewer GREASE, ALPN h2,h3     |
| OkHttp 4.12 (Android)   | t13d1312h2  | No GREASE, TLS 1.2 fallback  |
| Expo/RN fetch (iOS)     | t13d1414h2  | Mirrors URLSession            |
| Expo/RN fetch (Android) | t13d1312h2  | Mirrors OkHttp                |

Bot management rules that allowlist only browser JA4 families
silently block all mobile clients. Never use JA4 as the sole
filter; always combine with additional signal.

## User-Agent matching pitfalls

Expo and React Native apps often ship no meaningful User-Agent
or a generic one like `okhttp/4.12.0`. WAF expressions such as:

```
# BAD — blocks all non-browser UA on mobile endpoints
(not http.user_agent matches "Mozilla")
```

will catch every mobile SDK client. The correct approach is an
explicit allowlist combined with a rate limiter, not a blocklist
of unknown UAs:

```
# BETTER — skip WAF for requests with a valid app UA or
# a known CF-Access service token header
(
  http.user_agent matches "^example project-Mobile/[0-9]"
  or
  http.request.headers["cf-access-client-id"] ne ""
)
```

Set the User-Agent in the mobile SDK at app startup:

```ts
// React Native / Expo — set before any fetch
const APP_UA = `example project-Mobile/${APP_VERSION} (${Platform.OS})`;
```

## Managed ruleset tuning for mobile endpoints

The Cloudflare-managed OWASP and Bot Management rulesets assign
sensitivity scores. Mobile endpoints serving anonymous social
content need a more permissive profile than a login endpoint.

```
# Cloudflare Dashboard > Security > WAF > Managed rules
# Create a skip rule with higher priority than managed rules:

Rule name: Skip managed rules for mobile API paths
Expression:
  http.request.uri.path matches "^/api/v[0-9]+/(feed|posts|media)"
  and
  http.user_agent matches "^example project-Mobile/"

Action: Skip > Managed rules (select specific rulesets)
Priority: 1   ← must be lower number than managed rule priority
```

For the login and age-verification endpoints, keep full WAF
coverage. Only skip on read-heavy anonymous feed paths.

## WAF logging and triage workflow

1. Enable Security Event logs in the Cloudflare dashboard.
2. Filter by `action:block` and `rayId` to find the firing rule.
3. Check `matchedData` — it shows which expression matched.
4. Use the Cloudflare Trace tool to replay a blocked request:

```bash
# Cloudflare Workers Trace (wrangler)
wrangler dev --inspect
# or via API:
curl -X POST \
  "https://api.cloudflare.com/client/v4/zones/${ZONE}/security-events" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -d '{"filters": {"action": "block"}, "limit": 100}'
```

5. Add the firing rule ID to a skip expression scoped to the
   mobile path. Re-test from a real device before deploying.

## ASCII decision tree — false positive triage

```
Request blocked (1020)?
├── Ray ID found in Security Events?
│   ├── YES → matchedData shows rule ID
│   │         → Is rule a managed ruleset rule?
│   │             YES → Add skip rule for path + UA
│   │             NO  → Edit custom rule expression
│   └── NO  → Block is from origin Worker (check Worker logs)
└── No Ray ID → Origin returned 403, not Cloudflare WAF
```

## Anti-patterns

- Writing `not http.user_agent contains "Mozilla"` to block bots
  — this catches every mobile SDK client.
- Enabling Bot Fight Mode on API subdomains without excluding
  mobile UA patterns; BFM issues JS challenges that native apps
  cannot solve.
- Using JA4 as the primary allow/block signal without combining
  it with path scope — JA4 changes across OS upgrades silently.
- Disabling WAF entirely on `/api/*` as a quick fix — removes
  protection from injection and credential stuffing attacks.
- Trusting the User-Agent header alone for identity; it is
  trivially spoofed. Pair with CF-Access token or mTLS.

## Gotchas

- Cloudflare's Bot Fight Mode and Super Bot Fight Mode issue
  browser challenges (JS or CAPTCHA) that native mobile apps
  cannot complete. Disable SBFM for API zones or use CF Access
  service tokens to authenticate the mobile app instead.
- JA4 fingerprints for iOS change with each major OS release.
  Pin your allow rules to JA4 prefix patterns, not exact hashes,
  or plan to update rules every iOS major release.
- WAF skip rules need `priority` lower than the managed ruleset
  priority. In Cloudflare's model, lower numeric priority = runs
  first. A skip rule at priority 100 fires before managed rules
  at priority 900.
- Expo Go (development client) presents a different UA than the
  production app binary. Test WAF rules against production builds,
  not Expo Go.

## Verification

- `curl -A "example project-Mobile/1.0 (ios)" https://api.example project.app/feed`
  → 200, no `cf-ray` block header
- `curl -A "curl/7.88" https://api.example project.app/feed`
  → 403 from custom WAF rule (confirms rule still active for
  unknown clients)
- Check Security Events dashboard — zero blocks with
  `example project-Mobile` UA after skip rule is deployed
- Load test from iOS Simulator and Android Emulator; confirm
  no intermittent 403s over 1000 requests

## Related

- `security/cloudflare-zero-trust-mtls-service-auth.md`
- `security/rate-limiting-strategies.md`
- `cloudflare/workers-request-lifecycle.md`
- `mobile/react-native-http-client-config.md`
- `security/credential-stuffing-account-takeover-defense.md`

## Sources

- https://developers.cloudflare.com/waf/custom-rules/
- https://developers.cloudflare.com/bots/concepts/ja4-signals/
- https://developers.cloudflare.com/waf/managed-rules/
- https://github.com/FoxIO-LLC/ja4 (JA4 specification)
- https://developers.cloudflare.com/waf/tools/cloudflare-trace/
