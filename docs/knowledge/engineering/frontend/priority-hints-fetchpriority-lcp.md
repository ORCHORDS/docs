# Priority Hints and fetchpriority for LCP Optimization

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

The browser's default resource priority queue deprioritizes hero images and late-discovered LCP candidates, causing them to be fetched after render-blocking CSS or below-the-fold images that appear earlier in the HTML. `fetchpriority="high"` corrects the queue position without changing load order in the HTML.

## Context

Priority Hints (`fetchpriority` attribute on `<img>`, `<link>`, `<script>`, and `<iframe>`, plus `priority` option in the `fetch()` API) are now Baseline 2023 and available in all evergreen browsers. Cloudflare Pages and Workers can inspect the request's `Save-Data` header or `CF-Device-Type` to make server-side decisions about which assets to preload and at what priority. Combined with HTTP 103 Early Hints, this gives sub-50 ms LCP on repeated navigations.

## Marking the LCP Image High Priority

The browser assigns `<img>` elements a "Low" or "Medium" fetch priority by default. An LCP hero image should be "High".

```tsx
// src/components/Hero.tsx
interface HeroProps {
  src: string;
  alt: string;
  width: number;
  height: number;
}

export function Hero({ src, alt, width, height }: HeroProps) {
  return (
    <img
      src={src}
      alt={alt}
      width={width}
      height={height}
      // Opt into the highest priority tier
      fetchPriority="high"
      // Never lazy-load the LCP image
      loading="eager"
      // Decode off-thread but do not defer layout
      decoding="async"
    />
  );
}
```

In Next.js / React, use the string casing `fetchPriority` (React normalises to `fetchpriority` in HTML).

## Lowering Priority for Below-the-Fold Images

```tsx
// src/components/ImageGrid.tsx
interface GridImage {
  src: string;
  alt: string;
}

interface ImageGridProps {
  images: GridImage[];
  aboveFold?: number; // how many images are above the fold
}

export function ImageGrid({ images, aboveFold = 2 }: ImageGridProps) {
  return (
    <ul role="list" className="image-grid">
      {images.map((img, i) => (
        <li key={img.src}>
          <img
            src={img.src}
            alt={img.alt}
            loading={i < aboveFold ? "eager" : "lazy"}
            fetchPriority={i === 0 ? "high" : i < aboveFold ? "auto" : "low"}
            decoding="async"
            width={600}
            height={400}
          />
        </li>
      ))}
    </ul>
  );
}
```

## Preload with Priority in `<link>`

`<link rel="preload">` combined with `fetchpriority` affects where in the preload scanner queue the asset lands.

```tsx
// app/layout.tsx
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        {/* Preload LCP image at high priority */}
        <link
          rel="preload"

          as="image"
          type="image/avif"
          // @ts-expect-error fetchPriority is not yet in React's type defs for <link>
          fetchPriority="high"
        />
        {/* Preload web font — medium priority by default, keep it */}
        <link
          rel="preload"

          as="font"
          type="font/woff2"
          crossOrigin="anonymous"
        />
        {/* Defer non-critical analytics script */}
        <link
          rel="preload"

          as="script"
          // @ts-expect-error
          fetchPriority="low"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
```

## Edge-Side Priority Decision via `CF-Device-Type`

Cloudflare sets `CF-Device-Type: mobile | desktop | tablet` on requests. On mobile, avoid preloading large desktop-optimised images.

```typescript
// functions/_middleware.ts
type DeviceType = "mobile" | "tablet" | "desktop";

function getDevice(request: Request): DeviceType {
  const raw = request.headers.get("CF-Device-Type") ?? "desktop";
  return raw as DeviceType;
}

export const onRequest: PagesFunction = async (context) => {
  const device = getDevice(context.request);
  const response = await context.next();

  if (!response.headers.get("content-type")?.includes("text/html")) {
    return response;
  }

  return new HTMLRewriter()
    .on('img[data-lcp="true"]', {
      element(el) {
        el.setAttribute("fetchpriority", "high");
        el.setAttribute("loading", "eager");
        if (device === "mobile") {
          // Swap src to mobile-optimised AVIF
          const src = el.getAttribute("src") ?? "";
          el.setAttribute("src", src.replace("/images/", "/images/mobile/"));
        }
      },
    })
    .transform(response);
};
```

## Using `fetch()` Priority in Workers

The `fetch()` API accepts a `priority` option (non-standard, supported in Cloudflare Workers and Chrome).

```typescript
// functions/api/critical-data.ts
export const onRequestGet: PagesFunction = async (context) => {
  const [critical, secondary] = await Promise.all([
    // High-priority upstream call for above-the-fold data
    fetch("https://api.example.com/hero", {
      // @ts-expect-error priority is non-standard
      priority: "high",
      headers: { Authorization: `Bearer ${context.env.API_TOKEN}` },
    }),
    // Low-priority call for sidebar recommendations
    fetch("https://api.example.com/recommendations", {
      // @ts-expect-error
      priority: "low",
      headers: { Authorization: `Bearer ${context.env.API_TOKEN}` },
    }),
  ]);

  const [hero, recs] = await Promise.all([
    critical.json(),
    secondary.json(),
  ]);

  return Response.json({ hero, recs });
};
```

## Measuring the Impact

```typescript
// src/lib/measure-lcp.ts
export function measureLCP(onLCP: (entry: PerformanceEntry) => void): void {
  if (!("PerformanceObserver" in window)) return;

  const observer = new PerformanceObserver((list) => {
    const entries = list.getEntries();
    const last = entries[entries.length - 1];
    onLCP(last);
    observer.disconnect();
  });

  observer.observe({ type: "largest-contentful-paint", buffered: true });
}

// Usage in app entry
measureLCP((entry) => {
  const lcp = entry as PerformancePaintTiming;
  console.debug(`LCP: ${lcp.startTime.toFixed(0)} ms`);
  // Send to Cloudflare Analytics or RUM endpoint
  navigator.sendBeacon("/api/rum", JSON.stringify({ lcp: lcp.startTime }));
});
```

## Anti-patterns

- Setting `fetchpriority="high"` on every image — degrades to no priority differentiation, browser ignores the signal
- Combining `fetchpriority="high"` with `loading="lazy"` on the LCP image — lazy load always wins; image is deferred
- Using `<link rel="preload">` without `fetchpriority` for non-critical assets — they compete with LCP resources at "High" by default
- Relying on `fetchpriority` without also removing render-blocking resources — priority hints only reorder the queue they cannot remove blocking

## Gotchas

- Firefox shipped `fetchpriority` support in version 132 (2024); check Can I Use before dropping the `<link rel="preload">` fallback
- `priority` in `fetch()` is a non-standard extension; TypeScript types do not include it — suppress with `// @ts-expect-error`
- Cloudflare's `CF-Device-Type` header is only available when Cloudflare's Bot Management or Browser Integrity Check is enabled on the zone
- Priority hints affect only the browser's network scheduler — they do not change parse-tree order or rendering order

## Verification

1. Open Chrome DevTools → Network tab → right-click column header → enable "Priority". Confirm the LCP image shows "Highest".
2. Run `npx unlighthouse --site https://<project>.pages.dev` and compare LCP before and after applying `fetchpriority="high"`.
3. Check `performance.getEntriesByType("largest-contentful-paint")` in the DevTools console — `startTime` should be below 2500 ms on simulated 4G.

## Related

- [early-hints-103-cloudflare-pages.md](early-hints-103-cloudflare-pages.md)
- [html-web-vitals-lcp.md](html-web-vitals-lcp.md)
- [html-performance-resource-hints.md](html-performance-resource-hints.md)
- [image-format-selection-webp-avif.md](image-format-selection-webp-avif.md)
- [nextjs-image-optimization-cloudflare-pages.md](nextjs-image-optimization-cloudflare-pages.md)

## Sources

- https://developer.chrome.com/docs/web-platform/fetch-priority
- https://wicg.github.io/priority-hints/
- https://web.dev/articles/fetch-priority
- https://developer.mozilla.org/en-US/docs/Web/API/HTMLImageElement/fetchPriority
