# In-App Browser Detection and Escape Patterns for Social Traffic

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Most first visits to example.com arrive from links shared inside
Instagram, TikTok, and Telegram — and land in the host app's in-app
browser, not Safari or Chrome. There the funnel quietly dies: the
21+ age-gate cookie is set in an isolated per-app cookie jar and
"forgets" the user on their next visit; "Sign in with Google"
returns `403: disallowed_useragent`; Solana wallet connect finds no
`window.solana` because extension wallets cannot exist in a
webview; media downloads fail silently. Desktop dashboards look
healthy because desktop literally never sees this environment —
it is a mobile-only traffic class. Tickets say "the site is broken on my
phone"; the same user succeeds later in a real browser.

## Context

Social apps open tapped links in embedded webviews (WKWebView /
Android WebView wrappers) to keep users inside the app. These are
not real browsers: cookies and storage are partitioned per app,
there is no extension support, and host apps rewrite the User-Agent
and inject their own JavaScript — Meta apps inject `pcm.js` from
`connect.facebook.net`, and Felix Krause documented TikTok
subscribing to every keystroke and tap ("the equivalent of
installing a keylogger"). Google has blocked OAuth in all embedded
webviews since September 30, 2021 under its "Use secure browsers"
policy. For example project, whose growth loop is links shared inside these
apps, detecting the in-app browser and escaping the user to the
system browser decides mobile signup conversion.

## Why in-app browsers break flows

```
Capability            System browser    In-app browser
──────────────────────────────────────────────────────────────────
Cookies / storage     Shared, durable   Per-app jar, isolated from
                                        Safari/Chrome and from
                                        other apps; may be purged
                                        aggressively → age gate and
                                        session repeat every visit
Google OAuth          Works             Blocked: 403
                                        disallowed_useragent (all
                                        embedded webviews since
                                        2021-09-30)
Extension wallets     window.solana /   Impossible — no extension
(Phantom, etc.)       injected provider runtime; connect button is
                                        a dead end
Downloads /           Work              Fail silently (TikTok,
file pickers                            Messenger) or with a note
                                        (Instagram, WeChat); file
                                        pickers flaky
Web push              Supported (PWA)   Unavailable
User-Agent            Honest            App token appended
                                        (Instagram, FBAN, ...)
Page JavaScript       Yours only        Host app injects scripts
                                        that observe taps, text
                                        selection, form input
```

The injection point is documented, not folklore: InAppBrowser.com
shows the exact commands each host app executes against your page.

## Detection: UA markers first, feature checks second

UA sniffing is normally an anti-pattern; here it is the correct
tool: every major in-app browser deliberately announces itself
with an app token, and no feature query answers "am I inside
Instagram".

```javascript
// lib/inapp.js — every token below is app-appended, not spoofed
// by real browsers.
const UA = navigator.userAgent || '';

const IN_APP = [
  ['instagram', /Instagram/i],
  ['facebook',  /FBAN|FBAV|FB_IAB/i],   // FBAN/FBAV iOS, FB_IAB Android
  ['tiktok',    /musical_ly|Bytedance|TikTok/i],
  ['snapchat',  /Snapchat/i],
  ['line',      /\bLine\//i],
  ['twitter',   /Twitter/i],            // X in-app browser
];

export function detectInApp() {
  for (const [app, re] of IN_APP) if (re.test(UA)) return app;
  // Fallback: iOS webview without Safari's version token.
  // CAUTION: Chrome/Firefox on iOS are WebKit too — exclude them
  // or you will flag real, capable browsers (CriOS/FxiOS).
  const iosWebview = /iPhone|iPad/.test(UA)
    && /AppleWebKit/.test(UA)
    && !/Safari\//.test(UA)
    && !/CriOS|FxiOS|EdgiOS/.test(UA);
  return iosWebview ? 'unknown-ios-webview' : null;
}
```

Telegram is the notable gap: its in-app browser often presents a
near-stock WebView UA with no `Telegram` token. Treat
"unknown-ios-webview" plus link-level UTM context
(`?utm_source=telegram`) as the Telegram signal.

## Escape patterns per platform

```
Platform  Technique                     Reality check
──────────────────────────────────────────────────────────────────
Android   intent://example.com/x        Most reliable escape; opens
          #Intent;scheme=https;end      the default browser. Works
                                        in Telegram; TikTok is
                                        inconsistent ("not
                                        dependable" per
                                        inapp-debugger tests)
iOS       x-safari-https://example.com  Works in some hosts
                                        (Telegram, Line); fails in
                                        others (X, TikTok). No
                                        Apple-approved escape API
iOS       googlechromes://example.com   Chrome-specific variant;
                                        only if user has Chrome
Any       Interstitial banner +        Always works; the fallback
          copy-link button              when programmatic escape
                                        is blocked
Telegram  "Open in ..." item in the    Menu wording differs per
          ••• menu (iOS: Open in       host app — Instagram: "Open
          Safari)                       in external browser"
```

```javascript
export function escapeToSystemBrowser(url) {
  const clean = url.replace(/^https?:\/\//, '');
  if (/Android/i.test(navigator.userAgent)) {
    window.location.href =
      `intent://${clean}#Intent;scheme=https;` +
      `action=android.intent.action.VIEW;end`;
    return 'attempted';
  }
  // iOS: try the Safari scheme; it either works or is silently
  // ignored, so always render the manual banner as well.
  window.location.href = `x-safari-https://${clean}`;
  return 'banner-required';
}
```

Interstitial rules for example project: render the banner *before* the age
gate, wallet connect, or OAuth buttons — a flow that will fail is
worse than one extra tap. The banner needs per-app instructions
("Tap ••• then Open in external browser"), a copy-link button
(`navigator.clipboard.writeText`) for hosts that block the menu,
and a signed token in the link so age-gate/session state survives
the switch — cookies will not follow the user out of the webview.

## Measuring the segment and flagging it at the edge

Client detection can fail; classify at the edge too so analytics
and the API both know the environment.

```javascript
// Worker: tag every request with the in-app classification.
const IN_APP_RE =
  /Instagram|FBAN|FBAV|FB_IAB|musical_ly|Bytedance|Snapchat|\bLine\//i;

export default {
  async fetch(req, env, ctx) {
    const ua = req.headers.get('user-agent') || '';
    const m = ua.match(IN_APP_RE);
    const res = await handle(req, env);
    ctx.waitUntil(env.ANALYTICS.writeDataPoint({
      blobs: [m ? m[0] : 'browser', new URL(req.url).pathname],
      doubles: [res.status],
      indexes: [m ? 'inapp' : 'browser'],
    }));
    return res;
  },
};
```

Track two numbers per host app: share of first visits (for example project
this is most mobile first-touches, since the growth loop *is*
Instagram/TikTok/Telegram shares) and signup
conversion delta vs. system browsers. The delta is the business
case for escape-UX work, and it flags host-app changes: a UA token
change shows as an "unknown" spike, an injection change as a
conversion cliff.

## Anti-patterns

- **Treating UA sniffing as forbidden and shipping feature
  detection only** — there is no feature that identifies the host
  app, and the failures (OAuth, wallets) cannot be feature-tested
  before the user hits them. UA tokens are the designed signal.
- **Starting OAuth anyway and handling the 403** — Google rejects
  the request at its own page; you never get a callback to handle.
  Detect first and gate the button.
- **Relying on cookies across the escape** — the system browser
  has a different jar; carry state in the URL (signed, short-lived
  token) or the user restarts the age gate and rage-quits.
- **Generic "iOS webview" heuristics without excluding CriOS /
  FxiOS** — Chrome and Firefox on iOS are WebKit webviews by
  platform rule; flagging them tells real-browser users to "open
  in a browser" they are already in.
- **Blocking the page entirely for in-app users** — browsing and
  reading work fine in-app; only gate the flows that actually
  break (auth, wallet, downloads). Interstitials on every page
  view burn the growth loop you are trying to feed.

## Gotchas

- **Escape support is per-host-app and changes without notice** —
  `x-safari-https://` works in Telegram and Line but not X or
  TikTok; Android `intent://` is undependable in TikTok. Keep a
  device-tested matrix, and always ship the manual banner.
- **Telegram hides in plain sight** — no UA token in many builds;
  it looks like a stock WebView. Use link-level UTM tagging to
  attribute it.
- **Wallet connect has a different escape** — extension wallets
  are impossible in any mobile browser context; the fix for
  Solana is a Phantom/Solflare deep link (wallet-adapter mobile
  flow), not "open in Safari". Escaping to Safari alone still
  leaves `window.solana` undefined.
- **Host-app injection can interact with your page** — Meta's
  `pcm.js` and TikTok's listeners observe taps and input. Krause's
  defensive trick (pre-defining `#iab-pcm-sdk` spans) is fragile;
  the durable fix is moving sensitive input out of the webview.
- **Downloads fail with no error** — TikTok and Messenger drop
  file downloads silently; route media-export features through the
  escape banner instead of a broken save button.

## Verification

- Detection module returns the correct app for real Instagram,
  TikTok, Facebook, Snapchat, Line, and X in-app browsers on both
  iOS and Android devices (not just simulated UAs).
- Chrome iOS and Firefox iOS are NOT flagged as in-app.
- Android `intent://` escape opens the default browser from
  Instagram and Telegram; iOS banner renders when the
  `x-safari-https://` attempt is ignored.
- Age-gate/session state survives the escape via signed URL token.
- OAuth and wallet-connect buttons are gated behind the escape
  interstitial when in-app is detected.
- Edge Worker tags requests; dashboard shows per-app traffic share
  and signup conversion vs. system browsers, with an alert on
  "unknown webview" spikes (UA token drift).

## Related

- `documentation/docs/policies/cloudflare/turnstile-webview-in-app-browser-challenge-loops.md`
- `documentation/docs/policies/mobile/webview-security.md`
- `documentation/docs/policies/mobile/deep-linking-universal-app-links.md`
- `documentation/docs/policies/mobile/mobile-auth-oauth-pkce.md`

## Source URLs (verified 2026-08-17)

- Google OAuth blocked in embedded webviews — https://developers.googleblog.com/upcoming-security-changes-to-googles-oauth-20-authorization-endpoint-in-embedded-webviews/
- Auth0: Google blocks OAuth from embedded browsers — https://auth0.com/blog/google-blocks-oauth-requests-from-embedded-browsers/
- Krause: Instagram/Facebook in-app browser injection — https://krausefx.com/blog/ios-privacy-instagram-and-facebook-can-track-anything-you-do-on-any-website-in-their-in-app-browser
- Krause: InAppBrowser.com injection detector — https://krausefx.com/blog/announcing-inappbrowsercom-see-what-javascript-commands-get-executed-in-an-in-app-browser
- inapp-debugger: per-app escape/download test matrix — https://github.com/shalanah/inapp-debugger
