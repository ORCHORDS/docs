# React Server Components Patterns

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your React application ships a large JavaScript bundle to the browser —
including data-fetching libraries, utility functions, and component logic
that never needs interactivity. Pages feel slow on mobile devices
because the browser must download, parse, and execute megabytes of
JavaScript before the page is interactive. Server-side rendering (SSR)
helps initial load but still hydrates the entire component tree on the
client, shipping all component code twice.

## Context

React Server Components (RSC) render exclusively on the server and send
only HTML to the browser — zero JavaScript shipped for server components.
Unlike traditional SSR which renders on the server then hydrates on the
client (shipping all code twice), RSC never runs on the client at all.
In 2026, RSC is the production-standard architecture for React
applications, embedded as the default in Next.js App Router. Teams
report 30-50% smaller JavaScript bundles and improved Core Web Vitals
(LCP, INP) from adopting server-first component patterns.

## Server vs. Client Components

```
Server Component (default in Next.js App Router):
  ✓ Direct database/API access
  ✓ Zero client-side JavaScript
  ✓ Access to server-only resources (env vars, file system)
  ✗ No useState, useEffect, or event handlers
  ✗ No browser APIs (window, document)

Client Component ('use client' directive):
  ✓ useState, useEffect, event handlers
  ✓ Browser APIs
  ✓ Interactive UI (forms, modals, animations)
  ✗ Cannot import server components directly
```

### The 'use client' boundary

```tsx
// app/dashboard/page.tsx — Server Component (default)
import { db } from '@/lib/db';
import { DashboardChart } from './chart'; // Client Component

export default async function DashboardPage() {
  const metrics = await db.query('SELECT * FROM metrics');

  return (
    <div>
      <h1>Dashboard</h1>
      {/* Server-rendered, zero JS */}
      <MetricsSummary data={metrics} />
      {/* Client component — JS shipped for interactivity */}
      <DashboardChart data={metrics} />
    </div>
  );
}

function MetricsSummary({ data }) {
  return <p>Total: {data.length} metrics</p>;
}
```

```tsx
// app/dashboard/chart.tsx — Client Component
'use client';

import { useState } from 'react';

export function DashboardChart({ data }) {
  const [timeRange, setTimeRange] = useState('7d');

  return (
    <div>
      <select onChange={(e) => setTimeRange(e.target.value)}>
        <option value="7d">7 days</option>
        <option value="30d">30 days</option>
      </select>
      <Chart data={filterByRange(data, timeRange)} />
    </div>
  );
}
```

## Key patterns

### 1. Push Client Components to the leaves

```
Good: Server components compose the page, client components are leaves
  ServerPage
    ├── ServerHeader (zero JS)
    ├── ServerContent (zero JS)
    │   ├── ServerArticle (zero JS)
    │   └── ClientLikeButton (small JS)
    └── ServerFooter (zero JS)

Bad: Client component wraps everything
  ClientPage (all JS shipped)
    ├── ClientHeader
    ├── ClientContent
    └── ClientFooter
```

### 2. Server Component data fetching

```tsx
// Fetch data directly in server components — no useEffect, no SWR
async function ProductPage({ params }) {
  const product = await db.products.findUnique({
    where: { id: params.id },
  });
  const reviews = await db.reviews.findMany({
    where: { productId: params.id },
  });

  return (
    <div>
      <ProductDetails product={product} />
      <ReviewList reviews={reviews} />
      <AddReviewForm productId={params.id} /> {/* Client Component */}
    </div>
  );
}
```

### 3. Streaming with Suspense

```tsx
import { Suspense } from 'react';

export default function Page() {
  return (
    <div>
      {/* Shell renders immediately */}
      <Header />
      <Hero />

      {/* Slow data streams in when ready */}
      <Suspense fallback={<ProductsSkeleton />}>
        <Products /> {/* async server component */}
      </Suspense>

      <Suspense fallback={<ReviewsSkeleton />}>
        <Reviews /> {/* async server component */}
      </Suspense>
    </div>
  );
}
```

### 4. Server Actions (mutations)

```tsx
// app/actions.ts
'use server';

export async function createOrder(formData: FormData) {
  const items = formData.getAll('items');
  const order = await db.orders.create({ data: { items } });
  revalidatePath('/orders');
  return { orderId: order.id };
}
```

```tsx
// Client Component using Server Action
'use client';

export function OrderForm() {
  return (
    <form action={createOrder}>
      <input name="items" />
      <button type="submit">Place Order</button>
    </form>
  );
}
```

## Anti-patterns

- **Making everything 'use client'** — adding 'use client' to every
  component defeats the purpose of RSC. Only components that need
  interactivity (state, effects, event handlers) should be client
  components.
- **Passing non-serializable props to client components** — server
  components pass data to client components via props. Props must be
  serializable (no functions, no classes, no Dates). Convert to plain
  objects before passing.
- **Fetching data in client components when server is available** —
  using `useEffect` + `fetch` in a client component when the data
  could be fetched in a parent server component wastes a network
  round-trip and delays rendering.
- **Large 'use client' subtrees** — placing the 'use client' boundary
  high in the component tree forces everything below it to be client-
  rendered. Move the boundary as close to the interactive leaf as
  possible.

## Gotchas

- **Server component imports** — a client component cannot import a
  server component. But a server component can pass a server component
  as `children` to a client component (composition pattern).
- **Third-party library compatibility** — many React libraries
  (animation, state management, UI kits) use hooks and browser APIs
  internally. They must be wrapped with 'use client' or replaced with
  RSC-compatible alternatives.
- **Caching and revalidation** — Next.js caches server component
  rendering by default. Use `revalidatePath()` or `revalidateTag()`
  to invalidate cached renders after mutations.
- **Development vs. production behavior** — RSC streaming behavior
  differs between development (synchronous for debugging) and
  production (streamed). Test with production builds.

## Verification

- Default components are server components (no 'use client' directive).
- 'use client' is only on interactive leaf components.
- Data fetching happens in server components, not client-side effects.
- Suspense boundaries provide loading UI for slow server components.
- JavaScript bundle size is 30%+ smaller than pre-RSC architecture.
- Core Web Vitals (LCP, INP) meet targets.

## Related

- `documentation/categories/frontend/performance-optimization.md`
- `documentation/categories/frontend/ssr-hydration-patterns.md`
- `documentation/categories/performance/core-web-vitals.md`

## Source URLs (verified 2026-08-16)

- RSC complete 2026 guide — https://dev.to/iammuhammadarslan/react-server-components-explained-the-complete-2026-guide-1o68
- RSC patterns and pitfalls — https://jsmanifest.com/react-server-components-patterns-pitfalls-2026
- Next.js RSC and Server Actions — https://medium.com/@Samira8872/next-js-in-2026-exploring-react-server-components-rsc-and-server-actions-in-depth-60f0478830af
- RSC guide (ZAX) — https://z-ax.com/en/blog/react-server-components-complete-guide-2026/
