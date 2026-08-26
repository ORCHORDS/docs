# HTMX with Cloudflare Workers for Hypermedia-Driven UIs

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You want a fast, server-rendered UI without a JavaScript framework. The server owns all state; the browser only requests and swaps HTML fragments. Cloudflare Workers provide a globally distributed runtime that renders HTML at the edge and reads/writes from D1, eliminating a cold-start penalty.

## Context

HTMX extends HTML with attributes (`hx-get`, `hx-post`, `hx-swap`, `hx-target`) that trigger XHR requests and patch the DOM with the returned HTML fragment. The Workers endpoint returns `Content-Type: text/html`—not JSON. D1 is the persistence layer. `hx-push-url` keeps the browser URL in sync with the current view without a client-side router.

## Workers Endpoint Returning HTML Fragments

```typescript
// workers/src/index.ts
import { Env } from './types';
import { renderItemList, renderItemRow, renderError } from './templates';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const method = request.method;

    // GET /items — full list fragment
    if (method === 'GET' && url.pathname === '/items') {
      const { results } = await env.DB.prepare(
        'SELECT id, name, created_at FROM items ORDER BY created_at DESC'
      ).all<{ id: string; name: string; created_at: string }>();

      return new Response(renderItemList(results), {
        headers: { 'Content-Type': 'text/html; charset=utf-8' },
      });
    }

    // POST /items — create and return the new row only
    if (method === 'POST' && url.pathname === '/items') {
      const form = await request.formData();
      const name = (form.get('name') as string)?.trim();

      if (!name || name.length < 2) {
        return new Response(renderError('Name must be at least 2 characters'), {
          status: 422,
          headers: { 'Content-Type': 'text/html; charset=utf-8' },
        });
      }

      const id = crypto.randomUUID();
      const createdAt = new Date().toISOString();
      await env.DB.prepare(
        `INSERT INTO items (id, name, created_at) VALUES (?, ?, ?)`
      )
        .bind(id, name, createdAt)
        .run();

      return new Response(renderItemRow({ id, name, created_at: createdAt }), {
        headers: { 'Content-Type': 'text/html; charset=utf-8' },
      });
    }

    // DELETE /items/:id — return empty string to remove the row
    const deleteMatch = url.pathname.match(/^\/items\/([\w-]+)$/);
    if (method === 'DELETE' && deleteMatch) {
      const id = deleteMatch[1];
      await env.DB.prepare('DELETE FROM items WHERE id = ?').bind(id).run();
      // Returning empty body removes the element when hx-swap="outerHTML"
      return new Response('', {
        headers: { 'Content-Type': 'text/html; charset=utf-8' },
      });
    }

    return new Response('Not Found', { status: 404 });
  },
};
```

```typescript
// workers/src/templates.ts
interface Item {
  id: string;
  name: string;
  created_at: string;
}

export function renderItemRow(item: Item): string {
  return `
<li id="item-${item.id}" class="item-row">
  <span>${escapeHtml(item.name)}</span>
  <span class="ts">${item.created_at}</span>
  <button
    hx-delete="/items/${item.id}"
    hx-target="#item-${item.id}"
    hx-swap="outerHTML"
    hx-confirm="Delete this item?"
  >Delete</button>
</li>`.trim();
}

export function renderItemList(items: Item[]): string {
  return `<ul id="item-list">${items.map(renderItemRow).join('')}</ul>`;
}

export function renderError(message: string): string {
  return `<p class="form-error" role="alert">${escapeHtml(message)}</p>`;
}

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
```

## HTML Page with HTMX Attributes

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Items</title>
  <script src="https://unpkg.com/htmx.org@2.0.0" defer></script>
</head>
<body>
  <h1>Items</h1>

  <!-- Load the list on page load via hx-trigger="load" -->
  <div
    hx-get="/items"
    hx-trigger="load"
    hx-target="#list-container"
    hx-swap="innerHTML"
    hx-push-url="/items"
  >
    <p>Loading…</p>
  </div>
  <div id="list-container"></div>

  <!-- Form: hx-post sends multipart/form-data; the response row is prepended -->
  <form
    hx-post="/items"
    hx-target="#item-list"
    hx-swap="afterbegin"
    hx-on::after-request="this.reset()"
  >
    <input name="name" placeholder="Item name" required />
    <button type="submit">Add</button>
    <!-- Validation errors are swapped into #form-error by the 422 response -->
    <div id="form-error" hx-swap-oob="true"></div>
  </form>
</body>
</html>
```

## hx-swap Strategies and hx-push-url

| Scenario | `hx-swap` value | Effect |
|---|---|---|
| Replace entire list | `outerHTML` | Swaps the `<ul>` itself |
| Remove a row | `outerHTML` (empty response) | Removes the `<li>` from the DOM |
| Prepend new row | `afterbegin` | Inserts before first child |
| Replace error slot | `innerHTML` | Updates just the error text |

`hx-push-url="/items"` updates `window.location` and creates a history entry so the browser back button works without client-side routing code.

## Keeping All State Server-Side

No Zustand, Redux, or React context. The D1 database is the single source of truth. Each HTMX request fetches fresh state. For real-time updates (e.g., multi-user lists), combine with Server-Sent Events via `hx-ext="sse"` pointed at a Workers SSE endpoint.

## Anti-patterns

- Returning JSON from a Workers endpoint targeted by `hx-get`—HTMX inserts JSON as raw text, not rendered HTML.
- Forgetting `escapeHtml` in templates—renders XSS vulnerabilities when item names contain `<script>` tags.
- Using `hx-swap="innerHTML"` on a `<ul>` when you want to remove individual rows—swap the `<li>` with `outerHTML` instead.
- Nesting `hx-*` attributes on both a parent and a child without understanding event bubbling—requests can fire twice.

## Gotchas

- HTMX 2.x removed `hx-on:` shorthand for custom events; use `hx-on::after-request` (double colon) for lifecycle hooks.
- `hx-confirm` shows a native browser `confirm()` dialog—it blocks the thread. For custom dialogs, use `htmx:confirm` event interception.
- Cloudflare Workers have a 128 MB memory limit; keep template rendering lean and avoid buffering large D1 result sets in memory.
- Workers do not support `EventSource` (SSE) out of the box on free plans—check Durable Objects for fan-out.

## Verification

```bash
# Start local Workers dev server
npx wrangler dev --local --d1=DB

# In another tab: seed D1
npx wrangler d1 execute DB --local --command \
  "INSERT INTO items (id,name,created_at) VALUES ('abc','Test item',datetime('now'))"

# Open http://localhost:8787 — list should load immediately
# Submit a new item — it should prepend without a full page reload
# Click Delete — the row should disappear via outerHTML swap
```

## Related

- `tanstack-query-workers-optimistic-mutations.md`
- `nextjs-app-router-cloudflare-pages-adapter.md`

## Sources

- https://htmx.org/docs/
- https://developers.cloudflare.com/workers/
- https://developers.cloudflare.com/d1/
- https://htmx.org/attributes/hx-push-url/
