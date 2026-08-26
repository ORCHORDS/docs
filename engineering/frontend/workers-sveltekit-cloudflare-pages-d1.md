# SvelteKit on Cloudflare Pages with D1 via platform.env

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
You are deploying a SvelteKit application to Cloudflare Pages and need to read from a D1 database inside `+page.server.ts` load functions. The standard Node adapter does not expose Cloudflare bindings, so you must use `@sveltejs/adapter-cloudflare` and access the database through `event.platform.env.DB`.

---

## Context
SvelteKit's Cloudflare adapter wraps the SvelteKit server handler as a Pages Function, surfacing Cloudflare runtime bindings through the `platform` property on the `RequestEvent`. D1 is bound as `DB` in `wrangler.toml` and typed via `app.d.ts` augmentation so TypeScript resolves `platform.env.DB` without casting. KV can also be bound for server-side session storage, providing a fast cookie-less session layer. Local development uses `wrangler pages dev` which emulates Pages Functions with real D1 and KV.

---

## Section 1 — Adapter & Wrangler Config

```bash
npm install @sveltejs/adapter-cloudflare
npx wrangler d1 create orchords-sk-db
npx wrangler kv namespace create SESSIONS
```

```toml
# wrangler.toml
name = "orchords-sveltekit"
compatibility_date = "2025-09-01"
compatibility_flags = ["nodejs_compat"]
pages_build_output_dir = ".svelte-kit/cloudflare"

[[d1_databases]]
binding = "DB"
database_name = "orchords-sk-db"
database_id = "<YOUR_DATABASE_ID>"

[[kv_namespaces]]
binding = "SESSIONS"
id = "<YOUR_KV_NAMESPACE_ID>"
preview_id = "<YOUR_KV_PREVIEW_ID>"
```

```javascript
// svelte.config.js
import adapter from '@sveltejs/adapter-cloudflare';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
  preprocess: vitePreprocess(),
  kit: {
    adapter: adapter({
      routes: {
        include: ['/*'],
        exclude: ['<all>'],
      },
    }),
  },
};

export default config;
```

---

## Section 2 — Types & Load Functions

```typescript
// src/app.d.ts
import type { D1Database, KVNamespace } from '@cloudflare/workers-types';

declare global {
  namespace App {
    interface Platform {
      env: {
        DB: D1Database;
        SESSIONS: KVNamespace;
      };
      context: {
        waitUntil(promise: Promise<unknown>): void;
      };
      caches: CacheStorage & { default: Cache };
    }
    interface Locals {
      userId: string | null;
    }
    interface PageData {}
    interface Error {
      message: string;
      code?: string;
    }
  }
}

export {};
```

```typescript
// src/hooks.server.ts
import type { Handle } from '@sveltejs/kit';

export const handle: Handle = async ({ event, resolve }) => {
  const sessionId = event.cookies.get('session_id');
  if (sessionId && event.platform?.env.SESSIONS) {
    const raw = await event.platform.env.SESSIONS.get(`session:${sessionId}`);
    if (raw) {
      const session = JSON.parse(raw) as { userId: string };
      event.locals.userId = session.userId;
    } else {
      event.locals.userId = null;
    }
  } else {
    event.locals.userId = null;
  }
  return resolve(event);
};
```

```typescript
// src/routes/tracks/+page.server.ts
import type { PageServerLoad, Actions } from './$types';
import { error, fail } from '@sveltejs/kit';

export interface Track {
  id: number;
  title: string;
  artist: string;
  bpm: number;
  created_at: string;
}

export const load: PageServerLoad = async ({ platform, url }) => {
  if (!platform?.env.DB) {
    throw error(500, 'Database binding not available');
  }
  const db = platform.env.DB;

  const page = Number(url.searchParams.get('page') ?? '1');
  const limit = 20;
  const offset = (page - 1) * limit;

  const [tracksResult, countResult] = await Promise.all([
    db
      .prepare('SELECT * FROM tracks ORDER BY created_at DESC LIMIT ? OFFSET ?')
      .bind(limit, offset)
      .all<Track>(),
    db.prepare('SELECT COUNT(*) as total FROM tracks').first<{ total: number }>(),
  ]);

  return {
    tracks: tracksResult.results,
    total: countResult?.total ?? 0,
    page,
    limit,
  };
};

export const actions: Actions = {
  create: async ({ platform, request }) => {
    if (!platform?.env.DB) return fail(500, { message: 'DB unavailable' });
    const data = await request.formData();
    const title = data.get('title');
    const artist = data.get('artist');
    const bpm = Number(data.get('bpm'));

    if (!title || !artist || isNaN(bpm) || bpm < 60 || bpm > 240) {
      return fail(400, { message: 'Invalid track data' });
    }

    await platform.env.DB
      .prepare('INSERT INTO tracks (title, artist, bpm) VALUES (?, ?, ?)')
      .bind(String(title), String(artist), bpm)
      .run();

    return { success: true };
  },
};
```

---

## Section 3 — KV Session Storage & Local Dev

```typescript
// src/routes/login/+page.server.ts
import type { Actions } from './$types';
import { redirect, fail } from '@sveltejs/kit';
import { randomUUID } from 'crypto';

export const actions: Actions = {
  default: async ({ platform, request, cookies }) => {
    if (!platform?.env.SESSIONS || !platform?.env.DB) {
      return fail(500, { message: 'Platform bindings unavailable' });
    }
    const data = await request.formData();
    const email = String(data.get('email') ?? '');

    const user = await platform.env.DB
      .prepare('SELECT id FROM users WHERE email = ? LIMIT 1')
      .bind(email)
      .first<{ id: string }>();

    if (!user) return fail(401, { message: 'Invalid credentials' });

    const sessionId = randomUUID();
    await platform.env.SESSIONS.put(
      `session:${sessionId}`,
      JSON.stringify({ userId: user.id }),
      { expirationTtl: 60 * 60 * 24 * 7 } // 7 days
    );

    cookies.set('session_id', sessionId, {
      path: '/',
      httpOnly: true,
      secure: true,
      sameSite: 'lax',
      maxAge: 60 * 60 * 24 * 7,
    });

    throw redirect(303, '/tracks');
  },
};
```

```bash
# Build and run locally with real Cloudflare bindings
npm run build
npx wrangler pages dev .svelte-kit/cloudflare --d1=DB --kv=SESSIONS --port=5173

# Apply D1 schema
npx wrangler d1 execute orchords-sk-db \
  --file=./migrations/001_init.sql

# Deploy to Cloudflare Pages
npx wrangler pages deploy .svelte-kit/cloudflare \
  --project-name=orchords-sveltekit
```

---

## Anti-patterns
- **Accessing `platform.env` in `+page.ts`** — Client-side load functions do not receive `platform`; it is only available in `+page.server.ts` and `+layout.server.ts`.
- **Importing `@cloudflare/workers-types` directly in runtime code** — These are type-only; importing them at runtime throws. Use them only in `.d.ts` files or with `import type`.
- **Using `fetch` to call your own API in a load function** — Inside server-side loads, call D1 directly instead of making an HTTP round-trip through your own endpoints.
- **Hardcoding the KV namespace ID in code** — Always read it from the binding; IDs differ between preview and production environments.

---

## Gotchas
- `wrangler pages dev` requires the built output in `.svelte-kit/cloudflare`, not the source directory — always run `npm run build` first before local dev.
- `platform` can be `undefined` when running SvelteKit in non-Cloudflare environments (e.g., during `vite dev`); always guard with `platform?.env.DB`.
- D1 `all()` returns `{ results, success, meta }` — destructure `results` before iterating; the top-level response is not an array.
- KV `put` with `expirationTtl` requires a minimum value of 60 seconds; values below that are silently rejected.

---

## Verification

```bash
# Type-check the project
npx svelte-check --tsconfig ./tsconfig.json

# Confirm bindings in local dev
curl http://localhost:5173/tracks | jq '.tracks | length'

# Confirm KV session round-trip
curl -c cookies.txt -b cookies.txt -X POST http://localhost:5173/login \
  -d 'email=test@example.com'
curl -c cookies.txt -b cookies.txt http://localhost:5173/tracks
```

---

## Related
- `workers-astro-cloudflare-d1-integration.md`
- `workers-openapi-zod-swagger-ui.md`

---

## Sources
- SvelteKit Cloudflare Adapter — https://kit.svelte.dev/docs/adapter-cloudflare
- Cloudflare D1 Workers Binding — https://developers.cloudflare.com/d1/worker-api/
- Cloudflare KV — https://developers.cloudflare.com/kv/api/
