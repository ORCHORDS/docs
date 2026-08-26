# Bot Scoring and TLS Fingerprinting: Native App False Positives

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Desktop web traffic to example.com sails through Cloudflare, but the
future example project native apps hit 403s or challenge HTML on plain API
calls. Bot analytics show mobile-app requests clustered at bot
scores of 1-29 ("likely automated") while Chrome-on-desktop sits at
90+. After an iOS update, a previously "known good" fingerprint
disappears and a new one appears — and a zone-wide rule that blocks
low scores silently drops every updated device. Solana wallet
callbacks and NOWPayments IPN webhooks (server-to-server, no
browser) get served a challenge page they can never solve, so
payments stall with no visible error on our side.

## Context

Cloudflare Bot Management scores every request 1-99: a score of 1
means "quite certain the request was automated", 2-29 is likely
automated, 30-99 is likely human. Scores come from heuristics
(typically 1 or 29), a machine-learning engine trained on billions
of requests, and JavaScript detections injected into HTML pages.
TLS fingerprints (JA3/JA4, Enterprise Bot Management fields
`cf.bot_management.ja3_hash` and `cf.bot_management.ja4`) identify
the client's TLS stack independently of IP or User-Agent. The
catch: every one of these signals is calibrated around browsers.
A native app's HTTP stack (okhttp, URLSession/CFNetwork, Dart,
React Native) is not a browser, cannot run JS detections, and
produces a non-browser TLS fingerprint — so legitimate app traffic
looks exactly like a bot. The example project Worker API (133+ routes)
serves web today and native clients later; any zone-wide bot rule
we write now must not become a silent app-killer then.

## JA3 vs JA4

```
                JA3                     JA4
──────────────────────────────────────────────────────────────
Output          MD5 hash (opaque)       Readable, sortable:
                                        t13d1516h2_8daaf6152771_
                                        b0da82dd1658
Input order     Ciphers + extensions    Ciphers, extensions,
                hashed IN WIRE ORDER    sig algorithms SORTED
                                        before hashing
Chrome ~110+    Randomized extension    Sorting absorbs the
(early 2023)    order => new JA3 hash   shuffle => stable
                per connection          fingerprint
Components      One blob                protocol, TLS version,
                                        SNI presence, cipher
                                        count, extension count,
                                        ALPN + 2 truncated
                                        SHA256 hashes
ALPN            Not included            Included (h2/h3 visible)
```

JA3 relied on the exact ClientHello ordering, so Chrome's
extension permutation made real browsers emit thousands of
distinct JA3 hashes — allowlists built on JA3 rotted overnight.
JA4 sorts before hashing, which removes randomization churn but
NOT churn from genuine stack changes (new TLS features, dropped
ciphers). Prefer `cf.bot_management.ja4` in new rules.

## Fingerprints churn with OS and browser updates

Cloudflare's own writeup describes customers who saw a new JA3
fingerprint, blocked it, and then discovered it was a new browser
release — or an OS update that changed the fingerprint of their
users' mobile devices. Mobile is hit hardest:

```
Event                          Fingerprint effect
──────────────────────────────────────────────────────────────
iOS major/minor update         New CFNetwork/BoringSSL build
                               => new JA3/JA4 for URLSession
Android WebView / Play         okhttp + Conscrypt updates roll
  services update              out silently => fingerprint moves
New Chrome/Safari release      New browser fingerprint appears
                               in traffic within days
App dependency bump            okhttp 4.x -> 5.x changes cipher
                               ordering => new fingerprint
```

Consequence: a static allowlist of "our app's fingerprint" is a
time bomb. Every fingerprint rule needs an expiry mindset and a
monitoring step (see Verification) before and after each app or
OS release.

## Native app HTTP stacks score like bots

```
Client                    TLS stack           Typical outcome
──────────────────────────────────────────────────────────────
Chrome/Firefox desktop    Browser TLS         Score 30-99, passes
iOS app (URLSession)      CFNetwork/BoringSSL Non-browser JA4,
Android app (okhttp)      Conscrypt           low ML score,
React Native (fetch)      okhttp / iOS native no JS detection
Flutter (dart:io)         Dart TLS            signal => 1-29
NOWPayments IPN callback  Server-side lib     Score ~1
Solana wallet backend     Server-side lib     Score ~1
```

The ML engine learned that "human" traffic looks like browsers;
JavaScript detections only run where HTML+JS executes. A native
app fails both, so its floor score is structurally low — this is
not misbehavior by the app, it is the model working as designed
on the wrong population.

## Challenges cannot run in a native-app API context

Challenge Pages interrupt the request by returning a full HTML
page for a browser to render and solve. Cloudflare's docs are
explicit that this fails whenever the client expects a non-HTML
response (fetch/XHR — and by extension any native HTTP client).
Turnstile needs a browser environment; on native mobile the only
supported pattern is rendering it inside a WebView and passing
the token out. The clearance flow also depends on the
`cf_clearance` cookie, which native stacks do not persist the way
browsers do. So the mobile-app API is the most common
false-positive landing zone: low score + challenge action =
unsolvable challenge = user-visible outage that looks like a
generic network error in the app.

## Mitigation: layered rules instead of zone-wide blocking

```
# 1. Dedicated API hostname: api.example.com
#    Configuration Rules / WAF skip: disable Managed Challenge,
#    Browser Integrity Check, and JS detections on this host.
#    Protection comes from auth, not challenges.

# 2. WAF custom rule — allow verified app traffic by JA4 + signal
(http.host eq "api.example.com"
 and cf.bot_management.ja4 in {"t13d1516h2_8daaf6152771_b0da82dd1658"}
 and http.request.headers["x-example project-client"][0] eq "ios")
Action: Skip (bot fight / super bot fight mode)

# 3. Webhook routes — never challenge, verify HMAC in the Worker
(http.request.uri.path eq "/api/payments/nowpayments/ipn")
Action: Skip challenges; Worker verifies IPN HMAC signature

# 4. Strongest option: API Shield mTLS for the native apps
#    Ship a client cert with the app (Cloudflare-managed CA is
#    available on all plans), then enforce:
(http.host eq "api.example.com"
 and not cf.tls_client_auth.cert_verified)
Action: Block
```

Order matters: allow/skip rules for app fingerprints and webhook
paths must evaluate before any low-score block rule. Combine
signals — JA4 alone is spoofable by attack tooling that replays
your app's fingerprint, so pair it with auth (session token, HMAC,
or mTLS) rather than treating the fingerprint as identity.

## Inter-request signals (JA4 Signals, JA4H)

JA4 alone is one connection's snapshot. Cloudflare's JA4 Signals
aggregate behavior per fingerprint across the whole network
(15M+ unique JA4 fingerprints, 500M+ user agents, hourly):

```
Signal                Meaning
──────────────────────────────────────────────────────────────
browser_ratio_1h      Share of requests from this JA4 that look
                      browser-like network-wide
cache_ratio_1h        Share hitting cacheable content
h2h3_ratio_1h         HTTP/2 + HTTP/3 usage share
reqs_quantile_1h      Volume rank vs all fingerprints
```

A legitimate app fingerprint has a LOW browser_ratio (expected —
it is not a browser) but stable volume and normal cache behavior;
scraper fingerprints spike in reqs_quantile with skewed ratios.
JA4H (the HTTP-header fingerprint in the JA4+ suite) adds a
second, independent axis: header order/casing identifies the HTTP
library even when the TLS layer is mimicked. Use these to
separate "non-browser but ours" from "non-browser and hostile"
instead of treating all non-browser traffic as one bucket.

## Anti-patterns

- **Zone-wide "challenge if score < 30"** — structurally 403s
  every native app and webhook while desktop browsers pass.
  Scope score rules to browser-facing hostnames only.
- **Blocking a new unknown fingerprint on sight** — the
  documented failure mode: it is usually a browser release or an
  OS update, and on mobile that means blocking real users.
- **Allowlisting one static JA3 hash for "the app"** — JA3
  churns with Chrome randomization and every stack update. Use
  JA4, expect rotation, and never let the allowlist be the only
  path (fingerprint + auth, not fingerprint = auth).
- **Serving web and app/webhook traffic from one hostname with
  one bot policy** — you cannot tune challenge behavior per
  client class. Split `api.` from the web origin.
- **Treating a challenge as protection for webhooks** — the
  NOWPayments IPN sender will never solve it; you just drop
  payment notifications silently. HMAC verification in the
  Worker is the real control.

## Gotchas

- **JA3/JA4 fields are Enterprise Bot Management only** — on
  lower plans you cannot write fingerprint rules; you only get
  the blunt Bot Fight Mode toggles, which is exactly why they are
  dangerous for app traffic.
- **TLS session resumption skips recalculation** — a resumed
  session keeps its original fingerprint; per-request fingerprint
  fields can be absent or stale. Fingerprints are also missing on
  plain HTTP and Worker subrequests.
- **A score of 1 vs 29 encodes the engine** — heuristic matches
  typically pin 1; ML fills the 2-99 range. An app stuck at
  exactly 1 usually means a heuristic/fingerprint match, not ML.
- **Turnstile in a WebView is a UX cliff** — it works, but it
  injects a browser moment into a native flow; for a 21+
  anonymous platform, extra friction at login is churn. Prefer
  mTLS or token auth on the API hostname.
- **`cf_clearance` is cookie-bound** — CORS preflights and
  cookie-less native stacks do not carry it, so a cleared web
  session does not clear the app's API calls.

## Verification

- Bot score distribution reviewed in analytics segmented by
  platform (desktop web / mobile web / app UA / webhook paths)
  BEFORE any enforcement rule ships — log-only first.
- `api.example.com` split from the web hostname; challenges and
  JS detections disabled there; auth enforced in the Worker.
- Webhook paths (NOWPayments IPN, wallet callbacks) covered by
  skip rules and HMAC signature verification, not challenges.
- App allow rules use `cf.bot_management.ja4` combined with an
  auth signal, and evaluate before any low-score block rule.
- Fingerprint watchlist re-checked after every app release and
  major iOS/Android update; alerts on new dominant JA4 values.
- mTLS (API Shield) evaluated for native clients; rules gate on
  `cf.tls_client_auth.cert_verified`.

## Related

- `documentation/categories/cloudflare/bot-fight-mode-free-vs-super.md`
- `documentation/categories/cloudflare/bot-management-enterprise.md`
- `documentation/categories/cloudflare/waf-rate-limiting-deep-dive.md`
- `documentation/categories/security/webhook-signature-verification-hmac.md`

## Source URLs (verified 2026-08-17)

- Advancing Threat Intelligence: JA4 fingerprints and inter-request
  signals — https://blog.cloudflare.com/ja4-signals/
- JA3/JA4 fingerprints (Bot Management) —
  https://developers.cloudflare.com/bots/additional-configurations/ja3-ja4-fingerprint/
- Bot scores — https://developers.cloudflare.com/bots/concepts/bot-score/
- Challenge pages —
  https://developers.cloudflare.com/cloudflare-challenges/challenge-types/challenge-pages/
- API Shield Mutual TLS —
  https://developers.cloudflare.com/api-shield/security/mtls/
