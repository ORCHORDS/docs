# Cloudflare Zaraz: Third-Party Tags at the Edge as a Mobile CPU Win

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

You add a single analytics tool or marketing pixel the classic way
(script tag or GTM container) and mobile INP degrades while desktop
barely moves. Lighthouse mobile runs show TBT jumping by hundreds of
milliseconds from vendor JavaScript you do not control. On example project
(mobile-majority, strict privacy posture) there is a second problem:
every classic tag ships vendor code to the user's device and lets the
vendor see the visitor's raw IP address — unacceptable for an
anonymous 21+ platform.

## Context

Cloudflare Zaraz is a server-side tag manager built on Workers. The
page loads one small first-party loader; vendor integrations execute
in a Workers-based environment at the edge, not in the browser.
Events (pageviews, `zaraz.track` calls) are POSTed to a first-party
endpoint on your own domain, and the Worker forwards them to vendors
via their server-side APIs (GA4 Measurement Protocol, Meta
Conversions API, etc.). Vendor JavaScript never reaches the device.
For a Next.js static export on Cloudflare Pages, Zaraz is enabled
zone-wide with zero build changes — the loader is auto-injected, or
can be added manually if auto-injection is disabled.

## How Zaraz works

```
Classic tag manager                Zaraz (edge)
─────────────────────────────      ─────────────────────────────
Browser downloads GTM (~100KB+)    Browser loads 1 small loader
GTM downloads N vendor scripts     Loader batches events, POSTs
Each vendor JS parses/executes     to first-party /cdn-cgi path
on the MAIN THREAD                     │
Vendor sets 3rd-party cookies,         ▼
sees user IP + fingerprint         Worker at nearest PoP runs
                                   tool integrations server-side
                                       │
                                       ▼
                                   HTTPS calls to vendor APIs
                                   (GA4 MP, Meta CAPI, Mixpanel)
                                   — IP hidden or anonymized

Browser main-thread cost:          Browser main-thread cost:
loader + all vendor bundles        loader only
```

Key consequence: main-thread JavaScript cost of a tag becomes
near-constant regardless of how many tools you enable. Adding a
second or fifth vendor changes edge work, not client work.

## Why the payoff is disproportionately mobile

```
INP pass rate (good <= 200ms), CrUX via Web Almanac 2025
────────────────────────────────────────────────────────
Desktop pages with good INP        97%
Mobile pages with good INP         77%
Gap                                20 points

Same JS bundle, different silicon:
  Desktop CPU: fast cores, active cooling
  Median mobile SoC: slower cores, thermal throttling
  → the SAME vendor script blocks a mobile main thread
    several times longer than a desktop one
```

Third-party tags are pure main-thread overhead: parse + compile +
execute, often re-entering on every interaction (auto-click
tracking, scroll listeners). Desktop absorbs this inside the 200ms
INP budget; mobile does not. Removing a GTM container plus two or
three pixel bundles typically eliminates 100-300KB of client
JavaScript and the long tasks it creates — savings that land almost
entirely in the mobile INP/TBT column, which is exactly where
example project's majority traffic lives.

## Configuring tools, triggers, and events

Zaraz is configured in the dashboard (or via its Config API):
add a tool, then wire triggers to actions.

```
Concept    What it is
──────────────────────────────────────────────────────────────
Tool       A vendor integration (GA4, Meta, Mixpanel, custom)
Event      Pageview (automatic) or a zaraz.track() call
Trigger    Rule matching events (Event Name == "signup_21plus")
Action     "When trigger fires, send X to tool Y"
```

```javascript
// Client side: the only tracking code the browser ever runs.
// Fire a custom event with properties:
zaraz.track('post_created', { board: 'confessions' });

// E-commerce style events skip trigger wiring entirely —
// Zaraz maps them to each tool's native format:
zaraz.ecommerce('Order Completed', { value: 4.99 });
```

Tools with Automated Actions (pageviews etc.) work with a toggle;
others need a trigger (Match rule on Event Name) plus a Custom
Action mapping event properties to the vendor's fields. Note that
Zaraz does not replicate every automatic event the GA4 browser
snippet collects — scroll depth, outbound clicks, and similar must
be rebuilt as explicit `zaraz.track` calls and triggers.

## Consent management and TCF

Zaraz ships a built-in Consent Management platform (CMP): a
first-party consent modal, purposes you define, and per-tool purpose
assignment. Tools assigned to a purpose simply do not fire (client
or edge) until the visitor grants it — enforcement happens before
any vendor call. An opt-in "IAB TCF compliant modal" mode makes the
CMP operate under the IAB Transparency & Consent Framework, and a
Google Consent Mode integration forwards consent signals to Google
tools. For example project this means GDPR-grade consent without adding yet
another third-party CMP script to the page.

```
Dashboard path: Zaraz → Consent
  1. Enable Consent Management
  2. Define purposes (e.g. "Analytics", "Marketing")
  3. Assign each tool to a purpose
  4. Optional: check "Use IAB TCF compliant modal"
```

## What Zaraz cannot replace

- **Tags needing live DOM access** — heatmaps, session replay
  (Hotjar/FullStory-class tools), A/B testing snippets that mutate
  the page. These fundamentally require code in the browser; running
  them via Zaraz's Custom HTML escape hatch reintroduces the exact
  client cost you were removing.
- **Vendor auto-instrumentation** — GA4 enhanced measurement,
  pixel auto-events. You must re-express these as explicit
  `zaraz.track` calls.
- **Widgets with UI** — chat bubbles, embedded players. Zaraz moves
  data collection, not user-facing UI.

For an anonymous platform this is mostly a feature: session replay
is off the table for privacy reasons anyway.

## Privacy, pricing, and debugging

Privacy: because the Worker makes the vendor call, the vendor sees
Cloudflare's edge, not the user. Zaraz exposes per-tool "Hide
Originating IP Address" (vendor never receives the visitor IP) and
"Anonymize Originating IP Address" (IP sent with the vendor's
anonymization flag). For example project, hide-IP plus trimmed event
payloads means vendors receive only fields we explicitly forward —
no raw IPs, no vendor cookies, no device fingerprinting surface.

Pricing (verified 2026-08-17): every Cloudflare account gets
1,000,000 free Zaraz Events per month on any plan; beyond that the
paid tier is $5 per additional 1,000,000 events. An event is
anything sent to Zaraz (pageview, `zaraz.track`, ...). Without paid
billing enabled you get emails at 50/80/90% usage and Zaraz is
disabled for the rest of the cycle once the free million is
exhausted — enable Zaraz Paid before launch traffic.

```javascript
// Debugging: get the Debug Key from Zaraz → Settings, then in
// the browser console on your site:
zaraz.debug("YOUR_DEBUG_KEY")   // opens debugger pop-up:
                                // events, matched triggers,
                                // per-tool dispatch results
zaraz.debug()                   // removes the cookie, turns it off
```

## Anti-patterns

- **Loading GTM through Zaraz Custom HTML** — injecting the GTM
  container as a custom tag ships the whole client-side bundle
  again. Migrate tools to native Zaraz integrations instead.
- **Treating Zaraz as a drop-in GA4 snippet** — assuming enhanced
  measurement events arrive automatically. They do not; audit which
  auto-events you rely on and rebuild them as triggers.
- **Leaving IP forwarding at defaults for sensitive platforms** —
  hide/anonymize IP is per-tool configuration, not a global switch.
  On an anonymous platform, verify it on every tool you add.
- **Skipping the CMP because "Zaraz is server-side"** — server-side
  execution does not waive consent requirements; data still flows
  to vendors and GDPR/ePrivacy still apply.

## Gotchas

- **Browser code cannot see the tools** — Zaraz runs vendors
  server-side, so tag-assistant browser extensions, pixel helpers,
  and `window.dataLayer` checks show nothing. Verify with
  `zaraz.debug()` and Zaraz Monitoring, not browser extensions.
- **E2E tests must change strategy** — Playwright/Cypress tests
  that assert on vendor network requests from the page will fail;
  the browser only emits POSTs to the first-party Zaraz endpoint
  (`/cdn-cgi/zaraz/...`). Assert on those requests, or stub the
  endpoint; also block it in CI so test runs do not burn real
  Zaraz Events or pollute analytics.
- **Free-tier hard stop** — at 1M events without Zaraz Paid,
  Zaraz turns off until next cycle: analytics silently goes dark
  mid-month on a traffic spike.
- **Ad blockers still matter, less** — the loader and first-party
  endpoint are on your domain, so generic third-party blocklists
  miss them, but aggressive blockers target `/cdn-cgi/zaraz` paths
  specifically. Expect better capture than client pixels, not 100%.

## Verification

- One Zaraz loader on the page; zero vendor `<script>` tags in the
  served HTML (`curl https://example.com | grep -i script`).
- Lighthouse mobile TBT unchanged (within noise) after enabling
  each additional Zaraz tool.
- `zaraz.debug("KEY")` shows pageview + `zaraz.track` events
  matching triggers and dispatching to each configured tool.
- Vendor dashboards receive events with no visitor IP (hide-IP
  enabled per tool) and no vendor cookies set on the client.
- Consent modal blocks all tool dispatch until purpose granted;
  TCF mode enabled if serving EU ad traffic.
- Zaraz Paid enabled (or usage alerts monitored) before exceeding
  1M events/month.

## Related

- `documentation/categories/performance/core-web-vitals-mobile-desktop-disparity-edge-caching.md`
- `documentation/categories/performance/web-performance-budgets-core-web-vitals.md`
- `documentation/categories/performance/tag-manager-performance.md`
- `documentation/categories/performance/analytics-performance-impact.md`

## Source URLs (verified 2026-08-17)

- Zaraz FAQ (IP hiding, limitations, debug) — https://developers.cloudflare.com/zaraz/faq/
- Zaraz pricing — https://developers.cloudflare.com/zaraz/pricing-info/
- Zaraz Consent Management platform — https://developers.cloudflare.com/zaraz/consent-management/
- Zaraz debug mode — https://developers.cloudflare.com/zaraz/web-api/debug-mode/
- Web Almanac 2025: Performance (mobile 77% vs desktop 97% good INP) — https://almanac.httparchive.org/en/2025/performance
