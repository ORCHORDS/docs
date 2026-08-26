# React 19 `use()` API with Suspense for Data Fetching in Cloudflare Workers SSR

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

You are building a server-side rendered React 19 application on Cloudflare Workers and want to stream
data-driven UI without waterfalls. The new `use(promise)` API lets you unwrap promises directly inside
render, but coordinating it with Workers' streaming response and Hono's middleware requires care.

## Context

React 19 formalises `use()` as a first-class hook that can suspend a component by accepting a Promise or
Context object. On Cloudflare Workers, `renderToPipeableStream` is unavailable — you must use
`renderToReadableStream` from `react-dom/server.edge`, which returns a Web-standard `ReadableStream`
that maps directly onto Workers' `Response`. Hono is the most common routing layer in this environment
and provides request context injection that feeds data promises to your component tree.

## Setting Up `renderToReadableStream` with Hono

Wire Hono to render React 19 components as a streaming Workers response. Pass promises created during
the request lifecycle into the component tree via context so `use()` can suspend against them.

```typescript
// src/index.tsx
import { Hono } from 'hono';
import { renderToReadableStream } from 'react-dom/server.edge';
import { createElement } from 'react';
import { App } from './App';

type Bindings = { DB: D1Database; KV: KVNamespace };

const app = new Hono<{ Bindings: Bindings }>();

app.get('*', async (c) => {
  // Create promise BEFORE render — do NOT await it.
  const userPromise = c.env.DB
    .prepare('SELECT id, name, email FROM users WHERE id = ?1')
    .bind(c.req.param('id') ?? '1')
    .first<{ id: string; name: string; email: string }>();

  const stream = await renderToReadableStream(
    createElement(App, { userPromise }),
    {
      bootstrapScripts: ['/client.js'],
      onError(error) {
        console.error('RSC/SSR error', error);
      },
    }
  );

  return new Response(stream, {
    headers: {
      'Content-Type': 'text/html; charset=utf-8',
      'Transfer-Encoding': 'chunked',
    },
  });
});

export default app;
```

## Using `use()` Inside Components

Components call `use(promise)` to unwrap the value. React suspends the component until the promise
resolves. Wrap the suspending subtree in `<Suspense>` with a meaningful fallback; wrap the error path
in an `ErrorBoundary`.

```typescript
// src/App.tsx
import React, { use, Suspense } from 'react';
import { ErrorBoundary } from 'react-error-boundary';

interface User { id: string; name: string; email: string }

function UserCard({ userPromise }: { userPromise: Promise<User | null> }) {
  // Suspends here until userPromise resolves.
  const user = use(userPromise);
  if (!user) return <p>User not found.</p>;
  return (
    <article>
      <h1>{user.name}</h1>
      <p>{user.email}</p>
    </article>
  );
}

function UserCardSkeleton() {
  return (
    <article aria-busy="true">
      <div className="skeleton h-6 w-48" />
      <div className="skeleton h-4 w-64 mt-2" />
    </article>
  );
}

export function App({ userPromise }: { userPromise: Promise<User | null> }) {
  return (
    <html lang="en">
      <head><meta charSet="utf-8" /><title>Workers SSR</title></head>
      <body>
        <ErrorBoundary fallback={<p>Something went wrong.</p>}>
          <Suspense fallback={<UserCardSkeleton />}>
            <UserCard userPromise={userPromise} />
          </Suspense>
        </ErrorBoundary>
      </body>
    </html>
  );
}
```

## Parallel Data Fetching Without Waterfalls

Create all promises before entering the render tree so React can stream each Suspense boundary as its
promise resolves independently rather than sequentially.

```typescript
// src/index.tsx — parallel promise creation
app.get('/dashboard', async (c) => {
  const db = c.env.DB;

  // All three queries fire simultaneously — no await chains.
  const userPromise    = db.prepare('SELECT * FROM users WHERE id = ?1').bind('1').first();
  const ordersPromise  = db.prepare('SELECT * FROM orders WHERE user_id = ?1 LIMIT 10').bind('1').all();
  const settingsPromise = c.env.KV.get('settings:global', 'json');

  const stream = await renderToReadableStream(
    createElement(Dashboard, { userPromise, ordersPromise, settingsPromise }),
    { bootstrapScripts: ['/client.js'] }
  );

  return new Response(stream, {
    headers: { 'Content-Type': 'text/html; charset=utf-8' },
  });
});
```

```typescript
// src/Dashboard.tsx — each section suspends independently
import React, { use, Suspense } from 'react';
import { ErrorBoundary } from 'react-error-boundary';

export function Dashboard({ userPromise, ordersPromise, settingsPromise }: DashboardProps) {
  return (
    <main>
      <ErrorBoundary fallback={<p>Failed to load user.</p>}>
        <Suspense fallback={<p>Loading user…</p>}>
          <UserSection userPromise={userPromise} />
        </Suspense>
      </ErrorBoundary>

      <ErrorBoundary fallback={<p>Failed to load orders.</p>}>
        <Suspense fallback={<p>Loading orders…</p>}>
          <OrdersSection ordersPromise={ordersPromise} />
        </Suspense>
      </ErrorBoundary>

      <ErrorBoundary fallback={<p>Failed to load settings.</p>}>
        <Suspense fallback={<p>Loading settings…</p>}>
          <SettingsSection settingsPromise={settingsPromise} />
        </Suspense>
      </ErrorBoundary>
    </main>
  );
}
```

## Error Boundaries with React 19

React 19 error boundaries receive a `reset` function as part of the fallback render props via
`react-error-boundary`. On the Workers side, any uncaught promise rejection propagates through the
`onError` callback passed to `renderToReadableStream`.

```typescript
// src/boundaries.tsx
import { ErrorBoundary, FallbackProps } from 'react-error-boundary';

function ApiErrorFallback({ error, resetErrorBoundary }: FallbackProps) {
  const isNotFound = error?.message?.includes('not found');
  return (
    <div role="alert">
      <p>{isNotFound ? 'Resource not found.' : 'An unexpected error occurred.'}</p>
      <button onClick={resetErrorBoundary}>Retry</button>
    </div>
  );
}

export function SafeSection({ children }: { children: React.ReactNode }) {
  return (
    <ErrorBoundary FallbackComponent={ApiErrorFallback}>
      {children}
    </ErrorBoundary>
  );
}
```

## Anti-patterns

- Awaiting promises before passing them to components — this negates streaming and creates a waterfall.
- Creating promises inside the component body — each render invocation fires a new request.
- Using `use()` outside a `<Suspense>` boundary — the component suspends indefinitely without a fallback.
- Relying on `renderToPipeableStream` — it is Node.js-only; Workers require `renderToReadableStream`.

## Gotchas

- `renderToReadableStream` resolves after all Suspense boundaries with `bootstrapScripts` are flushed;
  early `stream.allReady` awaiting blocks streaming — consume the stream directly without awaiting it.
- Cloudflare Workers have a 30-second CPU limit; long-pending promises can cause the Worker to be killed
  mid-stream. Add a `Promise.race` with a timeout and reject to trigger the ErrorBoundary instead.

## Verification

```bash
# Deploy and measure streaming with curl
wrangler dev --port 8787

# Confirm chunks arrive progressively (should see HTML before promise resolves)
curl -N --http1.1 http://localhost:8787/dashboard

# Run unit tests with Vitest + miniflare environment
npx vitest run --reporter=verbose
```

## Related

- `frontend/streaming-html-workers-react-rendertopipeablestream.md`
- `frontend/react-19-server-components-streaming-ssr.md`
- `frontend/react-suspense-cloudflare-pages-ssr-edge.md`

## Sources

- https://developers.cloudflare.com/workers/frameworks/framework-guides/react/
- https://react.dev/reference/react/use
- https://react.dev/reference/react-dom/server/renderToReadableStream
- https://hono.dev/docs/getting-started/cloudflare-workers
