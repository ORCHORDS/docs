# browser-integrity-hotlink-email-toggles

**Issue:** A free Cloudflare zone ships with several small Scrape Shield / edge toggles — Browser Integrity Check, Hotlink Protection, Email Obfuscation, Privacy Pass — that are easy to enable and quietly reshape responses or drop clients. Individually each looks harmless; together they explain a steady drip of odd reports: API health checks failing with challenges, images not loading in embeds, mailto links showing `[email protected]` in scraped or non-JS contexts, and users getting re-challenged. This article covers what each toggle actually does in 2025-2026, what it breaks, and how to scope or disable each one.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Browser Integrity Check (BIC)

1. **What it does.** BIC "looks for common HTTP headers abused most commonly by spammers and denies access", and it "challenges visitors without a user agent or with a non-standard user agent". It is enabled by default on zones.
2. **What it breaks.** Any client that omits `User-Agent` or sends a non-standard one — hand-rolled health checkers, some server-to-server SDKs, IoT/app HTTP stacks, misconfigured proxies — receives a challenge instead of the response. If your monitoring suddenly reports failures right after onboarding to Cloudflare, BIC is a prime suspect.
3. **Where the toggle lives.** Security > Settings, filter by "DDoS attacks", toggle Browser integrity check. It can be turned off zone-wide, but the better fix is usually scoping.
4. **Per-path scoping.** Use a configuration rule with a filter expression (hostname, URI path) to disable BIC for `/api/` or a webhook endpoint, or a custom rule with a Skip action — same pattern as the other zone-wide protections.
5. **Caching note.** Because BIC acts on the request before cache lookup for challenge-worthy clients, keep it off on endpoints where responses must never be intercepted — payment webhooks and machine-to-machine callbacks are the classic cases.

## Hotlink Protection

1. **What it does.** Hotlink Protection "denies access to requests when the HTTP referer does not include your website domain name (and is not blank)" — a Referer-header check that stops other sites from embedding your images and burning your bandwidth. It lives in Security > Settings (filter "Client-side abuse"), zone setting `hotlink_protection`.
2. **The extension list is tiny.** It only covers `gif`, `ico`, `jpg`, `jpeg`, `png`. Video, webp/avif, fonts, and other assets are not covered at all — do not rely on it as a content-protection wall.
3. **Blank Referer is allowed — both a hole and a mercy.** Direct visits, new tabs, and clients that strip or omit the Referer header (default referrer policies, some RSS readers and mobile apps) are *not* blocked. Conversely this means protection is trivially bypassed by anyone suppressing Referer; it is bandwidth hygiene, not access control.
4. **It breaks legitimate embeds.** Cloudflare warns it "will prevent the images from being displayed on sites such as Google images, Pinterest, and Facebook", and calls out RSS feeds as a scenario where you may want hotlinking to work. Expect SEO/social-preview regressions after enabling it.
5. **SaaS zones beware.** By default it only allows your zone as Referer, which blocks your customers' custom hostnames from displaying images; exempt them via configuration rules or custom rules (per-hostname application is configuration-rule territory, since the dashboard toggle is zone-wide).
6. **Bypass directories exist.** Any image under a folder named `hotlink-ok` (e.g. `/images/hotlink-ok/pic.jpg`) skips the check — a deliberate escape hatch for embeds you want to allow. The Workers example repo has a Referer-checking Worker if you need logic beyond the toggle.

## Email Obfuscation

1. **What it does.** Cloudflare rewrites visible email addresses in HTML into `[email protected]` links and injects `email-decode.min.js` (with `defer`, running before `DOMContentLoaded`) that decodes them for real visitors. It is "enabled automatically when you sign up" — check it before assuming your HTML is what you wrote.
2. **How to exclude specific addresses.** Wrap them in `<!--email_off-->address@example.com<!--/email_off-->`, deliver them via AJAX with `application/json` content type, or disable obfuscation per-endpoint/hostname with a configuration rule. (Note: it is `email_off`, not the `data-cfemail` internals, that is the supported interface.)
3. **Where it silently does nothing.** Inside `<script>`, `<noscript>`, `<textarea>`, `<xmp>`, and `<head>` tags; on responses whose MIME type is not `text/html`/`application/xhtml+xml`; when the response carries `Cache-Control: no-transform`; and on HTML "specifically added by a Worker". Pages using `<template>` tags may obfuscate unreliably.
4. **What it breaks.** Any non-JavaScript consumer of the HTML: scrapers, server-side renderers that re-process the markup, text-mode browsers, copy-from-source workflows, and mailto links in emails generated by scraping your own page. SSR frameworks that hydrate user-visible content from the initial HTML will also expose the `[email protected]` placeholder until client JS runs — verify with JS disabled.
5. **Performance history.** Older versions of the decode script were flagged for Core Web Vitals regressions; the script has since been reworked (deferred, pre-DOMContentLoaded), but if you measure INP/LCP regressions on email-heavy pages, test with the toggle off before assuming it is your app.

## Privacy Pass

1. **What it is.** Privacy Pass (IETF RFC 9576 architecture, RFC 9578 issuance — Cloudflare helped pioneer it in 2017) issues blind tokens: a client proves a claim once and "receives tokens that can be redeemed later without revealing their identity", so a provider "can verify information about a user without learning who that user is or being able to track them across requests".
2. **Why site owners care.** Privacy Pass reduces how often real humans see your challenge pages: clients holding valid tokens clear challenges without a CAPTCHA, cutting challenge friction from Browser Integrity Check, Security Level/UAM challenges, and bot challenges. It is "built into Turnstile" as a signal in challenge decisions.
3. **Apple devices get it automatically.** Apple's Private Access Tokens automatically reduce CAPTCHAs on iOS 16+ — a meaningful share of mobile visitors will rarely see an interactive challenge on your zone.
4. **No per-zone dashboard toggle to babysit.** The current developer docs describe the protocol and Turnstile integration rather than a site-owner switch; it operates at the challenge layer rather than as a zone setting you must configure. Treat it as a built-in mitigation of challenge friction, and remember its effect when counting challenge rates in your analytics.
5. **Privacy posture.** Redemption is unlinkable to issuance by design — using it does not add a tracking vector, which matters if your legal/compliance reviews challenge security features that fingerprint users.

## Related

- `free-tier-domain-security-runbook.md` — these four toggles in the context of the full free-tier security checklist (all of them are free-plan features).
- `bot-fight-mode-free-vs-super.md` — JavaScript Detections injects scripts under `/cdn-cgi/challenge-platform/` with similar CSP/no-transform caveats as the toggles above.
- `under-attack-mode-ddos-runbook.md` — challenge-heavy modes make Privacy Pass and challenge passage settings matter more.
- `turnstile-best-practices.md` — Turnstile embeds Privacy Pass tokens at the application layer.
