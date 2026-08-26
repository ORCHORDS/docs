# Fetch Priority for LCP Resource Prioritization

**Issue:** Browsers can discover a Largest Contentful Paint image late or initially assign it insufficient priority, while indiscriminate high-priority hints compete with critical CSS, fonts, and scripts.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Use `fetchpriority="high"` only on a measured, above-the-fold LCP candidate. Keep the image discoverable in initial HTML, provide dimensions, responsive `srcset`/`sizes`, and avoid lazy loading it. If discovery is inherently late, pair a matching image preload with the priority hint, ensuring URL, CORS mode, media, and responsive selection agree so the browser does not fetch twice.

Use `fetchpriority="low"` for known noncritical images or scripts only after verifying it does not delay interaction. Treat `auto` as the default and remember the value is a hint: the browser retains final scheduling control.

## Verification

Measure field LCP and lab request timing before and after. In the network trace, confirm the correct resource is discovered earlier, receives higher priority, and is downloaded exactly once. Test mobile bandwidth/CPU, cold and warm caches, responsive breakpoints, authenticated/CDN variants, and browsers that ignore the hint. Monitor regressions in CSS delivery, font rendering, INP, and total bytes.

## Gotchas

Boosting several resources makes none meaningfully special and can delay more important work. Preloading the wrong responsive candidate wastes bandwidth. A priority hint cannot repair an oversized image, slow origin, render-blocking stylesheet, or client-rendered discovery chain.

## Sources

- [MDN fetchpriority attribute](https://developer.mozilla.org/en-US/docs/Web/HTML/Attributes/fetchpriority)
- [MDN HTMLImageElement.fetchPriority](https://developer.mozilla.org/en-US/docs/Web/API/HTMLImageElement/fetchPriority)
- [WHATWG HTML fetch priority attributes](https://html.spec.whatwg.org/multipage/urls-and-fetching.html#fetch-priority-attributes)
