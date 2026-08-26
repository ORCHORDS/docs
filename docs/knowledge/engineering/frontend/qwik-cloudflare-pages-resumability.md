# Qwik on Cloudflare Pages with Resumability

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You want near-zero JavaScript on initial load for a content-heavy or interactive site deployed to Cloudflare Pages. Qwik's resumability model serialises component state into the HTML at SSR time; the browser resumes execution at the exact point where the server left off instead of re-executing the entire component tree (hydration). Cloudflare Pages edge servers run SSR close to the user.

## Context

Qwik City is the meta-framework on top of Qwik. It ships an official Cloudflare Pages adapter that produces a `_worker.js` bundle compatible with Pages Functions. Cloudflare bindings (D1, KV, R2) are accessed via `platform.env` inside `loader$()` and `action$()`. Because components do not re-execute on the client, there is no equivalent of `useEffect` for data fetching—all server data flows through loaders.

## Adapter Setup and vite.config.ts

```typescript
// vite.config.ts
import { defineConfig } from 'vite';
import { qwikVite } from '@builder.io/qwik/optimizer';
import { qwikCity } from '@builder.io/qwik-city/vite';
import { cloudflarePagesAdapter } from '@builder.io/qwik-city/adapters/cloudflare-pages/vite';

export default defineConfig(() => {
  return {
    plugins: [
      qwikCity(),
      qwikVite(),
      cloudflarePagesAdapter(),
    ],
    preview: {
      headers: {
        'Cache-Control': 'public, max-age=600',
      },
    },
  };
});
```

```toml
# wrangler.toml
name = "my-qwik-app"
pages_build_output_dir = "dist"
compatibility_date = "2024-09-23"
compatibility_flags = ["nodejs_compat"]

[[d1_databases]]
binding = "DB"
database_name = "my-app-db"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[[kv_namespaces]]
binding = "SESSIONS"
id = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

```typescript
// src/routes/items/index.tsx
import { component$ } from '@builder.io/qwik';
import {
  routeLoader$,
  routeAction$,
  Form,
  zod$,
  z,
} from '@builder.io/qwik-city';
import type { RequestEventBase } from '@builder.io/qwik-city';

// Type for Cloudflare env — extend as needed
interface CloudflareEnv {
  DB: D1Database;
  SESSIONS: KVNamespace;
}

interface Item {
  id: string;
  name: string;
  created_at: string;
}

// loader$ runs on the server; platform.env gives access to bindings
export const useItems = routeLoader$(async ({ platform }) => {
  const env = platform.env as CloudflareEnv;
  const { results } = await env.DB.prepare(
    'SELECT id, name, created_at FROM items ORDER BY created_at DESC LIMIT 100'
  ).all<Item>();
  return results;
});

// action$ handles form submissions server-side
export const useCreateItem = routeAction$(
  async ({ name }, { platform, fail }) => {
    const env = (platform as { env: CloudflareEnv }).env;
    const id = crypto.randomUUID();
    const createdAt = new Date().toISOString();

    try {
      await env.DB.prepare(
        `INSERT INTO items (id, name, created_at) VALUES (?, ?, ?)`
      )
        .bind(id, name.trim(), createdAt)
        .run();
    } catch (e) {
      return fail(500, { message: 'Database error' });
    }

    return { id, name, createdAt };
  },
  zod$({ name: z.string().min(2).max(200) })
);

export default component$(() => {
  const items = useItems();
  const createItem = useCreateItem();

  return (
    <section>
      <h1>Items</h1>

      <Form action={createItem}>
        <input name="name" required />
        <button type="submit">Add</button>
        {createItem.value?.failed && (
          <p>{createItem.value.message}</p>
        )}
      </Form>

      <ul>
        {items.value.map((item) => (
          <li key={item.id}>
            {item.name} — {item.created_at}
          </li>
        ))}
      </ul>
    </section>
  );
});
```

## Resumability vs Hydration Trade-off

| | Hydration (React/Vue) | Resumability (Qwik) |
|---|---|---|
| Initial JS download | Full framework + all components | Only the event handlers needed for visible interactions |
| Client re-execution | Yes — component tree re-runs | No — serialised state is restored from HTML |
| Time to interactive | Depends on bundle size | Near-instant (resumes from server state) |
| Mental model shift | `useEffect` for data | `loader$` / `action$` for everything server-side |

Because components do not re-run, you cannot use `useState` for data that should come from the server. Use `useSignal` and `useStore` for purely client-side reactive state (e.g., a toggle, a counter), and `routeLoader$` for any data that requires a Cloudflare binding.

## Performance on Cloudflare Pages Edge

Cloudflare Pages runs SSR in Workers at the closest PoP to the visitor. Qwik's lazy-loaded event chunks (`*.js` chunks emitted per event handler) are served from the Pages CDN. The combination means:

1. SSR HTML arrives from the nearest edge, typically <50 ms TTFB in major cities.
2. The browser parses and paints HTML—no JS blocking.
3. When the user first interacts, Qwik downloads only the tiny chunk for that handler.

Avoid putting large synchronous data processing inside `loader$`—it runs in the Worker request, so CPU time counts toward the Worker's 50 ms CPU limit on the free plan (30 s on paid).

## Anti-patterns

- Using `useVisibleTask$` for initial data loading—it runs on the client after paint, defeating edge SSR.
- Importing Node.js modules inside loaders without checking `nodejs_compat` is set.
- Casting `platform.env` without a type guard when bindings are undefined in local dev (local dev requires `--d1=DB` wrangler flag).
- Placing large data arrays in `useStore`—Qwik serialises the full store into the HTML, inflating page size.

## Gotchas

- `platform.env` is `undefined` in unit tests unless mocked—use a test factory that provides a fake `D1Database`.
- The Cloudflare Pages adapter sets `output: 'server'`; do not override it to `'static'` or loaders will not run.
- Qwik City's `Form` component reloads the loader automatically after a successful action—no manual cache invalidation needed.
- Hot module replacement in local dev (`npm run dev`) uses a Node.js server, not Workers; platform.env bindings are only available via `wrangler pages dev`.

## Verification

```bash
# Build
npm run build

# Preview with Workers runtime and D1 binding
npx wrangler pages dev dist --d1=DB

# Check that 0 kB JS is requested before any interaction
# Open DevTools > Network > JS — only qwik-prefetch-graph is loaded
# Submit the form — watch the single action chunk download

# Deploy
npx wrangler pages deploy dist
```

## Related

- `nextjs-app-router-cloudflare-pages-adapter.md`
- `css-container-queries-cloudflare-pages-components.md`

## Sources

- https://qwik.builder.io/docs/deployments/cloudflare-pages/
- https://developers.cloudflare.com/pages/
- https://qwik.builder.io/docs/route-loader/
- https://qwik.builder.io/docs/action/
