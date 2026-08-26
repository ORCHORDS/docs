# Font Loading, FOUT and Mobile Networks

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Users on 3G or congested LTE see body copy in a system
font for 1–3 s before the branded typeface swaps in
(FOUT), or text is invisible for the same window (FOIT).
CLS scores climb past the 0.1 budget when the swap
reflows every text node whose box size changes.

## Context

FOUT is worse on mobile for three compounding reasons:
RTT on 3G averages 100–300 ms so a 60 KB WOFF2 can take
1–3 s to arrive; fonts are not discovered until CSS is
parsed, stalling text paint; and mobile CPUs spend more
frame time on the resulting reflow. example project ships Inter
in three weights — without intervention, three separate
HTTP requests are each discovered after CSS parsing.

---

## 1. font-display Strategy for Mobile

```
Value     Block    Swap      Mobile outcome
--------  -------  --------  -------------------------
auto      browser  browser   Avoid; unpredictable
block     3 s      infinite  FOIT 3 s; never use
swap      0 ms     infinite  Fallback shown immediately
fallback  100 ms   3 s       Tiny FOIT, then fallback
optional  100 ms   0         Skips swap on slow network
```

- **Body/UI copy** → `optional` with a tuned fallback.
  On slow connections no swap fires; CLS contribution = 0.
- **Brand headings** → `swap` + `<link rel="preload">`
  so the font is cached before the swap window opens.
- Never use `block` for body copy: 3 s invisible text.

```css
@font-face {
  font-family: 'Inter';
  src: url('/fonts/inter-variable.woff2') format('woff2-variations');
  font-weight: 100 900;
  font-display: swap; /* headings — use optional for body */
}
```

---

## 2. Preloading with rel=preload

Preload moves the font fetch to `<head>` parse time,
before CSS is evaluated.

```html
<link rel="preload"
  as="font" type="font/woff2" crossorigin />
```

**`crossorigin` is mandatory even for same-origin fonts.**
Fonts use CORS anonymous mode; omitting it causes two
fetches (preload non-CORS + render CORS). Preload only
above-fold fonts — extra weights compete with LCP images.

---

## 3. Matching Fallback Metrics (CLS Reduction)

When `swap` fires, the layout shifts because Inter and the
system sans-serif have different ascent, descent, and
x-height. Override the fallback's metrics with the four
`@font-face` metric descriptors. As of mid-2026 Safari
supports only `size-adjust` (v15.4+); the other three
(`ascent-override`, `descent-override`, `line-gap-override`)
are ignored on WebKit but applied in Chromium and Firefox.
Apply all four; `size-adjust` alone eliminates most shift.

```css
@font-face {
  font-family: 'Inter Fallback';
  src: local('Arial');
  size-adjust: 107%;
  ascent-override: 90%;
  descent-override: 22%;
  line-gap-override: 0%;
}
body { font-family: 'Inter', 'Inter Fallback', sans-serif; }
```

Generate exact values with fontpie or `@next/font`
automatic fallback. Target per-swap CLS < 0.05.

---

## 4. Cloudflare Pages vs Google Fonts

```
Factor          Google Fonts           Cloudflare Pages
--------------  ---------------------  --------------------
DNS lookup      Extra (fonts.gstatic)  None (same origin)
TCP handshake   Extra cross-origin     Reused connection
Cache control   Their headers          You own the header
GDPR            IP sent to Google      No third-party log
font-display    ?display= param only   Full @font-face ctrl
CSP font-src    fonts.gstatic.com req  'self' only
```

Edge density and raw latency are comparable. Self-hosting
wins on privacy and control. Use Cloudflare Fonts to
auto-rewrite Google Fonts references during migration.

---

## 5. Variable Fonts: One Request for All Weights

```
Approach             Requests  Size       Round-trips
-------------------  --------  ---------  -----------
3 separate WOFF2s    3         ~60 KB     3 RTT
1 variable WOFF2     1         55–80 KB   1 RTT
Subsetted variable   1         35–45 KB   1 RTT (best)
```

On 200 ms RTT, 3 RTTs = 600 ms of pure wait. Variable
fonts appear on 41% of mobile sites (HTTP Archive 2025).
Subset with pyftsubset to keep the file under 50 KB.

```css
@font-face {
  font-family: 'Inter';
  src: url('/fonts/inter-var-latin.woff2') format('woff2-variations');
  font-weight: 100 900;
  font-display: swap;
}
```

---

## 6. @font-face and Content Security Policy

`font-src` governs both `@font-face` loads and
`<link rel="preload" as="font">`; once declared it fully
overrides `default-src` for fonts.

```http
Content-Security-Policy: default-src 'self';
  font-src 'self'; style-src 'self' 'unsafe-inline';
```

Pitfalls:
- Google Fonts binary lives on `fonts.gstatic.com`; that
  host must appear in `font-src` if any `@import` is live.
- `font-src data:` enables base64 inline fonts — avoid;
  data URIs are not HTTP-cached between navigations.

---

## Anti-patterns

- `font-display: block` on body copy — 3 s FOIT on mobile.
- Google Fonts without `?display=swap` — defaults to block.
- Preloading all weights — starves LCP images of bandwidth.
- Missing `crossorigin` on preload — double fetch; preload
  response silently discarded at render time.
- `data:` URI fonts — not cached; re-parsed every page.
- Skipping `size-adjust` when using `swap` — guaranteed
  CLS; `ascent-override` alone does not help on Safari.

---

## Gotchas

- `optional` skips swap on cold cache; private-browsing
  users always see the fallback regardless of declared value.
- Chrome may abort the `swap` window early on Save-Data
  connections even when `swap` is declared.
- `crossorigin` on preload must match the effective CORS
  mode of the `@font-face` fetch or the response is
  silently discarded.
- Variable `opsz` axes shift glyph metrics by size;
  metric overrides tuned for body may underfit headings.

---

## Verification

```bash
# Self-hosted font: long cache + Brotli compression
curl -sI https://example.com/fonts/inter-var-latin.woff2 \
  | grep -E 'cache-control|content-encoding'
# cache-control: public, max-age=31536000 / content-encoding: br

# CSP: font-src must list 'self' only when self-hosted
curl -sI https://example.com/ | grep content-security-policy
```

DevTools Network → filter `woff2`: exactly one row per
font file (no duplicate preload + render-time fetches).
PageSpeed Insights → p75 CLS field data < 0.1.
Lighthouse "Ensure text remains visible during webfont
load" should report no warnings.

---

## Related

- `performance/cls-prevention.md`
- `performance/font-display-swap.md`
- `performance/font-preloading.md`
- `performance/font-subsetting.md`
- `performance/critical-rendering-path.md`

## Source URLs (verified 2026-08-17)

- https://almanac.httparchive.org/en/2025/fonts
- https://web.dev/articles/css-size-adjust
- https://developer.mozilla.org/en-US/docs/Web/CSS/@font-face/font-display
- https://caniuse.com/?search=ascent-override
- https://developers.cloudflare.com/speed/optimization/content/fonts/
- https://content-security-policy.com/font-src/
- https://fontcompressor.com/blog/self-hosting-google-fonts
- https://www.corewebvitals.io/pagespeed/responsive-font-loading-strategy
