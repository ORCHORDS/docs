# React 19 Server Components — Streaming SSR, Suspense, use() Hook, and Server Actions

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your React SPA ships a 340KB JavaScript bundle. First Contentful
Paint is 2.1 seconds on 3G networks. Every component fetches data
client-side with `useEffect`, causing waterfall requests — the
header fetches user data, then the sidebar fetches navigation, then
the main content fetches products. Users see three loading spinners
in sequence. Meanwhile, your SEO-critical product pages are not
indexed because the crawler does not execute JavaScript.

## Context

React 19 Server Components (RSC) shift rendering to the server by
default, sending HTML and a streaming RSC payload instead of
JavaScript. Client Components (marked with `"use client"`) are the
opt-in for interactivity. Streaming SSR with Suspense shows ready
content immediately while slower parts stream in progressively.
The `use()` hook reads promises mid-render without useEffect
boilerplate. Server Actions (`"use server"`) handle mutations
without manual API routes. Production benchmarks show JS bundle
reductions of 74% (340KB to 89KB), FCP improvements from 2.1s to
0.8s on 3G, and TTFB drops from 450ms to 45ms.

## Server Components vs Client Components

```
Decision tree — default to Server Components:

  Need event handlers (onClick, onChange)?     → Client Component
  Need useState, useEffect, useReducer?        → Client Component
  Need browser-only APIs (window, localStorage)? → Client Component
  Need React Context (useContext)?             → Client Component
  Need third-party state (Redux, Zustand)?     → Client Component
  None of the above?                           → Server Component

  Server Components:
    → No JavaScript shipped to client
    → Direct database/filesystem access
    → Async by default (can await in render)
    → Cannot use hooks, event handlers, or browser APIs

  Client Components:
    → "use client" directive at top of file
    → Full React hook and event handler support
    → Hydrated on the client for interactivity
```

## Streaming SSR with Suspense

```jsx
// app/page.tsx — Server Component (default)
import { Suspense } from 'react';
import { Header } from './Header';
import { ProductList } from './ProductList';
import { Recommendations } from './Recommendations';

export default function Page() {
  return (
    <>
      <Header />
      <Suspense fallback={<ProductSkeleton />}>
        <ProductList />
      </Suspense>
      <Suspense fallback={<RecommendationSkeleton />}>
        <Recommendations />
      </Suspense>
    </>
  );
}

// ProductList and Recommendations are async Server Components.
// They fetch data independently and in parallel.
// Each streams to the client as soon as its data is ready.
// Header renders immediately (no data dependency).
```

```
Streaming flow:

  1. Server renders Header → sends HTML immediately
  2. ProductList starts async data fetch
  3. Recommendations starts async data fetch (parallel)
  4. ProductList resolves → streams HTML chunk to client
  5. Recommendations resolves → streams HTML chunk
  6. Client progressively replaces skeletons with content

  Result: fast initial paint, progressive content reveal.
  No waterfall. No blocking on slowest component.
```

## use() hook for data fetching

```jsx
// use() reads a promise mid-render — must be inside Suspense
'use client';
import { use } from 'react';

function Comments({ commentsPromise }) {
  const comments = use(commentsPromise);
  return (
    <ul>
      {comments.map(c => <li key={c.id}>{c.text}</li>)}
    </ul>
  );
}

// Parent passes the promise (starts fetch early)
<Suspense fallback={<CommentSkeleton />}>
  <Comments commentsPromise={fetchComments(postId)} />
</Suspense>
```

```
use() vs useEffect for data fetching:

  use()                           useEffect + useState
  ──────────────────────────────────────────────────────
  Suspends render until ready     Shows empty → loading → data
  No loading state management     Manual isLoading/error state
  Works in Server Components      Client Components only
  Must be inside Suspense         No Suspense requirement
  Throws on rejection             Manual error handling
```

## Server Actions

```jsx
// app/actions.ts
'use server';

export async function createOrder(formData: FormData) {
  const product = formData.get('product');
  const quantity = Number(formData.get('quantity'));
  await db.orders.create({ product, quantity });
  revalidatePath('/orders');
}

// app/OrderForm.tsx
'use client';
import { useActionState } from 'react';
import { createOrder } from './actions';

export function OrderForm() {
  const [state, action, isPending] = useActionState(createOrder, null);
  return (
    <form action={action}>
      <input name="product" required />
      <input name="quantity" type="number" required />
      <button disabled={isPending}>
        {isPending ? 'Ordering...' : 'Place Order'}
      </button>
    </form>
  );
}
```

## RSC payload and selective hydration

```
RSC payload format:

  Server Components render to a streaming RSC payload (not HTML).
  Client component boundaries are replaced with module references
  plus serialized props. The payload streams in chunks that React
  starts processing before the full response arrives.

Selective hydration:

  React 19 makes hydration non-monolithic:
  → Pure Server Components skip hydration entirely (no JS)
  → Client Components hydrate selectively and progressively
  → Priority: interactive elements hydrate first
  → User interaction during hydration triggers priority boost

Performance benchmarks:
  JS bundle:  340KB → 89KB (-74%)
  FCP (3G):   2.1s → 0.8s
  TTFB:       450ms → 45ms
  LCP:        1.2s → 380ms
```

## Anti-patterns

- **Overusing `"use client"` at high tree levels** — adding the
  directive to a layout or page component collapses the server-first
  advantage. Push `"use client"` to the leaf components that
  actually need interactivity.
- **Single Suspense boundary for entire page** — defeats streaming.
  Each independent data-fetching component should have its own
  Suspense boundary so fast parts are not blocked by slow ones.
- **Client-side data fetching in Server Components** — Server
  Components can access databases and filesystems directly. Using
  `useEffect` + `fetch` in a Server Component is not possible and
  indicates the wrong component type.
- **Passing non-serializable props across the boundary** —
  functions, class instances, and Symbols cannot cross from Server
  to Client Components. Only JSON-serializable data is allowed.

## Gotchas

- **Server Components cannot consume React Context** — Context is
  a client runtime concept. Global state libraries (Redux, Zustand)
  do not work in pure RSC trees. Use URL search params for
  server-side state or pass data as props.
- **use() must be inside Suspense** — React throws if `use()` is
  called outside a Suspense boundary. Always wrap components using
  `use()` in a Suspense boundary with a fallback.
- **Server Actions security** — `"use server"` creates implicit
  network boundaries (server-callable functions). Validate all
  inputs server-side — the function is exposed as an HTTP endpoint
  and can be called by anyone.
- **Third-party library compatibility** — many libraries assume
  client-side rendering. Check that dependencies work with RSC
  before adopting. Libraries using `useEffect`, `window`, or
  `document` at module scope will fail in Server Components.

## Verification

- Default to Server Components; `"use client"` only on interactive leaves.
- Each async data-fetching component wrapped in its own Suspense boundary.
- Server Actions validate all inputs server-side.
- No non-serializable props passed across server/client boundary.
- Bundle size measured and compared to pre-RSC baseline.
- Streaming SSR verified with throttled network conditions.

## Related

- `documentation/docs/policies/frontend/web-components-shadow-dom-custom-elements.md`
- `documentation/docs/policies/performance/critical-rendering-path-css-optimization.md`
- `documentation/docs/policies/frontend/css-container-queries-has-selector.md`

## Source URLs (verified 2026-08-16)

- React 19 Server Components: Production Patterns — https://dev.to/vikrant_bagal_afae3e25ca7/react-19-server-components-production-patterns-for-high-performance-apps-in-2026-3278
- React Server Components Streaming Performance Guide — https://www.sitepoint.com/react-server-components-streaming-performance-2026/
- React 19 Complete Guide: Actions, use() Hook, Server Components — https://zeonedge.com/blog/react-19-complete-guide-actions-use-hook-server-components-compiler
- React Server Components in Production: Benefits, Pitfalls — https://www.growin.com/blog/react-server-components/
