# Turnstile Challenge Loops in Mobile Webviews and In-App Browsers

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Mobile users tapping example project links inside Instagram, TikTok, or
Telegram hit "Verify you are human" at the age-gate/login step and
loop forever — the Turnstile widget spins, resets, and re-issues the
challenge without ever minting a token. Desktop conversion metrics
look healthy, so dashboards hide the problem: failures concentrate
in social-app in-app browsers, exactly where a large share of
example.com traffic originates (link taps in bios, stories, group
chats). Tickets say "the site is broken on my phone"; the same
account works fine minutes later on a laptop.
Native-app experiments with react-native-webview and
flutter_inappwebview error out unless configured very specifically.

## Context

example project is a Next.js static export on Cloudflare Pages with a
Worker API (133+ routes) behind Turnstile at signup/login and the
21+ age gate. Turnstile is not a native SDK — it is a JavaScript
widget that assumes a full browser environment. In-app browsers are
stripped-down webviews: they may lag the system browser engine,
inject or rewrite the User-Agent, restrict DOM storage, and
partition or drop third-party cookies. Cloudflare's official mobile
implementation guidance requires JavaScript execution, the DOM
storage API, network access to `challenges.cloudflare.com`,
`about:blank`, and `about:srcdoc`, and a User-Agent that stays
consistent for the whole session. Any of these missing produces
exactly one visible outcome for the user: an endless challenge loop.

## Why Turnstile needs a full browser environment

```
Requirement                      Why the challenge fails without it
──────────────────────────────────────────────────────────────────
JavaScript enabled               Widget is pure JS; nothing renders
DOM storage API available        Challenge state cannot persist,
                                 widget resets → loop
Access to                        Challenge iframe/scripts blocked
challenges.cloudflare.com        by origin whitelist or CSP
about:blank / about:srcdoc       Internal iframes fail to load
allowed as origins
Consistent User-Agent            "Changing the User Agent during a
for the whole session            session causes Turnstile
                                 challenges to fail" (official docs)
Accurate device clock            Minutes of clock drift break the
                                 token/cookie validation handshake
Cookies accepted for the zone    cf_clearance cannot be stored →
                                 user is re-challenged every request
```

The User-Agent rule bites twice in in-app browsers: some apps
append their own token (`Instagram`, `FBAN/FBAV`, `musical_ly`)
and some rewrite the UA differently for top-level navigation vs.
subresource fetches — from Turnstile's perspective that is a UA
change mid-session, so the challenge fails even after rendering.

## In-app browser and webview failure modes

```
Environment              Typical failure
──────────────────────────────────────────────────────────────────
Instagram / Facebook     Modified UA (FBAN/FBAV/FB_IAB tokens),
in-app browser (iAB)     partitioned cookie jar, older WKWebView
                         behavior → loop at managed challenge
TikTok in-app browser    UA contains musical_ly/Bytedance tokens;
                         aggressive JS bridge injection can trip
                         integrity signals → widget resets
Telegram in-app          Cookie jar isolated from Safari/Chrome;
browser                  cf_clearance never shared, re-challenge
                         on every visit
iOS SFSafariView /       Closest to real Safari, but ITP
WKWebView                partitions third-party storage; DOM
                         storage off by default in bare WKWebView
Android WebView          JS and DOM storage disabled by default —
(bare)                   must opt in via WebSettings
react-native-webview     Fails unless originWhitelist includes
                         about:blank/about:srcdoc and domStorage
                         is enabled
flutter_inappwebview     Works when JS + DOM storage enabled;
                         Cloudflare tests against Flutter WebView
```

Working configuration for react-native-webview per the official
mobile implementation guide:

```jsx
<WebView
  source={{ uri: 'https://example.com/age-gate' }}
  originWhitelist={[
    'https://*', 'http://*', 'about:blank', 'about:srcdoc',
  ]}
  javaScriptEnabled={true}
  domStorageEnabled={true}
  // No custom userAgent — UA changes fail the challenge.
/>
```

Android WebView equivalents: `setJavaScriptEnabled(true)` and
`setDomStorageEnabled(true)` on `WebSettings`. flutter_inappwebview
needs `javaScriptEnabled: true` and (Android) `domStorageEnabled:
true` in its settings.

## cf_clearance, pre-clearance, and cookie partitioning

```
Full browser (works)                In-app browser (loops)
────────────────────────           ────────────────────────────
solve Turnstile widget              solve widget (maybe)
  → token + cf_clearance              → cookie dropped or
    cookie stored for zone              partitioned per-app
  → WAF sees cookie,                  → WAF sees no cookie
    skips next challenge              → challenge again → loop
```

- Pre-clearance issues a `cf_clearance` cookie alongside the
  Turnstile token so later requests skip WAF challenges — but only
  when "the hostname of the Turnstile widget matches the zone with
  the WAF rules". A widget served from a different domain than the
  Worker API zone gives you tokens but no clearance.
- Default Challenge Passage validity is 30 minutes (recommended
  15–45). Every in-app browser keeps its own cookie jar, so
  clearance earned in Instagram's webview does not exist in Safari,
  Chrome, or another app's webview.
- Safari ITP and Chrome third-party cookie partitioning mean a
  widget embedded cross-site (or a page iframed inside another
  origin) may be unable to persist challenge state at all.
- Clearance levels: `interactive` clears all challenge types,
  `managed` clears managed + non-interactive, `jschallenge` only
  non-interactive. Match the WAF rules on the Worker routes.

## Hostname management for webview-hosted pages

Every widget requires at least one configured hostname, matched as
FQDN without scheme/port/path; wildcards are not supported, but a
registered hostname covers all its subdomains. For example project:

```
Widget allowed hostnames        Covers
──────────────────────────────────────────────────────────────
example.com                      example.com, www.example.com, all
                                subdomains (Pages + Worker API)
localhost                       local dev (with test keys)
```

Limits: 10 hostnames per widget (free), 200 (Enterprise). A native
app hosting the challenge page in a webview must load that page
from an allowed hostname — loading raw HTML via `loadHTMLString`
or a `file://` URL has no qualifying hostname and the widget will
refuse to run. Serve a real page (e.g.
`https://example.com/turnstile.html`) inside the webview instead.

## Mitigation: detect in-app browsers, escape to the system browser

For web traffic, the highest-leverage fix is not fighting the
webview — it is getting the user out of it before the age gate.

```javascript
// Best-effort in-app browser detection (UA tokens are not
// guaranteed stable; treat as a hint, not proof).
const UA = navigator.userAgent || '';
const IN_APP_TOKENS =
  /FBAN|FBAV|FB_IAB|Instagram|musical_ly|Bytedance|TikTok|Line\/|Twitter/i;
export const isInAppBrowser = IN_APP_TOKENS.test(UA);

export function escapeToBrowser(url) {
  if (/Android/i.test(UA)) {
    // Android: intent URL forces the default browser.
    window.location.href =
      'intent://' + url.replace(/^https?:\/\//, '') +
      '#Intent;scheme=https;action=android.intent.action.VIEW;end';
  } else {
    // iOS: no reliable programmatic escape — show a banner:
    // "tap ••• and choose Open in Browser / Open in Safari".
    document.getElementById('open-in-browser-banner').hidden = false;
  }
}
```

Render the banner *before* mounting the Turnstile widget when
`isInAppBrowser` is true; a challenge that will loop is worse UX
than one extra tap. For native example project apps, prefer a dedicated
API auth path (device attestation via Play Integrity / App Attest
plus short-lived Worker-issued session tokens) over browser
challenges in a webview; reserve the webview-hosted Turnstile page
for flows that need it, validating tokens via siteverify as usual.

## Anti-patterns

- **Trusting desktop metrics** — failures cluster in mobile
  in-app browsers. Segment Turnstile error rates by UA token or
  you silently lock out your largest acquisition channel.
- **Setting or mutating a custom User-Agent in a webview** —
  changing the UA during a session fails the challenge by design.
  Leave the platform default alone.
- **Loading the Turnstile page from file:// or inline HTML** — no
  hostname means the widget cannot match allowed hostnames and
  never solves. Host the page on a real allowed domain.
- **Enabling pre-clearance with a widget on the wrong hostname** —
  cf_clearance only helps when the widget hostname matches the
  zone carrying the WAF rules. Cross-zone widgets yield tokens
  but users still get challenged.
- **Retrying the widget in a loop on error** — re-execution in a
  broken webview burns challenges and looks bot-like. Detect the
  environment and change strategy instead.

## Gotchas

- **Cookie jars are per-app** — clearance earned in Telegram's
  webview does not carry to Safari or Chrome, so "already
  verified" users get re-challenged after switching. Expected.
- **iOS has no reliable programmatic escape** — Android intent
  URLs can force the system browser; on iOS you can only instruct
  the user via the in-app menu. Write the banner copy for that.
- **Device clock skew breaks the handshake silently** — validation
  tolerates only small skew; a phone minutes off loops silently.
- **UA-token detection decays** — apps change their UA strings;
  keep the regex list under test and treat detection as
  best-effort (some Telegram builds look like plain WebView).
- **Bare WKWebView/Android WebView disable what Turnstile needs**
  — DOM storage (Android) and other defaults are off until you opt
  in; the widget then fails the same way a bot would, which is
  misleading during triage.
- **Challenge Passage does not apply to rate limiting rules** —
  even cleared users can hit 429s if Worker rate limits are tight.

## Verification

- Turnstile error/timeout rate segmented by in-app UA tokens, with
  alerting when the in-app segment diverges from desktop.
- Age-gate flow tested inside real Instagram, TikTok, and Telegram
  in-app browsers on both iOS and Android, not just Safari/Chrome.
- Webview builds have JS + DOM storage enabled, originWhitelist
  includes about:blank and about:srcdoc, and no custom UA is set.
- Widget allowed hostnames cover every domain serving the
  challenge page, including the webview-hosted page's host.
- Pre-clearance widget hostname matches the zone with WAF rules;
  clearance level matches the challenge types in use.
- In-app detection banner renders before the widget mounts; the
  Android intent escape opens the system browser.

## Related

- `documentation/categories/cloudflare/turnstile-best-practices.md`
- `documentation/categories/testing/turnstile-test-keys-automation.md`
- `documentation/categories/mobile/webview-security.md`
- `documentation/categories/mobile/react-native-webview-patterns.md`

## Source URLs (verified 2026-08-17)

- Turnstile Mobile Implementation — https://developers.cloudflare.com/turnstile/get-started/mobile-implementation/
- Turnstile Pre-Clearance Support — https://developers.cloudflare.com/turnstile/concepts/pre-clearance-support/
- Turnstile Hostname Management — https://developers.cloudflare.com/turnstile/concepts/hostname-management/
- Challenge Passage (cf_clearance) — https://developers.cloudflare.com/cloudflare-challenges/challenge-types/challenge-pages/challenge-passage/
- Turnstile failing in mobile Webview (Cloudflare Community) — https://community.cloudflare.com/t/turnstile-is-failing-for-our-mobile-webview/644600
