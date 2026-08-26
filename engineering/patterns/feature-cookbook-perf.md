# feature-cookbook-perf

**Issue:** Performance recipes — bundle, image, lazy load
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your web app is slow. The page takes 5 seconds to load.
The bundle is 2 MB. The images are 5 MB each. The user
closes the tab. You wish you'd optimized earlier.

## Root cause
**Performance is a feature, not a polish step.** Build it
in.

**Source:** web.dev:
https://web.dev/performance/

## The "bundle size" pattern

For a small bundle:
```ts
// ❌ Importing the whole library
import _ from 'lodash';
const result = _.uniq([1, 2, 3]);

// ✅ Importing only what you need
import uniq from 'lodash/uniq';
const result = uniq([1, 2, 3]);

// ✅ Or use the built-in
const result = [...new Set([1, 2, 3])];
```

A smaller bundle = faster load.

## The "tree shaking" pattern

For tree shaking, use ES modules:
```ts
// ❌ CommonJS (not tree-shakable)
const utils = require('./utils');

// ✅ ES modules (tree-shakable)
import { uniqueId } from './utils';
```

Configure bundler (Vite, Webpack) for tree shaking.

## The "code splitting" pattern

For code splitting:
```tsx
import { lazy, Suspense } from 'react';

// Lazy load
const AdminPanel = lazy(() => import('./AdminPanel'));

function App() {
  return (
    <Suspense fallback={<Spinner />}>
      <Routes>
        <Route path="/admin" element={<AdminPanel />} />
        {/* ... */}
      </Routes>
    </Suspense>
  );
}
```

The admin panel is only loaded when needed.

## The "image optimization" pattern

For images:
- **WebP/AVIF:** 30-50% smaller than JPEG
- **Responsive:** multiple sizes for different screens
- **Lazy load:** only load when visible
- **CDN:** serve from edge

```tsx
<img

  srcSet="/image-320.webp 320w, /image-640.webp 640w, /image-1280.webp 1280w"
  sizes="(max-width: 640px) 100vw, 50vw"
  alt="Description"
  loading="lazy"
  decoding="async"
  width="640"
  height="480"
/>
```

The browser picks the right size.

## The "lazy load" pattern

For below-the-fold content:
```tsx
import { useEffect, useRef, useState } from 'react';

function LazyComponent({ children }: { children: React.ReactNode }) {
  const [isVisible, setIsVisible] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        setIsVisible(true);
        observer.disconnect();
      }
    });

    if (ref.current) observer.observe(ref.current);
    return () => observer.disconnect();
  }, []);

  return <div ref={ref}>{isVisible ? children : <Skeleton />}</div>;
}
```

The content loads when scrolled into view.

## The "virtual list" pattern

For long lists:
```tsx
import { useVirtualizer } from '@tanstack/react-virtual';

function VirtualList({ items }: { items: Item[] }) {
  const parentRef = useRef<HTMLDivElement>(null);

  const virtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 50,
  });

  return (
    <div ref={parentRef} style={{ height: '400px', overflow: 'auto' }}>
      <div style={{ height: virtualizer.getTotalSize() }}>
        {virtualizer.getVirtualItems().map((virtualItem) => (
          <div
            key={virtualItem.key}
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              transform: `translateY(${virtualItem.start}px)`,
              height: virtualItem.size,
            }}
          >
            {items[virtualItem.index].name}
          </div>
        ))}
      </div>
    </div>
  );
}
```

A list of 100k items renders only the visible ones.

## The "memo" pattern

For expensive components:
```tsx
import { memo } from 'react';

const ExpensiveComponent = memo(function ExpensiveComponent({ data }: { data: Data }) {
  // ... render
});
```

The component re-renders only when `data` changes.

## The "useMemo" pattern

For expensive calculations:
```tsx
import { useMemo } from 'react';

function List({ items }: { items: Item[] }) {
  const sorted = useMemo(() => {
    return [...items].sort((a, b) => a.name.localeCompare(b.name));
  }, [items]);

  return <ListView items={sorted} />;
}
```

The sort is recomputed only when `items` changes.

## The "useCallback" pattern

For stable function references:
```tsx
import { useCallback } from 'react';

function Parent() {
  const [count, setCount] = useState(0);

  // ❌ New function every render
  const handleClick = () => console.log('clicked');

  // ✅ Stable function reference
  const handleClickStable = useCallback(() => {
    console.log('clicked');
  }, []);

  return <Child onClick={handleClickStable} />;
}
```

A stable function reference prevents unnecessary re-renders.

## The "throttle/debounce" pattern

For high-frequency events:
```ts
import { throttle, debounce } from 'lodash';

const handleScroll = throttle(() => {
  // Update the UI
}, 100);

const handleSearch = debounce((query: string) => {
  // Search
}, 300);

window.addEventListener('scroll', handleScroll);
```

Throttle = at most once per N ms. Debounce = wait until N
ms of silence.

## The "preload" pattern

For critical resources:
```html
<link rel="preload"  as="font" type="font/woff2" crossorigin />
<link rel="prefetch"  as="fetch" crossorigin />
```

Preload = high priority. Prefetch = low priority.

## The "service worker" pattern

For offline + caching:
```ts
// service-worker.ts
const CACHE_NAME = 'v1';
const PRECACHE = ['/', '/static/main.js', '/static/main.css'];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE)));
});

self.addEventListener('fetch', (event) => {
  event.respondWith(
    caches.match(event.request).then((cached) => cached ?? fetch(event.request))
  );
});
```

The service worker caches + serves.

## The "Core Web Vitals" pattern

For good Web Vitals:
- **LCP (Largest Contentful Paint):** < 2.5s
- **FID (First Input Delay):** < 100ms
- **CLS (Cumulative Layout Shift):** < 0.1

```ts
// Measure
import { onLCP, onFID, onCLS } from 'web-vitals';

onLCP(console.log);
onFID(console.log);
onCLS(console.log);
```

Monitor the metrics; alert on regressions.

## The "render blocking" pattern

For non-blocking CSS/JS:
```html
<!-- ❌ Render-blocking -->
<link rel="stylesheet"  />

<!-- ✅ Non-blocking for non-critical CSS -->
<link rel="preload"  as="style" onload="this.onload=null;this.rel='stylesheet'" />
<noscript><link rel="stylesheet"  /></noscript>

<!-- ❌ Render-blocking -->
<script ></script>

<!-- ✅ Defer or async -->
<script  defer></script>
```

The page renders without waiting for non-critical resources.

## The "font" pattern

For fonts:
```css
@font-face {
  font-family: 'Inter';
  src: url('/fonts/inter.woff2') format('woff2');
  font-display: swap;  /* Use fallback, then swap */
}
```

`font-display: swap` shows text immediately; swaps when the
font loads.

## The "third-party" pattern

For third-party scripts:
```html
<!-- Load with async -->
<script async src="https://www.googletagmanager.com/gtag/js?id=..."></script>
```

Or lazy load on user interaction:
```ts
const analyticsScript = document.createElement('script');
analyticsScript.src = 'https://...';
document.head.appendChild(analyticsScript);
```

Third-party scripts can slow the page. Load them last.

## Verification
- **Test:** Bundle size is under the limit
- **Test:** Page loads in < 3s
- **Live:** Web Vitals are monitored
- **Audit:** Quarterly perf review

## Gotchas
- **The "import the whole library" anti-pattern.** A 1MB
  library for a 1KB use case is wasteful. Tree-shake.
- **The "no image optimization" anti-pattern.** A 5MB
  image on a 1MB page is bad. Resize, compress, lazy
  load.
- **The "render-blocking everything" anti-pattern.** A
  page that waits for all CSS/JS is slow. Defer, async.
- **The "no bundle analysis" anti-pattern.** Don't know
  what's in your bundle. Use `vite-bundle-visualizer`.
- **The "premature optimization" anti-pattern.** Optimize
  the hot path; ignore the cold path.
- **The "perf test in dev" anti-pattern.** Dev is not
  production. Test with prod-like conditions.

## Related
- `frontend-bundle-optimization.md`
- `caching-strategies-detail.md`
- `content-delivery-network.md`
- `accessibility-wcag-detail.md`
- web.dev: https://web.dev/performance/
- Lighthouse: https://developers.google.com/web/tools/lighthouse
- Vite: https://vitejs.dev/
- Web Vitals: https://web.dev/vitals/
