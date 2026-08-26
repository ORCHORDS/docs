# SvelteKit Form Actions with Cloudflare D1

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case
You need server-side form handling in a SvelteKit app deployed to Cloudflare Pages — validating input, writing to D1, and returning errors back to the same page without a full-page reload when JavaScript is available.

## Context
SvelteKit's form actions run as server-only code on the same route file as the page. When deployed with `@sveltejs/adapter-cloudflare`, they execute inside a Cloudflare Pages Function that has access to the D1 binding via `platform.env`. Actions progressively enhance: without JS the browser POSTs normally; with JS SvelteKit intercepts and replays as a `fetch`, returning `ActionData` for client-side updates. This gives both zero-JS fallback and a smooth SPA-like experience in one model.

## Setup — Adapter and D1 Binding

```bash
npm create svelte@latest my-app -- --template skeleton --types ts
cd my-app
npm install -D @sveltejs/adapter-cloudflare
```

```js
// svelte.config.js
import adapter from '@sveltejs/adapter-cloudflare'
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte'

/** @type {import('@sveltejs/kit').Config} */
export default {
  preprocess: vitePreprocess(),
  kit: {
    adapter: adapter({
      routes: {
        include: ['/*'],
        exclude: ['<all>'],
      },
    }),
  },
}
```

```toml
# wrangler.toml
name = "my-app"
compatibility_date = "2026-08-01"
compatibility_flags = ["nodejs_compat"]
pages_build_output_dir = ".svelte-kit/cloudflare"

[[d1_databases]]
binding = "DB"
database_name = "my-app-db"
database_id = "xxxx-xxxx-xxxx-xxxx"
```

## D1 Schema and Type Declaration

```sql
-- migrations/0001_init.sql
CREATE TABLE IF NOT EXISTS contacts (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  name      TEXT    NOT NULL,
  email     TEXT    NOT NULL UNIQUE,
  message   TEXT    NOT NULL,
  created_at TEXT   DEFAULT (datetime('now'))
);
```

```ts
// src/app.d.ts
import type { D1Database } from '@cloudflare/workers-types'

declare global {
  namespace App {
    interface Platform {
      env: {
        DB: D1Database
      }
      context: {
        waitUntil(promise: Promise<unknown>): void
      }
      caches: CacheStorage & { default: Cache }
    }
    interface Error {
      message: string
    }
  }
}
```

## Route — Page Load + Form Actions

```ts
// src/routes/contact/+page.server.ts
import { fail, redirect } from '@sveltejs/kit'
import type { Actions, PageServerLoad } from './$types'

export const load: PageServerLoad = async ({ platform }) => {
  const db = platform?.env.DB
  if (!db) throw new Error('D1 binding not available')

  const { results } = await db
    .prepare('SELECT id, name, email, created_at FROM contacts ORDER BY id DESC LIMIT 20')
    .all<{ id: number; name: string; email: string; created_at: string }>()

  return { contacts: results }
}

export const actions: Actions = {
  // Default action — handles <form method="POST"> with no action attribute
  default: async ({ request, platform }) => {
    const db = platform?.env.DB
    if (!db) return fail(503, { error: 'Database unavailable' })

    const data = await request.formData()
    const name    = (data.get('name')    as string | null)?.trim() ?? ''
    const email   = (data.get('email')   as string | null)?.trim() ?? ''
    const message = (data.get('message') as string | null)?.trim() ?? ''

    // Validate
    const errors: Record<string, string> = {}
    if (!name)                          errors.name    = 'Name is required'
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) errors.email = 'Valid email required'
    if (message.length < 10)            errors.message = 'Message must be at least 10 characters'

    if (Object.keys(errors).length > 0) {
      return fail(422, { errors, values: { name, email, message } })
    }

    try {
      await db
        .prepare('INSERT INTO contacts (name, email, message) VALUES (?, ?, ?)')
        .bind(name, email, message)
        .run()
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      if (msg.includes('UNIQUE constraint failed')) {
        return fail(409, { errors: { email: 'Email already submitted' }, values: { name, email, message } })
      }
      throw e
    }

    // PRG pattern — redirect after successful POST to prevent re-submission on refresh
    redirect(303, '/contact?success=1')
  },

  // Named action — handles <form method="POST" action="?/delete">
  delete: async ({ request, platform }) => {
    const db = platform?.env.DB
    if (!db) return fail(503, { error: 'Database unavailable' })

    const data = await request.formData()
    const id = Number(data.get('id'))
    if (!Number.isInteger(id) || id <= 0) return fail(400, { error: 'Invalid id' })

    await db.prepare('DELETE FROM contacts WHERE id = ?').bind(id).run()
    // Named action: no redirect needed; SvelteKit re-runs load() automatically
  },
}
```

## Svelte Page — Progressive Enhancement with `use:enhance`

```svelte
<!-- src/routes/contact/+page.svelte -->
<script lang="ts">
  import { enhance } from '$app/forms'
  import type { PageData, ActionData } from './$types'

  let { data, form }: { data: PageData; form: ActionData } = $props()

  // Track submission state for loading UI
  let submitting = $state(false)
</script>

<h1>Contact</h1>

{#if $page.url.searchParams.get('success')}
  <p role="status" class="success">Message sent! We'll be in touch.</p>
{/if}

<!-- use:enhance intercepts the POST and replays as fetch when JS is available -->
<form
  method="POST"
  use:enhance={() => {
    submitting = true
    return async ({ update }) => {
      await update()           // apply ActionData, re-run load()
      submitting = false
    }
  }}
>
  <label>
    Name
    <input name="name" value={form?.values?.name ?? ''} aria-invalid={!!form?.errors?.name} />
    {#if form?.errors?.name}<span class="error">{form.errors.name}</span>{/if}
  </label>

  <label>
    Email
    <input name="email" type="email" value={form?.values?.email ?? ''} aria-invalid={!!form?.errors?.email} />
    {#if form?.errors?.email}<span class="error">{form.errors.email}</span>{/if}
  </label>

  <label>
    Message
    <textarea name="message" aria-invalid={!!form?.errors?.message}>{form?.values?.message ?? ''}</textarea>
    {#if form?.errors?.message}<span class="error">{form.errors.message}</span>{/if}
  </label>

  <button type="submit" disabled={submitting} aria-busy={submitting}>
    {submitting ? 'Sending…' : 'Send'}
  </button>
</form>

<section>
  <h2>Recent contacts</h2>
  <ul>
    {#each data.contacts as contact (contact.id)}
      <li>
        {contact.name} — {contact.email}
        <form method="POST" action="?/delete" use:enhance>
          <input type="hidden" name="id" value={contact.id} />
          <button type="submit">Delete</button>
        </form>
      </li>
    {/each}
  </ul>
</section>
```

## Anti-patterns
- Accessing `platform.env` in `+page.svelte` or any `*.svelte` component — `platform` is only available in `+page.server.ts`, `+layout.server.ts`, and `+server.ts`; never in client-side code
- Forgetting `?/actionName` on named-action `<form>` elements — without it the POST hits the default action and the wrong handler runs
- Returning raw thrown errors from actions — always return `fail()` for expected validation errors; uncaught throws become 500 responses with no `ActionData`
- Using `redirect()` inside a try/catch block — `redirect()` throws a special `Response` object; catching it swallows the redirect
- Calling `db.run()` for SELECT queries — `.run()` returns metadata only; use `.all()` or `.first()` for rows

## Gotchas
- `platform` is `undefined` when running `vite dev` without wrangler; use `npx wrangler pages dev .svelte-kit/cloudflare` to get real bindings
- SvelteKit re-runs the `load()` function after every successful action automatically; avoid manually invalidating in `use:enhance` unless you need cross-route invalidation
- D1 `UNIQUE constraint failed` errors are thrown, not returned; wrap inserts in try/catch and inspect `e.message`
- The `fail()` return value is available as the `form` prop on the page; it is `null` on first load and after a successful redirect
- Pages Functions bundle size limit is 25 MB; Prisma-style ORMs with large engine files exceed this — use D1's prepared statements directly

## Verification

```bash
# Apply migration
npx wrangler d1 execute my-app-db --file=migrations/0001_init.sql

# Build
npm run build

# Preview locally with D1 bindings
npx wrangler pages dev .svelte-kit/cloudflare

# Test default action (no-JS fallback)
curl -s -X POST http://localhost:8788/contact \
  -d "name=Alice&email=alice@example.com&message=Hello there from curl" \
  -L | grep 'success=1'

# Test validation error
curl -s -X POST http://localhost:8788/contact \
  -d "name=&email=bad&message=short" | grep 'error'

# Deploy
npx wrangler pages deploy .svelte-kit/cloudflare --project-name=my-app
```

## Related
- [sveltekit-cloudflare-pages-adapter.md](sveltekit-cloudflare-pages-adapter.md)
- [progressive-enhancement-workers-form-actions.md](progressive-enhancement-workers-form-actions.md)
- [form-validation-zod-workers-endpoint.md](form-validation-zod-workers-endpoint.md)
- [svelte-5-runes-cloudflare-pages.md](svelte-5-runes-cloudflare-pages.md)
- [html-form-validation.md](html-form-validation.md)

## Sources
- https://svelte.dev/docs/kit/form-actions
- https://developers.cloudflare.com/pages/functions/bindings/#d1-databases
- https://svelte.dev/docs/kit/@sveltejs-adapter-cloudflare
- https://developers.cloudflare.com/d1/build-databases/query-databases/
