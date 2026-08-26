# Cloudflare Zaraz — Zero-Impact Third-Party Script Loading

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

Google Tag Manager loads 12 third-party scripts (analytics, chat widgets, A/B testing, pixels) that collectively add 800 ms to TTI on a 4G mobile connection and account for 40 % of your Lighthouse "Reduce JavaScript execution time" warning.  Removing them is not an option — marketing and product teams require them.  Traditional async/defer tricks help but still leak main-thread time.  You need a way to offload the entire third-party script footprint without breaking tag functionality.

## Context

**Cloudflare Zaraz** is a server-side tag manager that runs third-party tool logic inside a Cloudflare Worker rather than in the browser.  Instead of the browser downloading, parsing, and executing each vendor's SDK, Zaraz proxies the relevant API calls to vendor servers from the edge.  The browser receives only a single tiny Zaraz loader script (< 4 KB minified).

Mobile vs desktop impact:
- On desktop broadband, 12 third-party scripts in GTM add ~400 ms to TBT and ~300 ms to LCP (render-blocking tracking pixels, synchronous cookie writes).
- On 4G mobile (10 Mbps, 60 ms RTT), the same scripts add 1.2–2.0 s to TBT.  Each script requires its own TCP connection (pre-H2) or H2 stream plus DNS resolution (no browser cache cross-origin).
- With Zaraz, the browser downloads 1 script from its own origin, Zaraz fires the vendor calls from the Worker (collocated with CF's network backbone to vendor servers), and the browser never executes vendor JavaScript at all for server-side tools.

Zaraz supports two execution modes per tool:
- **Server-side** (recommended): Zaraz calls the vendor HTTP endpoint from the Worker.  Zero browser JS from that vendor.
- **Managed component** (fallback): Zaraz still loads the vendor JS but wraps it in a Web Worker for main-thread isolation.

## Section 1 — Enabling and Configuring Zaraz

Zaraz is available on all Cloudflare zones (including Free tier with limited tools).  Enable it in the Cloudflare dashboard under **Zaraz** (left nav on the zone).

**Zaraz works without code changes to your site** — it injects the loader automatically if you enable the HTML rewriter mode.  For Next.js on Pages, inject the loader explicitly:

```javascript
// app/layout.tsx
export default function RootLayout({ children }) {
  return (
    <html>
      <head>
        {/* Zaraz loader — single script, served from your own domain */}
        <script  referrerPolicy="origin" />
      </head>
      <body>{children}</body>
    </html>
  );
}
```

The path `/cdn-cgi/zaraz/i.js` is served by Cloudflare's edge — it is your own origin's URL, so no additional DNS resolution or TCP connection is needed by the browser.

## Section 2 — Migrating GTM Tools to Zaraz

In the Zaraz dashboard, add tools one-by-one.  For each tool, configure **triggers** (equivalent to GTM triggers) and **events** (equivalent to GTM tags).

**Example: Google Analytics 4**

1. Add tool → select "Google Analytics 4"
2. Enter Measurement ID (`G-XXXXXXXX`)
3. Choose execution mode: **Server-side** (Zaraz sends `collect` hits to `www.google-analytics.com/mp/collect` from the Worker)
4. Add trigger: **Pageview** on every page load
5. Add event: `page_view` with auto-mapped `page_location` and `page_title`

The browser sends no request to `google-analytics.com`.  Zaraz's Worker sends a server-to-server HTTP call from the CF PoP.  Google Analytics receives the hit with the user's real IP forwarded in `x-forwarded-for`.

**Example: Meta Pixel**

The Meta Conversions API (CAPI) endpoint is the server-side equivalent of the browser Pixel.  Zaraz integrates CAPI natively:

1. Add tool → select "Meta Pixel"
2. Enter Pixel ID and API access token
3. Select execution mode: **Server-side (CAPI)**
4. Map conversion events to Zaraz triggers

Result: the `connect.facebook.net` domain never loads in the browser.  On mobile, this alone saves 250 ms TTI (Meta Pixel JS is 85 KB and makes its own sub-resource requests).

## Section 3 — Custom Worker Tool for Unsupported Vendors

When a vendor is not in Zaraz's built-in catalog, use a **Custom HTML** tool (Managed Component) or write a **Custom Worker action**:

```javascript
// Zaraz Custom Action (runs in the Worker, not in the browser)
// Triggered on "Purchase" event
export default {
  async run({ zaraz, client }) {
    const { orderId, total, currency } = zaraz.e.data;

    // Fire a server-side webhook to your internal data warehouse
    await fetch('https://ingest.internal.example.com/events', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        event:    'purchase',
        order_id: orderId,
        total,
        currency,
        country:  client.country,
        ts:       Date.now(),
      }),
    });
  },
};
```

Custom actions are authored in the Zaraz dashboard under **Tools → Custom Tool → Worker action**.  They have access to Zaraz's event payload (`zaraz.e`) and the client context (`client.country`, `client.userAgent`, `client.ip`).

## Section 4 — Performance Measurement and Validation

**Before Zaraz:** collect a baseline using WebPageTest with a Moto G Power profile and Fast 4G network:
- Record TBT, TTI, total JS transferred, number of third-party requests.
- Typical: 15–25 third-party requests, 400–900 KB third-party JS, TBT 600–1500 ms on mobile.

**After Zaraz:** same WebPageTest profile:
- Expected: 1 request to `/cdn-cgi/zaraz/i.js` (< 4 KB), 0 third-party JS requests, TBT reduction of 40–70 %.
- LCP improvement: 150–400 ms (elimination of render-blocking tracking pixels and cookie-sync scripts).
- INP improvement: 20–60 ms (removal of heavy event listeners attached by vendor SDKs).

**Verify tag parity** — confirm that marketing and analytics tools still receive correct data:
- Check GA4 real-time view during a test session
- Use Meta Events Manager to confirm CAPI events are received
- Use Zaraz's **Event log** in the dashboard (shows every triggered event, its payload, and vendor response code)

**Zaraz debug mode** (for developers):

Add `?zaraz-debug=true` to any URL on your zone.  Zaraz renders a debug panel in the browser showing every event that fired, which tools received it, and the server-side response.

## Anti-patterns

- **Running all tools in Managed Component mode** — Managed Components still load vendor JS in a Web Worker.  Web Workers consume memory and have non-zero parsing cost.  For analytics and pixels that have server-side API equivalents, always prefer Server-side mode.
- **Loading GTM alongside Zaraz** — removes all Zaraz benefits.  Zaraz is a GTM replacement, not a complement.  Migrate all tags out of GTM before disabling it.
- **Mapping too many custom properties without sanitization** — Zaraz passes `zaraz.e.data` to vendor APIs.  Unsanitized user-supplied values (form inputs) in event data can leak PII to vendor servers unintentionally.
- **Relying on `document.cookie` for consent state** — Zaraz has a built-in consent management framework.  Use Zaraz's consent API to gate tool firing, rather than checking cookies in Custom HTML (which runs in the browser and re-introduces JS cost).
- **Ignoring Zaraz's sampling for high-volume events** — Zaraz Worker calls count toward your Worker request quota.  On high-traffic sites, scroll-depth events (100+ per page-view) can exhaust the free 100 k requests/day quota.  Sample these: fire every 5th scroll event, not every scroll.

## Gotchas

- Zaraz server-side calls use the CF edge IP, not the user's IP, unless you configure the `x-forwarded-for` passthrough.  Some vendors (Meta CAPI, TikTok Events API) require the user IP for deduplication and attribution.  Always forward `client.ip` in the event payload.
- Zaraz modifies your HTML via CF's HTML Rewriter.  If your origin already streams HTML with `Transfer-Encoding: chunked`, the Rewriter buffers the entire response before injecting the loader, adding TTFB latency.  Disable the auto-inject and use the explicit `<script>` tag in your layout instead.
- Tools in Managed Component mode run in a separate `iframe` + Web Worker sandbox.  Some vendor SDKs that rely on `window.parent` or `document.cookie` cross-frame access will break.  Test each tool with Zaraz debug mode.
- Zaraz caches the tool configuration at the edge.  Configuration changes take up to 30 s to propagate.  During this window, old and new tool configs may co-exist across PoPs.
- Zaraz is not available on `*.workers.dev` domains or on Cloudflare Tunnel-proxied origins not attached to a zone.  It requires a zone with Cloudflare proxy enabled (orange cloud).

## Verification

1. Open `https://yoursite.com/?zaraz-debug=true` on a Chrome Android device.  Confirm the Zaraz panel appears and shows the expected events firing with 200 OK vendor responses.
2. Run WebPageTest (Moto G Power, Fast 4G) before and after.  Confirm `connect.facebook.net`, `www.googletagmanager.com`, and other vendor domains appear zero times in the waterfall after migration.
3. Check GA4 real-time: open `/`, confirm a page_view event appears in GA4 real-time within 10 s.
4. Check Zaraz dashboard Event log for any failed tool calls (non-200 vendor responses) and resolve mapping issues.

## Related

- `third-party-script-impact.md` — quantifying third-party script cost
- `tag-manager-performance.md` — generic tag manager performance strategies
- `analytics-performance-impact.md` — analytics script performance trade-offs
- `analytics-engine-rum-web-vitals.md` — replacing RUM vendor SDK with AE
- `workers-cpu-time-optimization.md` — Worker CPU budget awareness for Zaraz actions
- `inp-optimization.md` — INP gains from main-thread offload

## Sources

- Cloudflare Zaraz documentation: https://developers.cloudflare.com/zaraz/
- Zaraz Managed Components: https://developers.cloudflare.com/zaraz/managed-components/
- Zaraz consent management: https://developers.cloudflare.com/zaraz/consent-management/
- Meta Conversions API: https://developers.facebook.com/docs/marketing-api/conversions-api/
- WebPageTest device profiles: https://www.webpagetest.org/
