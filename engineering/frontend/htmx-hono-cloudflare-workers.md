# HTMX + Hono on Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case
You want server-driven UI with minimal JavaScript — swapping DOM fragments over HTTP without a full SPA framework — while keeping all logic at the edge on Cloudflare Workers.

## Context
HTMX lets HTML attributes drive Ajax, WebSocket, and SSE requests, returning HTML partials instead of JSON. Paired with Hono's fast JSX renderer on Cloudflare Workers, the entire request/response cycle stays at the edge with zero cold-start penalty. No client-side router, no hydration mismatch, no bundle size regression — just hypermedia.

## Setup — wrangler + Hono

```toml
# wrangler.toml
name = "htmx-hono-app"
main = "src/index.tsx"
compatibility_date = "2026-08-01"
compatibility_flags = ["nodejs_compat"]

[vars]
ENVIRONMENT = "production"
```

```json
// package.json (relevant deps)
{
  "dependencies": {
    "hono": "^4.7.0"
  },
  "devDependencies": {
    "@cloudflare/workers-types": "^4.20260801.0",
    "wrangler": "^4.0.0"
  }
}
```

## Base Layout with HTMX CDN Script

```tsx
// src/layout.tsx
import { html } from 'hono/html'

export const Layout = ({ title, children }: { title: string; children: any }) => html`
  <!doctype html>
  <html lang="en">
    <head>
      <meta charset="UTF-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1.0" />
      <title>${title}</title>
      <!-- pin to a specific version; workers serve the same hash forever -->
      <script
        src="https://unpkg.com/htmx.org@2.0.4/dist/htmx.min.js"
        integrity="sha384-HGfztofotfshcF7+8n44JQL2oJmowVChPTg48S+jvZoztPfvwD79OC/LTtG6dMp+"
        crossorigin="anonymous"
        defer
      ></script>
      <script src="https://unpkg.com/htmx-ext-response-targets@2.0.2/response-targets.js" defer></script>
    </head>
    <body hx-ext="response-targets">
      ${children}
    </body>
  </html>
`
```

## Hono App — Full and Partial Route Pattern

```tsx
// src/index.tsx
import { Hono } from 'hono'
import { jsxRenderer, useRequestContext } from 'hono/jsx-renderer'
import { Layout } from './layout'

type Env = { Bindings: { DB: D1Database } }

const app = new Hono<Env>()

// Helper: detect HTMX request and return partial vs full page
function isHtmx(c: Parameters<Parameters<typeof app.get>[1]>[0]) {
  return c.req.header('HX-Request') === 'true'
}

// --- Full page ---
app.get('/', (c) => {
  const page = (
    <Layout title="Tasks">
      <h1>Tasks</h1>
      <div id="task-list">
        <TaskList tasks={[]} />
      </div>
      <form
        hx-post="/tasks"
        hx-target="#task-list"
        hx-swap="outerHTML"
        hx-on--after-request="this.reset()"
      >
        <input name="title" placeholder="New task…" required />
        <button type="submit">Add</button>
      </form>
    </Layout>
  )
  return c.html(page)
})

// --- Partial: list ---
app.get('/tasks', async (c) => {
  const { results } = await c.env.DB.prepare(
    'SELECT id, title, done FROM tasks ORDER BY id DESC LIMIT 50'
  ).all<{ id: number; title: string; done: number }>()

  const partial = <TaskList tasks={results} />
  return isHtmx(c)
    ? c.html(partial)
    : c.html(<Layout title="Tasks">{partial}</Layout>)
})

// --- Partial: create ---
app.post('/tasks', async (c) => {
  const body = await c.req.formData()
  const title = (body.get('title') as string | null)?.trim()
  if (!title) return c.html(<p id="task-list">Title required.</p>, 422)

  await c.env.DB.prepare('INSERT INTO tasks (title, done) VALUES (?, 0)').bind(title).run()

  const { results } = await c.env.DB.prepare(
    'SELECT id, title, done FROM tasks ORDER BY id DESC LIMIT 50'
  ).all<{ id: number; title: string; done: number }>()

  return c.html(<TaskList tasks={results} />)
})

// --- Partial: toggle done ---
app.put('/tasks/:id/toggle', async (c) => {
  const id = Number(c.req.param('id'))
  await c.env.DB.prepare('UPDATE tasks SET done = NOT done WHERE id = ?').bind(id).run()
  const row = await c.env.DB.prepare('SELECT id, title, done FROM tasks WHERE id = ?')
    .bind(id)
    .first<{ id: number; title: string; done: number }>()
  if (!row) return c.notFound()
  return c.html(<TaskRow task={row} />)
})

// --- Partial: delete ---
app.delete('/tasks/:id', async (c) => {
  const id = Number(c.req.param('id'))
  await c.env.DB.prepare('DELETE FROM tasks WHERE id = ?').bind(id).run()
  // returning empty 200 tells htmx to swap with nothing (outerHTML removes element)
  return c.body(null, 200)
})

export default app
```

## JSX Components (Server-side only)

```tsx
// src/components.tsx
export function TaskList({ tasks }: { tasks: { id: number; title: string; done: number }[] }) {
  return (
    <ul id="task-list">
      {tasks.map((t) => (
        <TaskRow key={t.id} task={t} />
      ))}
    </ul>
  )
}

export function TaskRow({ task }: { task: { id: number; title: string; done: number } }) {
  return (
    <li id={`task-${task.id}`} style={task.done ? 'opacity:0.5;text-decoration:line-through' : ''}>
      <span>{task.title}</span>
      <button
        hx-put={`/tasks/${task.id}/toggle`}
        hx-target={`#task-${task.id}`}
        hx-swap="outerHTML"
      >
        {task.done ? 'Undo' : 'Done'}
      </button>
      <button
        hx-delete={`/tasks/${task.id}`}
        hx-target={`#task-${task.id}`}
        hx-swap="outerHTML"
        hx-confirm="Delete this task?"
      >
        ✕
      </button>
    </li>
  )
}
```

## Anti-patterns
- Returning JSON from HTMX endpoints — HTMX expects HTML fragments, not data blobs
- Omitting `id` on swapped elements — without a stable id, `hx-swap="outerHTML"` cannot find the target after a redirect
- Importing HTMX via npm and bundling it — the bundle adds 50 kB to the worker script size unnecessarily; use the CDN or serve from R2
- Using `hx-boost` on the entire body without a `<head>` merge strategy — Hono JSX does not emit a `<head>` diff by default
- Skipping CSRF protection — Workers + Hono require a custom middleware for CSRF tokens on mutating routes

## Gotchas
- HTMX sends `HX-Request: true` on all Ajax requests; check this header to avoid returning full HTML pages to partial slots
- `hx-swap="outerHTML"` replaces the element including its `id`; the returned partial **must** carry the same `id` or targeting breaks on subsequent swaps
- D1 `.run()` returns `{ success, meta }` not rows; use `.all()` or `.first()` for SELECT
- Hono JSX renderer (`hono/jsx`) uses its own JSX factory, not React — do not mix React hooks or Context
- The `response-targets` extension is needed for `hx-target-4xx` / `hx-target-5xx` error routing
- Workers have a 6 ms CPU time limit on the free plan; avoid heavy synchronous loops inside route handlers

## Verification

```bash
# Run locally
npx wrangler dev

# Smoke-test full page
curl -s http://localhost:8787/ | grep 'id="task-list"'

# Smoke-test HTMX partial
curl -s -X POST http://localhost:8787/tasks \
  -H "HX-Request: true" \
  -d "title=hello" | grep '<ul id="task-list"'

# Deploy
npx wrangler deploy
npx wrangler d1 execute htmx-hono-app --command "SELECT * FROM tasks"
```

## Related
- [hono-cloudflare-workers-frontend-api.md](hono-cloudflare-workers-frontend-api.md)
- [progressive-enhancement-workers-form-actions.md](progressive-enhancement-workers-form-actions.md)
- [server-sent-events-streaming-ui.md](server-sent-events-streaming-ui.md)
- [websocket-durable-objects-realtime-ui.md](websocket-durable-objects-realtime-ui.md)

## Sources
- https://htmx.org/docs/
- https://hono.dev/docs/guides/jsx
- https://developers.cloudflare.com/d1/
- https://htmx.org/extensions/response-targets/
