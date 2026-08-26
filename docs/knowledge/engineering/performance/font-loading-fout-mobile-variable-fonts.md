# Variable Fonts and FOUT Elimination on Mobile Networks

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

A site uses three separate font weights (400, 600, 700) of Inter, loaded as individual WOFF2 files.  On 4G mobile, all three files load sequentially after the CSS is parsed — the page shows invisible text (FOIT) for 1.2 s, then flashes to the correct font (FOUT), harming both perceived performance and CLS.  Switching to a variable font file eliminates two of the three HTTP requests, reduces total font payload by 30–50 %, and allows `font-display: optional` to be used without layout shifts.

## Context

A **variable font** encodes multiple typographic variants (weight, width, slant, optical size) as interpolation axes within a single file.  Where three separate static files might total 180 KB, the variable font for the same weight range is typically 90–120 KB — one request, half the payload.

Mobile vs desktop distinction:
- On desktop broadband (100 Mbps), three 60 KB font files cost ~5 ms each.  FOIT/FOUT is unnoticeable.
- On 4G mobile (8 Mbps, 60 ms RTT), each file costs 60 ms download + 60 ms RTT = 120 ms.  Three sequential files = 360 ms minimum, often serialised behind render-blocking CSS = 600–900 ms of invisible text.
- HTTP/2 allows parallel fetching, but fonts are discovered late (after CSS parse), so the parallel benefit is limited unless `<link rel="preload">` is used.
- With a single variable font + preload, the font fetch begins before CSS is parsed and the single file loads in ~120 ms on 4G.

**CLS implications:**
- `font-display: swap` eliminates FOIT but causes layout shifts when the real font loads (different metrics from the fallback).  CLS score suffers.
- `font-display: optional` eliminates both FOIT and FOUT by only using the font if it loads within the first render (100 ms budget).  This works for variable fonts + preload on desktop but may still miss on slow mobile connections.
- `size-adjust` + `ascent-override` + `descent-override` on the fallback makes fallback metrics match the web font metrics, eliminating CLS even with `font-display: swap`.

## Section 1 — Subsetting a Variable Font

Variable fonts include all characters in the variable range, making them larger than a subsetting of only the characters you need.  Subset aggressively:

```bash
# Install pyftsubset (part of fonttools)
pip install fonttools brotli

# Subset to Latin Extended-A (covers most European languages)
pyftsubset \
  Inter[slnt,wght].woff2 \
  --output-file=Inter-var-subset.woff2 \
  --flavor=woff2 \
  --layout-features="kern,liga,calt,tnum,zero" \
  --unicodes="U+0000-00FF,U+0100-017F,U+0180-024F,U+2000-206F,U+2074,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD"
```

Typical reduction: 340 KB variable font (full) → 90 KB subset (Latin + common symbols).

**Unicode-range splitting** (advanced): serve separate files for Latin (always loaded) and non-Latin scripts (loaded on demand):

```css
/* Base: Latin — always downloaded */
@font-face {
  font-family: 'Inter';
  src: url('/fonts/Inter-var-latin.woff2') format('woff2');
  font-weight: 100 900;
  font-style: normal;
  font-display: optional;
  unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6,
                 U+02DA, U+02DC, U+2000-206F, U+2074, U+20AC, U+2122,
                 U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD;
}

/* Extended: Greek, Cyrillic — only downloaded if page contains those chars */
@font-face {
  font-family: 'Inter';
  src: url('/fonts/Inter-var-ext.woff2') format('woff2');
  font-weight: 100 900;
  font-style: normal;
  font-display: swap;
  unicode-range: U+0370-03FF,  /* Greek */
                 U+0400-045F,  /* Cyrillic */
                 U+0490-0491;
}
```

The browser only downloads `Inter-var-ext.woff2` when the page contains Greek or Cyrillic characters.  For English-only pages on mobile, this is never downloaded.

## Section 2 — CSS font-display and Fallback Metric Matching

**font-display: optional** is the most aggressive FOUT/FOIT prevention strategy.  The browser gives the font 100 ms to load on first visit; if it misses the window, the fallback is used for that page-view.  On second visit (font is cached), the web font renders immediately.

```css
@font-face {
  font-family: 'Inter';
  src: url('/fonts/Inter-var-latin.woff2') format('woff2 supports variations'),
       url('/fonts/Inter-var-latin.woff2') format('woff2');
  font-weight: 100 900;
  font-style: normal oblique 0deg 10deg;
  font-display: optional;
}
```

The problem: on first visit on a slow mobile connection, the font almost certainly misses the 100 ms window.  The user sees the fallback (Arial/system-ui) indefinitely on that visit.  This is fine if the fallback metrics are visually close to Inter.

**Matching fallback metrics with `@font-face` overrides:**

```css
/* Override system-ui to match Inter's metrics */
@font-face {
  font-family: 'Inter-Fallback';
  src: local('Arial');
  ascent-override: 90%;          /* Inter: 90.1% */
  descent-override: 22.5%;       /* Inter: 22.4% */
  line-gap-override: 0%;
  size-adjust: 107%;             /* Inter is slightly wider than Arial */
}

body {
  font-family: 'Inter', 'Inter-Fallback', system-ui, sans-serif;
}
```

With matched fallback metrics, even if the web font loads after first paint (with `font-display: swap`), the layout does not shift because the fallback occupies exactly the same space.  CLS contribution from font swap: 0.00.

Tools to generate override values:
- `fontpie` CLI: `npx fontpie Inter-var-latin.woff2 --name Inter --style normal`
- `next/font` module (auto-generates these overrides for Google Fonts and local fonts)

## Section 3 — Preloading and Priority

```html
<!-- In <head>, before any stylesheets -->
<link rel="preload"

      as="font"
      type="font/woff2"
      crossorigin="anonymous" />
```

Preloading starts the font download before the CSS `@font-face` declaration is parsed.  On mobile 4G, this saves 200–600 ms (the CSS parse time that would otherwise delay font discovery).

**Preload via Cloudflare Pages `_headers`:**

```
/
  Link: </fonts/Inter-var-latin.woff2>; rel=preload; as=font; type="font/woff2"; crossorigin=anonymous
```

This pushes the `Link` preload header from the edge, meaning the browser begins the font fetch from the moment the HTTP response headers arrive — even before the HTML body is parsed.  On mobile with 80 ms RTT and 600 ms HTML parse time, this saves the full 600 ms.

**`fetchpriority="high"` for LCP font:**

```html
<link rel="preload"

      as="font"
      type="font/woff2"
      crossorigin="anonymous"
      fetchpriority="high" />
```

Marks the font fetch as high priority in the browser's resource scheduler.  Without this, the font competes with images and scripts at normal priority.  On bandwidth-constrained 4G connections, this can advance the font load by 100–300 ms relative to other resources.

## Section 4 — Variable Font Axis Configuration in CSS

```css
/* Use font-variation-settings for precise axis control */
.body-text {
  font-family: 'Inter', 'Inter-Fallback', sans-serif;
  font-weight: 400;              /* shorthand — maps to wght axis */
  font-optical-sizing: auto;     /* maps to opsz axis if supported */
}

.heading {
  font-weight: 700;
}

.subheading {
  font-weight: 600;
}

/* Fine-grained: animatable (avoid in INP-critical interactions) */
.animated-weight {
  font-variation-settings: 'wght' var(--font-weight, 400);
  transition: font-variation-settings 0.2s ease;
}
```

Avoid animating `font-variation-settings` on elements the user interacts with — each interpolated frame triggers text re-layout, contributing to INP.  Safe: decorative headings during scroll.  Unsafe: button labels during hover.

**Optical size axis (`opsz`)** automatically adjusts letterform details for the rendered size.  At 12 px body text, `opsz: 12` makes strokes slightly wider for legibility.  At 48 px headline, `opsz: 48` thins strokes for elegance.  This replaces the need for separate "display" and "text" fonts:

```css
h1 { font-size: 3rem;  font-optical-sizing: auto; }  /* uses opsz ~48 */
p  { font-size: 1rem;  font-optical-sizing: auto; }  /* uses opsz ~16 */
```

## Anti-patterns

- **Preloading multiple font weights** — preloading `Inter-400.woff2`, `Inter-600.woff2`, and `Inter-700.woff2` triples the font payload on the critical path.  Use one variable font file.
- **Using `font-display: block` globally** — blocks text rendering for up to 3 s waiting for the font.  On slow mobile connections, users see a blank page.  Never use `block` except for icon fonts where invisible text is worse than invisible icons.
- **Loading Google Fonts from `fonts.googleapis.com`** — adds a cross-origin DNS resolution (30–80 ms on mobile), a redirect, and a second cross-origin request.  Self-host all fonts on your own domain or CF R2.
- **Not setting `crossorigin` on font preload** — `<link rel="preload" as="font">` without `crossorigin="anonymous"` causes the browser to fetch the font twice: once for the preload (without CORS) and once for the actual use (with CORS).  Always set `crossorigin`.
- **Variable font without subsetting** — a 340 KB unsubseted variable font is worse than three 60 KB static files.  Always subset before serving.

## Gotchas

- `font-display: optional` combined with `preload` still does not guarantee font loads within 100 ms on very slow (2G/3G) mobile connections.  Design the fallback to be visually acceptable, not a placeholder.
- `size-adjust`, `ascent-override`, and `descent-override` are supported in all modern browsers but not Safari < 15.  Safari < 15 ignores them, so fallback may still shift on older iPhones.  Test with BrowserStack on iOS 14.
- Woff2 variable font support: all modern browsers.  IE11 does not support variable fonts — serve a static WOFF2 subset to legacy browsers via the `format()` hint: `format('woff2 supports variations')` with a fallback to a static woff2.
- Cloudflare's automatic minification (`Speed → Optimization → Auto Minify`) does not minify fonts.  If you serve fonts via Workers (not as static assets), ensure the worker returns correct `Content-Type: font/woff2` or the browser may fail to use them.
- `next/font` (Next.js 13+) self-hosts Google Fonts automatically and generates the fallback overrides.  Use it in preference to manual `@font-face` declarations when on Next.js.

## Verification

1. Run `wc -c /fonts/Inter-var-latin.woff2` — target < 100 KB.  Compare to sum of original static files.
2. Open DevTools Network, filter by "Font".  Confirm one request, not three.  Check the request starts immediately after HTML arrives (preload working).
3. Slow-throttle to Slow 4G in DevTools.  Reload.  Text should appear on first paint using the fallback, then switch to Inter without any visible layout shift (CLS = 0 in the Performance panel).
4. Run `fontpie Inter-var-latin.woff2 --name Inter` and cross-check the generated `size-adjust` / `ascent-override` values against what is in your CSS.

## Related

- `font-loading-fout.md` — general FOUT/FOIT strategies
- `font-display-swap.md` — font-display strategy comparison
- `font-preloading.md` — preloading mechanics
- `font-subsetting.md` — subsetting workflows
- `cls-prevention.md` — CLS from font swap
- `lcp-optimization.md` — font load impact on LCP
- `early-hints-103-cloudflare-pages-mobile.md` — pushing font preload even earlier

## Sources

- Variable fonts guide: https://web.dev/articles/variable-fonts
- font-display descriptor MDN: https://developer.mozilla.org/en-US/docs/Web/CSS/@font-face/font-display
- CSS Fonts Level 5 — size-adjust: https://www.w3.org/TR/css-fonts-5/#descdef-font-face-size-adjust
- fontpie CLI (metric calculator): https://github.com/schwarzkopfb/fontpie
- next/font documentation: https://nextjs.org/docs/app/api-reference/components/font
- pyftsubset documentation: https://fonttools.readthedocs.io/en/latest/subset/index.html
