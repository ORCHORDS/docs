# Critical Rendering Path — CSS Optimization and Above-the-Fold Performance

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your Lighthouse score shows a First Contentful Paint (FCP) of 3.2
seconds and Largest Contentful Paint (LCP) of 5.1 seconds. The
waterfall reveals that a 250 KB stylesheet blocks rendering — the
browser cannot paint anything until the entire CSS file is downloaded
and parsed, even though most of the CSS rules apply to content below
the fold or on other pages. Users on 3G connections see a blank white
screen for 4+ seconds. Your Core Web Vitals fail the "good" threshold,
affecting search ranking.

## Context

The Critical Rendering Path (CRP) is the sequence of steps the browser
takes to convert HTML, CSS, and JavaScript into pixels on screen: DOM
construction → CSSOM construction → Render Tree → Layout → Paint →
Composite. CSS is render-blocking by default — the browser will not
paint any content until it has built the complete CSSOM. JavaScript is
parser-blocking — a `<script>` tag without `async` or `defer` halts
DOM construction until the script is downloaded and executed. In 2026,
optimizing the CRP remains the single most impactful technique for
improving FCP and LCP. The core strategy is to inline the critical CSS
(styles needed for above-the-fold content) in the `<head>` and defer
all other CSS, eliminating the render-blocking stylesheet request.

## Critical Rendering Path stages

```
1. DOM Construction
   HTML bytes → characters → tokens → nodes → DOM tree
   Parser-blocking: <script> tags halt DOM construction

2. CSSOM Construction
   CSS bytes → characters → tokens → nodes → CSSOM tree
   Render-blocking: browser waits for full CSSOM before painting

3. Render Tree
   DOM + CSSOM → Render Tree (visible elements only)
   Elements with display:none excluded

4. Layout
   Render Tree → calculate geometry (position, size)
   Viewport-dependent, recalculated on resize

5. Paint
   Layout → pixel data for each layer
   Text, colors, images, borders, shadows

6. Composite
   Layers → final screen output
   GPU-accelerated for transformed/animated elements
```

## Critical CSS extraction

```javascript
// Build-time: extract critical CSS with critters (Webpack/Vite)
// vite.config.js
import critters from 'critters-webpack-plugin';

export default {
  plugins: [
    critters({
      preload: 'swap',        // preload non-critical CSS
      inlineFonts: false,     // don't inline font data
      pruneSource: true,      // remove inlined rules from source
      compress: true,         // minify inlined CSS
    }),
  ],
};

// Next.js: critical CSS is handled automatically
// Inline styles for above-the-fold, async load rest

// Manual extraction with penthouse (Node.js)
const penthouse = require('penthouse');

const criticalCss = await penthouse({
  url: 'https://example.com',
  cssString: fullCss,
  width: 1300,
  height: 900,
  forceInclude: ['.header', '.hero', '.nav'],
  timeout: 30000,
});
```

## Inline critical CSS pattern

```html
<head>
  <!-- Critical CSS inlined — no render-blocking request -->
  <style>
    /* Only styles for above-the-fold content */
    :root { --bg: #fff; --text: #1a1a1a; --primary: #0066cc; }
    body { margin: 0; font-family: system-ui, sans-serif; color: var(--text); }
    .header { display: flex; align-items: center; padding: 1rem 2rem; }
    .hero { padding: 4rem 2rem; text-align: center; }
    .hero h1 { font-size: 2.5rem; margin: 0 0 1rem; }
    .nav { display: flex; gap: 1.5rem; list-style: none; }
  </style>

  <!-- Non-critical CSS loaded asynchronously -->
  <link rel="preload"  as="style"
        onload="this.onload=null;this.rel='stylesheet'">
  <noscript><link rel="stylesheet" ></noscript>
</head>
```

## Image optimization for LCP

```html
<!-- LCP image: preload with high priority -->
<link rel="preload" as="image"
      fetchpriority="high" type="image/webp">

<!-- Hero image with explicit dimensions (prevents layout shift) -->
<img
     alt="Hero banner"
     width="1200" height="600"
     fetchpriority="high"
     decoding="async">

<!-- Below-fold images: lazy load -->
<img
     alt="Feature"
     width="600" height="400"
     loading="lazy"
     decoding="async">
```

## JavaScript optimization

```html
<!-- Parser-blocking (BAD — default) -->
<script ></script>

<!-- Async: download in parallel, execute when ready (non-deterministic order) -->
<script  async></script>

<!-- Defer: download in parallel, execute after DOM parsed (preserves order) -->
<script  defer></script>

<!-- Module: deferred by default -->
<script type="module" ></script>

<!-- Inline critical JS only (route initialization) -->
<script>
  // Minimal inline JS for critical path only
  document.documentElement.classList.add('js-enabled');
</script>
```

## Font optimization

```css
/* Use font-display: swap to prevent FOIT (Flash of Invisible Text) */
@font-face {
  font-family: 'Brand';
  src: url('/fonts/brand.woff2') format('woff2');
  font-display: swap;
  font-weight: 400;
  unicode-range: U+0000-00FF; /* Latin subset only */
}
```

```html
<!-- Preload critical fonts -->
<link rel="preload"  as="font"
      type="font/woff2" crossorigin>

<!-- Preconnect to font CDN -->
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
```

## Measuring CRP performance

```
Core Web Vitals targets (2026):
  FCP  (First Contentful Paint):    < 1.8s (good), < 3.0s (needs improvement)
  LCP  (Largest Contentful Paint):  < 2.5s (good), < 4.0s (needs improvement)
  CLS  (Cumulative Layout Shift):   < 0.1  (good), < 0.25 (needs improvement)
  INP  (Interaction to Next Paint): < 200ms (good), < 500ms (needs improvement)

Tools:
  → Lighthouse (Chrome DevTools, CI)
  → WebPageTest (real device, multiple locations)
  → Chrome DevTools Performance panel
  → web-vitals library (Real User Monitoring)
  → CrUX (Chrome User Experience Report)
```

## Anti-patterns

- **Loading all CSS in one file** — a single 300 KB stylesheet
  blocks rendering for all pages, even though each page uses only
  20% of the rules. Split CSS by route/component and inline only
  the critical portion.
- **Render-blocking third-party scripts** — placing analytics,
  chat widgets, or A/B testing scripts in `<head>` without `async`
  or `defer`. These block DOM construction and delay FCP. Load
  third-party scripts asynchronously or after the page loads.
- **Web fonts without font-display** — loading custom fonts
  without `font-display: swap` causes invisible text (FOIT) until
  the font downloads. Users see a blank page even though content
  has rendered.
- **Missing image dimensions** — omitting `width` and `height`
  attributes on images causes layout shift (CLS) when images load.
  Always specify dimensions or use CSS `aspect-ratio`.

## Gotchas

- **Critical CSS invalidation** — inlined critical CSS becomes
  stale when styles change. Regenerate critical CSS as part of
  the build pipeline on every deploy. Do not manually maintain
  inlined styles.
- **HTTP/2 push is deprecated** — HTTP/2 Server Push was designed
  to solve the CRP problem but was removed from Chrome in 2022.
  Use `<link rel="preload">` instead for early resource loading.
- **Above-the-fold varies by viewport** — critical CSS for a
  1920px desktop viewport differs from a 375px mobile viewport.
  Generate critical CSS for multiple viewport sizes or target the
  smallest (mobile-first) for the widest coverage.
- **Excessive inlining** — inlining too much CSS (>14 KB) negates
  the benefit because it exceeds the initial TCP congestion window
  (typically 14 KB). Keep inlined critical CSS under 14 KB for
  optimal first-round-trip rendering.

## Verification

- FCP is under 1.8 seconds on 3G throttled connection.
- LCP is under 2.5 seconds for the primary landing page.
- No render-blocking CSS or JS in the critical path.
- Critical CSS is inlined in `<head>` and under 14 KB.
- LCP image is preloaded with `fetchpriority="high"`.
- Web fonts use `font-display: swap` and are preloaded.
- CLS is under 0.1 (all images have explicit dimensions).

## Related

- `documentation/docs/policies/performance/core-web-vitals-optimization.md`
- `documentation/docs/policies/performance/image-optimization-formats.md`
- `documentation/docs/policies/frontend/ssr-streaming-hydration.md`

## Source URLs (verified 2026-08-16)

- Browser Rendering Performance: Critical Rendering Path Guide — https://webeyez.com/insights/guides/browser-rendering-performance-guide
- Optimize the Critical Rendering Path in 2026 — https://pagespeedplus.com/blog/critical-rendering-path
- How Web Browsers Render Pages: 2026 Performance Guide — https://www.digitalapplied.com/blog/how-web-browsers-render-pages-performance-guide
- Optimizing Front-End Performance: Critical CSS & Lazy Loading — https://zvirec.com/critical-css-optimization-guide/
