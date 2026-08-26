# Image Lazy Loading with Intersection Observer

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Lighthouse reports excessive bytes transferred on initial load.
The network waterfall shows dozens of below-fold images fetching
in parallel with the LCP image, delaying it by 1–3 s on mobile.

## Context

Two mechanisms defer image loads until they approach the viewport:

| Mechanism              | Requires JS | Browser support    |
|------------------------|-------------|--------------------|
| `loading="lazy"`       | No          | All modern (2019+) |
| IntersectionObserver   | Yes         | Chrome 51+ / FF 55+|

Use `loading="lazy"` by default. Reach for IntersectionObserver
only when you need a custom placeholder (LQIP), need to observe
CSS background images, or must support very old browsers.

## Native loading="lazy"

```html
<!-- Below-fold image — defer fetch -->
<img

  width="512"
  height="512"
  alt="Blue running shoe, side view"
  loading="lazy"
  decoding="async"
/>
```

Always provide `width` and `height` (or `aspect-ratio` in CSS).
Without them the browser cannot reserve layout space, causing
Cumulative Layout Shift (CLS) when the image loads.

**Never add `loading="lazy"` to the LCP image.** The browser
deprioritizes lazy images; the LCP element must load immediately.

## LCP Image and fetchpriority

The Largest Contentful Paint image must load eagerly with
elevated network priority:

```html
<img

  srcset="
    /images/hero-640.webp   640w,
    /images/hero-1280.webp 1280w
  "
  sizes="100vw"
  width="1280"
  height="720"
  alt="Person running on a mountain trail"
  fetchpriority="high"
/>
```

Pair with a `<link rel="preload">` in `<head>` when the image
is rendered by a framework that hydrates asynchronously, so the
browser discovers it during the initial HTML parse.

## Intersection Observer with LQIP Blur-Up

Use IntersectionObserver when you need a low-quality image
placeholder (LQIP) that blurs up to the full image on load:

```ts
const io = new IntersectionObserver(
  (entries, observer) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      const img = entry.target as HTMLImageElement;
      if (img.dataset.src) {
        img.src = img.dataset.src;
        img.removeAttribute('data-src');
        img.classList.add('img--loaded');
      }
      observer.unobserve(img);
    });
  },
  { rootMargin: '200px 0px', threshold: 0 },
);

document
  .querySelectorAll<HTMLImageElement>('img[data-src]')
  .forEach((img) => io.observe(img));
```

```css
.img-placeholder {
  position: absolute; inset: 0;
  filter: blur(12px);
  transform: scale(1.05); /* hide blur edges */
  transition: opacity 0.4s ease;
}
.img-full { opacity: 0; transition: opacity 0.4s ease; }
.img-full.img--loaded { opacity: 1; }
.img-full.img--loaded ~ .img-placeholder { opacity: 0; }
```

Keep the LQIP base64 string under 300 bytes (4×4 px WebP).

## Mobile Viewport Considerations

On mobile the viewport is shorter and scroll speed is higher;
images enter the viewport with less warning. Adjust accordingly:

```ts
const rootMargin =
  window.innerWidth < 768 ? '400px 0px' : '200px 0px';
```

- `loading="lazy"` on iOS Safari 15.4+ works correctly; older
  versions load all images eagerly regardless of the attribute.
- Avoid lazy-loading images in the first two screen heights —
  they are likely in the initial viewport on small screens.
- Use `sizes` with `vw` units so the browser selects the
  correct `srcset` candidate at the device pixel ratio.

## Anti-patterns

- Adding `loading="lazy"` to the LCP element.
- Lazy-loading images within the first 600 px on mobile — they
  will appear to load during initial scroll.
- Omitting `width`/`height` on lazy images — causes CLS.
- Setting `rootMargin: '0px'` — images pop in visibly as the
  user scrolls instead of preloading off-screen.
- Using IntersectionObserver for all images instead of the
  native attribute — unnecessary JS complexity.

## Gotchas

- `fetchpriority="high"` is a hint; the browser may override it
  under memory pressure on low-end devices.
- Preloading the LCP image in `<head>` is sufficient; adding
  an IntersectionObserver on the same element is redundant.
- SSR frameworks may hydrate the observer after the LCP image
  has already loaded — only apply `data-src` to below-fold
  images that the server HTML clearly marks as deferred.

## Verification

- **Lighthouse mobile (4G throttle):** LCP ≤ 2.5 s.
- **WebPageTest waterfall:** below-fold images absent from the
  first two network columns.
- **CLS score:** 0 on pages with lazy images (`width`/`height`
  set on all lazy `<img>` elements).
- **DevTools Elements panel:** LCP `<img>` has no `loading`
  attribute and carries `fetchpriority="high"`.

## Related

- `performance/lcp-optimization.md`
- `performance/responsive-images-srcset.md`
- `performance/fetch-priority-hints.md`
- `frontend/html-lazy-loading-images.md`

## Source URLs (verified 2026-08-17)

- https://web.dev/articles/lazy-loading-images
- https://web.dev/articles/lcp
- https://developer.mozilla.org/en-US/docs/Web/API/Intersection_Observer_API
- https://developer.mozilla.org/en-US/docs/Web/HTML/Attributes/loading
- https://web.dev/articles/fetch-priority
