# feature-cookbook-frontend-detail

**Issue:** Frontend — React, state, performance, a11y
**Date:** 2026-08-09
**Status:** documented

## Symptom
You build a React app. The bundle is 2MB. The page
takes 5s to load. The user complains. You wish you'd
optimized.

## Root cause
**Frontend has specific patterns.** Optimize for
them.

**Source:** React docs.

## The "code splitting" pattern

For code splitting, use lazy:
```tsx
import { lazy, Suspense } from 'react';

const Dashboard = lazy(() => import('./Dashboard'));
const Settings = lazy(() => import('./Settings'));

function App() {
  return (
    <Suspense fallback={<Spinner />}>
      <Routes>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/settings" element={<Settings />} />
      </Routes>
    </Suspense>
  );
}
```

The code is split per route.

## The "bundle analysis" pattern

For bundle analysis:
- **Vite:** `rollup-plugin-visualizer`
- **Webpack:** `webpack-bundle-analyzer`
- **Bundlephobia:** Check npm packages

```bash
# Vite
npx vite build --mode analyze
```

The bundle is analyzed.

## The "image optimization" pattern

For images, use next-gen formats:
```tsx
// Use WebP / AVIF
<picture>
  <source srcSet="/image.avif" type="image/avif" />
  <source srcSet="/image.webp" type="image/webp" />
  <img  alt="..." />
</picture>
```

The image is optimized.

## The "lazy image" pattern

For lazy images:
```tsx
<img

  alt="..."
  loading="lazy"
  decoding="async"
  width="800"
  height="600"
/>
```

The image is lazy.

## The "memo" pattern

For memo:
```tsx
import { memo } from 'react';

const UserCard = memo(function UserCard({ user }: { user: User }) {
  return <div>{user.displayName}</div>;
});
```

The component is memo'd.

## The "useMemo" pattern

For expensive computation:
```tsx
import { useMemo } from 'react';

function SortedList({ items }: { items: Item[] }) {
  const sorted = useMemo(() => [...items].sort((a, b) => a.name.localeCompare(b.name)), [items]);
  return <ul>{sorted.map(i => <li key={i.id}>{i.name}</li>)}</ul>;
}
```

The computation is memo'd.

## The "useCallback" pattern

For stable callbacks:
```tsx
import { useCallback } from 'react';

function Parent() {
  const handleClick = useCallback((id: string) => {
    // ...
  }, []);

  return <Child onClick={handleClick} />;
}
```

The callback is stable.

## The "virtualization" pattern

For long lists, use virtualization:
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
      <div style={{ height: `${virtualizer.getTotalSize()}px` }}>
        {virtualizer.getVirtualItems().map(v => (
          <div key={v.key} style={{ transform: `translateY(${v.start}px)` }}>
            {items[v.index].name}
          </div>
        ))}
      </div>
    </div>
  );
}
```

The list is virtualized.

**Source:** TanStack Virtual:
https://tanstack.com/virtual

## The "service worker" pattern

For offline + PWA:
```ts
// sw.ts
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open('v1').then(cache => {
      return cache.addAll(['/', '/styles.css', '/app.js']);
    }),
  );
});

self.addEventListener('fetch', (event) => {
  event.respondWith(
    caches.match(event.request).then(cached => cached ?? fetch(event.request)),
  );
});
```

The SW caches + serves.

## The "accessibility" pattern

For a11y, ARIA + semantic:
```tsx
function Modal({ isOpen, onClose, children }: ModalProps) {
  return (
    <div role="dialog" aria-modal="true" aria-labelledby="modal-title">
      <h2 id="modal-title">Modal Title</h2>
      {children}
      <button onClick={onClose} aria-label="Close modal">X</button>
    </div>
  );
}
```

The modal is accessible.

## The "prefetch" pattern

For prefetch:
```tsx
import { Link } from 'react-router-dom';

<Link to="/dashboard" prefetch="intent">Dashboard</Link>
```

The route is prefetched on hover.

## The "performance metrics" pattern

For Web Vitals:
```ts
import { onCLS, onFID, onLCP } from 'web-vitals';

onCLS(console.log);
onFID(console.log);
onLCP(console.log);
```

The metrics are measured.

**Source:** Web Vitals:
https://web.dev/vitals/

## The "frontend observability" pattern

For observability:
- **Lighthouse:** Performance + a11y
- **Web Vitals:** LCP, FID, CLS
- **Sentry:** Errors
- **Analytics:** Usage

The frontend is monitored.

## The "frontend anti-pattern" anti-patterns

### 1. No code splitting
- **Issue:** Big bundle
- **Fix:** Lazy routes

### 2. No memo
- **Issue:** Re-renders
- **Fix:** memo + useMemo + useCallback

### 3. No virtualization
- **Issue:** Long lists
- **Fix:** Virtualize

### 4. No a11y
- **Issue:** Screen reader fails
- **Fix:** ARIA + semantic

### 5. No SW
- **Issue:** Slow + no offline
- **Fix:** SW + cache

## Verification
- **Test:** Lighthouse score
- **Test:** Web Vitals
- **Test:** a11y
- **Live:** Monitoring
- **Audit:** Quarterly review

## Gotchas
- **The "no code splitting" anti-pattern.** Lazy.
- **The "no memo" anti-pattern.** Memo.
- **The "no virtualization" anti-pattern.** Virtualize.

## Related
- `feature-cookbook-frontend.md`
- `feature-cookbook-frontend-patterns.md`
- `feature-cookbook-testing-frontend.md`
- `accessibility-wcag.md`
- `accessibility-components.md`
- React: https://react.dev/
- Web Vitals: https://web.dev/vitals/
- Lighthouse: https://developer.chrome.com/docs/lighthouse/overview
