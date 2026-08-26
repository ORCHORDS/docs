# Zone-Level Challenges: Uneven Mobile vs Desktop Pass Rates

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

During a scraping incident against example.com, someone flipped
Under Attack mode on. Desktop Chrome users saw a five-second
interstitial and carried on; nobody complained. Mobile signups
cratered: older Android browsers, Brave/Firefox Focus, and social
in-app browsers got stuck on "Checking your browser" or looped.
NOWPayments IPN webhooks and Solana RPC callbacks started getting
403 challenge HTML instead of reaching the Worker API — payments
silently stopped confirming.
Support tickets said "site won't load on my phone" while every
desktop dashboard looked green. This entry covers zone-level
challenge pages (WAF challenge actions and Under Attack mode) —
Turnstile widget loops in webviews are a separate entry.

## Context

example project is a Next.js static export on Cloudflare Pages with a
Worker API (133+ routes) on the same zone. A large share of traffic
is mobile, arriving through social in-app browsers. Zone-level
challenges are interstitial pages Cloudflare serves before the
origin: Managed Challenge (Cloudflare dynamically picks the
challenge type), Non-Interactive/JS Challenge, Interactive
Challenge, and Under Attack mode (a browser challenge for every
visitor). All require JavaScript execution and a stored
`cf_clearance` cookie, and all fail for non-HTML requests
(XHR/fetch) — SPAs, APIs, webhooks, and native apps cannot pass
them by design. Pass rates are therefore uneven: environments
common on mobile fail far more often than current desktop Chrome,
so a challenge rule that looks harmless in aggregate can quietly
gate your biggest acquisition channel.

## How Managed Challenge picks a challenge type

```
Request arrives, matches a rule with action = Managed Challenge
        │
        ▼
Cloudflare scores the request (heuristics, JS detections,
ML signals from the browser)
        │
        ├─ low suspicion  → silent/non-interactive checks,
        │                   auto-pass, page shows "Success"
        ├─ medium         → non-interactive challenge
        │                   (JS runs, no user action)
        └─ high suspicion → interactive challenge
                            (user must click/interact)
```

Managed Challenge is Cloudflare's recommended action for most WAF
rules: it serves the least intrusive verification the request's
signals allow. The catch for mobile: the signals that escalate a
request toward the interactive end — unusual UA, missing storage,
privacy features suppressing fingerprint surface — are exactly
what stripped-down mobile environments emit. Mobile users are both
likelier to get the harder variant and less able to complete it.

## Environments where challenges fail disproportionately

```
Environment                  Why the challenge fails
──────────────────────────────────────────────────────────────────
Older mobile browsers        Support window is current + two
                             previous major versions (Chrome,
                             Safari, Firefox, Edge, Samsung
                             Internet); 5+ year-old browsers
                             are explicitly unsupported
Privacy browsers /           Script blockers, fingerprinting and
extensions (Brave shields,   canvas protection interfere with
uBlock, Focus)               challenge verification; ad blockers
                             can stop challenge scripts loading
Social in-app webviews       Modified UA, partitioned or dropped
(Instagram, TikTok,          cookies → cf_clearance never sticks,
Telegram)                    re-challenge on every request
JS or cookies restricted     Pure-JS challenge never renders, or
                             solves but clearance cannot persist
                             → interstitial forever / loop
iOS Lockdown Mode            Blocks "complex web technologies";
                             community reports devices in
                             Lockdown cannot pass challenges
Native apps, API clients,    Cannot execute JS or render HTML;
webhooks (NOWPayments IPN,   get 403 + challenge HTML, fail
Solana RPC callbacks), curl  outright — every time
Headless browsers /          Challenges are designed to detect
automation (Puppeteer etc.)  and block these (intended)
```

## cf_clearance lifetime and partitioning on mobile

Passing any zone-level challenge sets a `cf_clearance` cookie.
Challenge Passage controls its validity — default 30 minutes —
after which the user is re-challenged. Validation tolerates a few
minutes of clock skew, and XHR requests get an extra hour so an
open SPA does not die mid-session. The cookie is set
`SameSite=None; Secure; Partitioned`:

- `SameSite=None` lets the cookie ride on cross-site requests so
  navigation between hostnames on the zone is not re-challenged.
  It requires HTTPS (`Secure`).
- `Partitioned` (CHIPS) keys the cookie to the top-level context:
  clearance earned browsing example.com directly does not exist
  where example.com is embedded under another top-level site — the
  embedded context must solve its own challenge, and a webview
  that cannot persist partitioned cookies never will.
- Each in-app browser keeps its own cookie jar, so clearance is
  also per-app: solved in Telegram's webview means nothing in
  Safari. Short Challenge Passage plus per-app jars multiplies
  challenge frequency for the users least able to solve them.

## Monitoring: challenge solve rate (CSR) by platform

```
CSR = challenges solved / challenges issued  (per rule)

Where: zone → Security → Security rules (or WAF → Custom rules /
Rate limiting rules) shows per-rule CSR. Security Events /
Security Analytics show challenge Issued vs Solved actions and
support filtering by user agent, path, country, etc.

Interpreting CSR:
  High CSR  → mostly humans solving → rule matches too much
              legitimate traffic (false positives) → narrow it
  Low CSR   → mostly bots abandoning at the challenge script →
              rule is doing its job

There is NO dedicated "failed challenge" metric — failure is the
gap between issued and solved.
```

The aggregate number hides the mobile story. Segment before
trusting it: filter Security Events by user agent substrings
(`Instagram`, `FBAN`, `musical_ly`, `Android`, `iPhone`) and
compare issued-vs-solved per segment. For example project, desktop Chrome
near 100% averaged against an in-app-browser CSR near zero into a
"fine-looking" blended number while mobile users were locked out.
Export events via Logpush/GraphQL for dashboards and alerting.

## Choosing rule actions and scoping challenges

```
Action              Use when                     Mobile/API impact
──────────────────────────────────────────────────────────────────
Managed Challenge   Default for suspect          Best pass rate of
                    *browser* traffic            the challenges;
                                                 0% non-browsers
JS Challenge        Legacy; no reason to         Slightly worse
(non-interactive)   prefer it now                than managed
Interactive         Almost never — Cloudflare    Worst mobile pass
Challenge           discourages it               rate
Block               Traffic you are sure is      Clean 403; APIs
                    bad, and ALL API/native      get an honest
                    routes                       error, not HTML
Skip                Known-good paths and         Exempts from
                    verified sources             challenges
```

Never put a challenge action on routes a non-browser calls. For
the example project zone that means the Worker API's webhook and native
paths get an explicit skip rule ordered before everything else:

```
# WAF custom rule 1 — action: Skip
# (skip remaining custom rules + Security Level, i.e. Under
#  Attack mode challenges; log matches)
(http.request.uri.path wildcard "/api/webhooks/*")
or (http.request.uri.path eq "/api/payments/nowpayments-ipn")
or (http.request.uri.path wildcard "/api/rpc/solana/*")

# WAF custom rule 2 — action: Managed Challenge
# challenge only browser-facing HTML routes, scoped away from API
(not starts_with(http.request.uri.path, "/api/"))
and (cf.threat_score gt 20)
```

Authenticate the skipped webhook paths in the Worker instead
(HMAC signature for NOWPayments IPN, allowlisted source for RPC
callbacks) — a skip rule trades edge protection for application-
level verification, so the application must actually verify.

Under Attack mode is a zone-wide switch that challenges every
visitor and requires JavaScript — every non-browser client fails,
and marginal mobile browsers fail with it. Treat it as a
last-resort, temporary lever: pre-stage the skip rule above
(Security Level is a skippable component), or use Configuration
Rules to raise Security Level to "Under Attack" only on the HTML
paths under active attack rather than the whole zone.

## Anti-patterns

- **Enabling Under Attack mode zone-wide with no API exemptions
  staged** — payment webhooks and native clients break instantly
  and silently; webhook senders get a 4xx they may not retry.
- **Challenging API routes "for extra safety"** — non-browser
  clients have a 0% solve rate; use Block, rate limiting, or
  token auth on `/api/*` and reserve challenges for HTML.
- **Reading blended CSR as health** — a high-desktop, zero-mobile
  split averages into a plausible number; segment by UA first.
- **Using Interactive or JS Challenge out of habit** — Managed
  Challenge auto-passes most humans and is Cloudflare's
  recommendation; older actions only lower mobile pass rates.
- **Shortening Challenge Passage to "fix" mobile complaints** —
  shorter clearance means *more* challenges for cookie-partitioned
  mobile contexts, the opposite of the intended fix.

## Gotchas

- **Challenge pages cannot be solved from XHR/fetch** — an SPA
  whose API call gets challenged receives challenge HTML in a
  JSON code path; the user sees a broken app, not a challenge.
- **cf_clearance is Partitioned** — clearance does not transfer
  between top-level contexts or app cookie jars; "I already
  verified" reports from users switching apps are expected
  behavior, not a bug.
- **Managed Challenge escalates on weak browser signals** — the
  same rule yields silent passes on desktop Chrome and interactive
  challenges on privacy/mobile browsers, so QA on desktop proves
  nothing about the mobile experience.
- **iOS Lockdown Mode users cannot pass** — a small but real
  cohort (journalists, activists — relevant to an anonymous
  platform) is hard-blocked by any challenge; give them a
  challenge-free path or accept the loss consciously.
- **Skip rule ordering matters** — WAF custom rules evaluate in
  order; a skip rule placed below the challenge rule skips
  nothing.

## Verification

- No challenge action (or Under Attack security level) applies to
  `/api/*`, webhook, or RPC callback paths — verified with curl
  expecting JSON, not challenge HTML.
- Skip rule for NOWPayments IPN and Solana callbacks is ordered
  first and the Worker verifies HMAC/source on those paths.
- CSR reviewed per rule AND segmented by user agent (in-app
  tokens, Android/iPhone vs desktop) in Security Events, with
  alerting on issued-vs-solved divergence for mobile segments.
- Under Attack runbook stages path-scoped Configuration Rules
  instead of the zone-wide toggle.
- Mobile QA pass includes an older Android browser, Brave with
  shields up, and at least one social in-app browser.

## Related

- `documentation/docs/policies/cloudflare/turnstile-webview-in-app-browser-challenge-loops.md`
- `documentation/docs/policies/cloudflare/under-attack-mode-ddos-runbook.md`
- `documentation/docs/policies/cloudflare/waf-rate-limiting-deep-dive.md`
- `documentation/docs/policies/cloudflare/bot-fingerprinting-native-app-traffic-false-positives.md`

## Source URLs (verified 2026-08-17)

- Interstitial Challenge Pages — https://developers.cloudflare.com/cloudflare-challenges/challenge-types/challenge-pages/
- Challenge Passage (cf_clearance) — https://developers.cloudflare.com/cloudflare-challenges/challenge-types/challenge-pages/challenge-passage/
- Challenge Solve Rate (CSR) — https://developers.cloudflare.com/cloudflare-challenges/reference/challenge-solve-rate/
- Supported Browsers for Challenges — https://developers.cloudflare.com/cloudflare-challenges/reference/supported-browsers/
- Under Attack Mode — https://developers.cloudflare.com/fundamentals/reference/under-attack-mode/
