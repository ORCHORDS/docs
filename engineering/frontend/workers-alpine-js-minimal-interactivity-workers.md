# Alpine.js + Workers: No-Build Interactive HTML with KV State

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You want rich client-side interactivity on a Workers-served HTML page without any build pipeline. Alpine.js is the lightest way to add declarative reactivity to server-rendered markup. Combined with `HTMLRewriter` on the Worker side to inject `x-data` attributes and a KV-backed JSON endpoint for persistent state, you get a full interactive experience with zero npm build steps.

## Context

- Cloudflare Workers (ESM module format)
- Alpine.js 3.x (loaded via CDN script tag — only external CDN allowed in Workers HTML responses)
- `HTMLRewriter` for server-side attribute injection
- KV namespace `STATE_KV` for server-side state persistence
- No Vite, no webpack, no npm build
- Wrangler v3, TypeScript 5.x

---

## Section 1 — Worker structure and HTML template

```typescript
// src/index.ts
export interface Env {
  STATE_KV: KVNamespace;
  ASSETS: Fetcher; // optional: serve static files from R2 or Pages
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    // Route to JSON API
    if (url.pathname.startsWith('/api/')) {
      return handleApi(request, env, ctx);
    }

    // Serve the base HTML page
    const baseHtml = buildPage();

    // Use HTMLRewriter to inject server state into Alpine x-data attributes
    const userId = getUserId(request); // from signed cookie
    const stateKey = `user:${userId}:ui-state`;
    const savedState = await env.STATE_KV.get(stateKey, 'json') as Record<string, unknown> | null;

    const initialState = JSON.stringify({
      count: 0,
      theme: 'light',
      notifications: [],
      ...savedState, // merge server-saved state
    });

    // HTMLRewriter injects the server state before the page reaches the client
    const rewriter = new HTMLRewriter()
      .on('#app', new AlpineDataInjector(initialState))
      .on('html', new ThemeClassInjector(savedState?.theme as string));

    return rewriter.transform(
      new Response(baseHtml, { headers: { 'Content-Type': 'text/html; charset=utf-8' } })
    );
  },
};

class AlpineDataInjector implements HTMLRewriterElementContentHandlers {
  constructor(private state: string) {}

  element(el: Element) {
    // Safe JSON injection — state is server-controlled, not user input
    el.setAttribute('x-data', this.state);
    el.setAttribute('x-init', 'initApp()');
  }
}

class ThemeClassInjector implements HTMLRewriterElementContentHandlers {
  constructor(private theme: string | undefined) {}

  element(el: Element) {
    if (this.theme === 'dark') {
      el.setAttribute('class', 'dark');
    }
  }
}

function getUserId(request: Request): string {
  // Simplified — use a signed cookie library in production
  const cookie = request.headers.get('Cookie') ?? '';
  const match = cookie.match(/uid=([a-zA-Z0-9-]+)/);
  return match?.[1] ?? 'anonymous';
}
```

---

## Section 2 — Base HTML with Alpine.js

```typescript
// src/template.ts
export function buildPage(): string {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Alpine + Workers Demo</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; }
    body { font-family: system-ui, sans-serif; margin: 0; padding: 1rem 2rem; }
    .dark body { background: #1a1a1a; color: #e5e5e5; }
    .card { border: 1px solid #e2e8f0; border-radius: 8px; padding: 1rem; margin-bottom: 1rem; }
    .dark .card { border-color: #3a3a3a; background: #2a2a2a; }
    button { padding: 0.4rem 0.8rem; border-radius: 4px; border: 1px solid #ccc; cursor: pointer; }
    [x-cloak] { display: none !important; }
  </style>
</head>
<body>
  <!--
    #app gets x-data injected by HTMLRewriter before the response
    reaches the browser — no flash of unhydrated content.
  -->
  <div id="app">
    <div class="card">
      <h2>Counter</h2>
      <p>Value: <strong x-text="count"></strong></p>
      <button @click="count++; saveState()">+</button>
      <button @click="count = Math.max(0, count - 1); saveState()">−</button>
      <button @click="count = 0; saveState()">Reset</button>
    </div>

    <div class="card">
      <h2>Theme</h2>
      <button @click="toggleTheme()">
        <span x-text="theme === 'dark' ? 'Switch to light' : 'Switch to dark'"></span>
      </button>
    </div>

    <div class="card" x-cloak>
      <h2>Notifications</h2>
      <ul>
        <template x-for="n in notifications" :key="n.id">
          <li x-text="n.message"></li>
        </template>
      </ul>
      <button @click="fetchNotifications()">Refresh</button>
    </div>
  </div>

  <!-- Alpine.js 3 — loaded from CDN (only external allowed in Workers HTML) -->
  <script defer src="https://unpkg.com/alpinejs@3.x.x/dist/cdn.min.js"></script>
  <script>
    function initApp() {
      // 'this' is the Alpine component data object
    }

    // Called from Alpine via @click — saves state to Workers KV via API
    async function saveState() {
      const el = document.getElementById('app');
      const state = Alpine.raw(Alpine.$data(el));
      await fetch('/api/state', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ count: state.count, theme: state.theme }),
      });
    }

    // Toggle and persist theme
    function toggleTheme() {
      const el = document.getElementById('app');
      const data = Alpine.$data(el);
      data.theme = data.theme === 'dark' ? 'light' : 'dark';
      document.documentElement.classList.toggle('dark', data.theme === 'dark');
      saveState();
    }

    // Fetch notifications from Workers API
    async function fetchNotifications() {
      const res = await fetch('/api/notifications');
      const data = await res.json();
      const el = document.getElementById('app');
      Alpine.$data(el).notifications = data.notifications;
    }
  </script>
</body>
</html>`;
}
```

---

## Section 3 — KV-backed state API endpoint

```typescript
// src/api.ts
import type { Env } from './index';

export async function handleApi(
  request: Request,
  env: Env,
  ctx: ExecutionContext
): Promise<Response> {
  const url = new URL(request.url);

  if (url.pathname === '/api/state') {
    return handleState(request, env, ctx);
  }

  if (url.pathname === '/api/notifications') {
    return handleNotifications(request, env);
  }

  return new Response('Not found', { status: 404 });
}

async function handleState(
  request: Request,
  env: Env,
  ctx: ExecutionContext
): Promise<Response> {
  const userId = getUserId(request);
  const stateKey = `user:${userId}:ui-state`;

  if (request.method === 'GET') {
    const state = await env.STATE_KV.get(stateKey, 'json');
    return Response.json(state ?? { count: 0, theme: 'light' });
  }

  if (request.method === 'PUT') {
    const body = await request.json<{ count: number; theme: string }>();

    // Validate inputs before writing to KV
    if (typeof body.count !== 'number' || !['light', 'dark'].includes(body.theme)) {
      return Response.json({ error: 'Invalid state' }, { status: 400 });
    }

    // Use waitUntil so the response returns immediately
    ctx.waitUntil(
      env.STATE_KV.put(stateKey, JSON.stringify(body), {
        expirationTtl: 60 * 60 * 24 * 30, // 30 days
      })
    );

    return Response.json({ ok: true });
  }

  return new Response('Method not allowed', { status: 405 });
}

async function handleNotifications(
  request: Request,
  env: Env
): Promise<Response> {
  const userId = getUserId(request);
  const key = `user:${userId}:notifications`;
  const raw = await env.STATE_KV.get(key, 'json') as Array<{ id: string; message: string }> | null;

  return Response.json(
    { notifications: raw ?? [] },
    { headers: { 'Cache-Control': 'no-store' } }
  );
}

function getUserId(request: Request): string {
  const cookie = request.headers.get('Cookie') ?? '';
  const match = cookie.match(/uid=([a-zA-Z0-9-]+)/);
  return match?.[1] ?? 'anonymous';
}
```

---

## Section 4 — Wrangler config and deployment

```toml
# wrangler.toml
name = "alpine-workers-demo"
main = "src/index.ts"
compatibility_date = "2025-08-01"

[[kv_namespaces]]
binding = "STATE_KV"
id = "yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy"

[[kv_namespaces]]
binding = "STATE_KV"
id = "zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz"
preview_id = "zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz"
```

```bash
# Build (just TypeScript compile — no bundler needed for this Worker)
npx tsc --noEmit

# Dev
wrangler dev

# Deploy
wrangler deploy
```

---

## Anti-patterns

- Do not inject raw user input into `x-data` via `HTMLRewriter` — always sanitise or use server-controlled defaults only.
- Do not store sensitive data (tokens, PII) in KV with `expirationTtl` only — KV is eventually consistent; use a session token pattern for auth.
- Do not call `saveState()` on every keystroke — debounce writes to avoid KV rate limits.
- Do not use `Alpine.store()` for data you also persist to the server — keep a single source of truth.
- Do not assume `Alpine.$data()` is synchronously available on DOMContentLoaded — wrap in `Alpine.nextTick()` if needed.

## Gotchas

- `HTMLRewriter` `.on('#app', handler)` matches by CSS selector; it fires for each matching element and is streaming — the handler cannot `await` async operations. Fetch KV data before calling `.transform()`.
- Alpine `x-data` must be valid JSON (for server injection) or a JavaScript expression. JSON.stringify produces valid JSON so use it for state passed via `HTMLRewriter`.
- The `https://unpkg.com` CDN URL is allowed from a Worker HTML response (CSP permitting) because it is the client's browser making the request, not the Worker.
- KV writes via `waitUntil` return to the client immediately; if the write fails, the client won't know. Add error logging via `console.error`.
- Alpine 3 `x-cloak` hides elements until Alpine initialises — always add it to sections that depend on hydration to prevent layout flash.

## Verification

```bash
# Start local dev
wrangler dev

# Verify HTMLRewriter injected the attribute
curl -s http://localhost:8787/ | grep 'x-data'

# Test state save
curl -X PUT http://localhost:8787/api/state \
  -H 'Content-Type: application/json' \
  -d '{"count": 5, "theme": "dark"}'

# Verify state persisted
curl http://localhost:8787/api/state

# Deploy and verify production
wrangler deploy
curl -s https://alpine-workers-demo.workers.dev/ | grep 'x-data'
```

## Related

- `documentation/backend/htmlrewriter-streaming-transforms.md`
- `documentation/backend/kv-session-storage-patterns.md`
- `documentation/categories/frontend/workers-service-worker-offline-cache-strategy.md`

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/
- https://developers.cloudflare.com/kv/
- https://alpinejs.dev/directives/data
- https://alpinejs.dev/magics/data
