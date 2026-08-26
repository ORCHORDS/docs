# Astro SSR on Cloudflare Pages with D1 Database Access

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
You are building an Astro site deployed to Cloudflare Pages and need to query a D1 database at request time inside `.astro` page components and API routes. The standard Node adapter does not expose Cloudflare bindings, so you must use the `@astrojs/cloudflare` adapter and access `Astro.locals.runtime.env.DB` directly.

---

## Context
Cloudflare Pages runs Astro in a Workers runtime rather than Node.js, meaning all platform bindings are surfaced through the Workers runtime context. The `@astrojs/cloudflare` adapter wraps Astro's server output in a Pages Function and exposes `runtime.env` on `Astro.locals`. D1 is a serverless SQLite database accessible via the `DB` binding you declare in `wrangler.toml`. ISR (Incremental Static Regeneration) is supported via Astro's `revalidate` export, letting you cache pages and revalidate them in the background. Typed query helpers ensure compile-time safety for your schema.

---

## Section 1 — Adapter & Wrangler Config

```bash
npm install @astrojs/cloudflare
npx wrangler d1 create orchords-db
```

```toml
# wrangler.toml
name = "orchords-astro"
compatibility_date = "2025-09-01"
compatibility_flags = ["nodejs_compat"]
pages_build_output_dir = "./dist"

[[d1_databases]]
binding = "DB"
database_name = "orchords-db"
database_id = "<YOUR_DATABASE_ID>"
```

```js
// astro.config.mjs
import { defineConfig } from 'astro/config';
import cloudflare from '@astrojs/cloudflare';

export default defineConfig({
  output: 'server',
  adapter: cloudflare({
    mode: 'directory',
    functionPerRoute: false,
  }),
});
```

---

## Section 2 — Typed D1 Helpers & Page Implementation

```typescript
// src/lib/db.ts
import type { D1Database } from '@cloudflare/workers-types';

export interface Track {
  id: number;
  title: string;
  artist: string;
  bpm: number;
  created_at: string;
}

export async function getTrackById(
  db: D1Database,
  id: number
): Promise<Track | null> {
  const result = await db
    .prepare('SELECT * FROM tracks WHERE id = ? LIMIT 1')
    .bind(id)
    .first<Track>();
  return result ?? null;
}

export async function listTracks(
  db: D1Database,
  limit = 20,
  offset = 0
): Promise<Track[]> {
  const { results } = await db
    .prepare('SELECT * FROM tracks ORDER BY created_at DESC LIMIT ? OFFSET ?')
    .bind(limit, offset)
    .all<Track>();
  return results;
}

export async function createTrack(
  db: D1Database,
  track: Omit<Track, 'id' | 'created_at'>
): Promise<number> {
  const { meta } = await db
    .prepare(
      'INSERT INTO tracks (title, artist, bpm) VALUES (?, ?, ?) RETURNING id'
    )
    .bind(track.title, track.artist, track.bpm)
    .run();
  return meta.last_row_id as number;
}
```

```astro
---
// src/pages/tracks/[id].astro
import type { GetStaticPaths } from 'astro';
import { getTrackById, listTracks } from '../../lib/db';
import type { RuntimeEnv } from '../../env';

// ISR: revalidate this page every 60 seconds
export const revalidate = 60;

const { DB } = (Astro.locals.runtime.env as RuntimeEnv);

const id = Number(Astro.params.id);
let track = null;
let error: string | null = null;

try {
  track = await getTrackById(DB, id);
} catch (e) {
  error = e instanceof Error ? e.message : 'Database error';
}
---

<!doctype html>
<html lang="en">
  <head><title>{track ? track.title : 'Track Not Found'}</title></head>
  <body>
    {error && (
      <div role="alert" class="error">
        <p>Failed to load track: {error}</p>
        <a >Back to tracks</a>
      </div>
    )}
    {!error && !track && <p>Track not found.</p>}
    {track && (
      <article>
        <h1>{track.title}</h1>
        <p>Artist: {track.artist}</p>
        <p>BPM: {track.bpm}</p>
        <time datetime={track.created_at}>{track.created_at}</time>
      </article>
    )}
  </body>
</html>
```

```typescript
// src/env.d.ts
import type { D1Database } from '@cloudflare/workers-types';

export interface RuntimeEnv {
  DB: D1Database;

}

declare namespace App {
  interface Locals {
    runtime: {
      env: RuntimeEnv;
    };
  }
}
```

---

## Section 3 — API Route & Local Dev

```typescript
// src/pages/api/tracks.ts
import type { APIRoute } from 'astro';
import { listTracks, createTrack } from '../../lib/db';
import type { RuntimeEnv } from '../../env';

export const GET: APIRoute = async ({ locals }) => {
  const { DB } = locals.runtime.env as RuntimeEnv;
  try {
    const tracks = await listTracks(DB, 20, 0);
    return new Response(JSON.stringify({ tracks }), {
      headers: { 'Content-Type': 'application/json' },
    });
  } catch (e) {
    return new Response(
      JSON.stringify({ error: 'Failed to fetch tracks' }),
      { status: 500, headers: { 'Content-Type': 'application/json' } }
    );
  }
};

export const POST: APIRoute = async ({ locals, request }) => {
  const { DB } = locals.runtime.env as RuntimeEnv;
  const body = await request.json();
  if (!body.title || !body.artist || typeof body.bpm !== 'number') {
    return new Response(JSON.stringify({ error: 'Invalid payload' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' },
    });
  }
  const id = await createTrack(DB, {
    title: String(body.title),
    artist: String(body.artist),
    bpm: Number(body.bpm),
  });
  return new Response(JSON.stringify({ id }), {
    status: 201,
    headers: { 'Content-Type': 'application/json' },
  });
};
```

```bash
# Local development with D1 bindings
npx wrangler pages dev ./dist --d1=DB

# Apply migrations
npx wrangler d1 execute orchords-db --file=./migrations/001_create_tracks.sql

# Production deploy
npx wrangler pages deploy ./dist
```

---

## Anti-patterns
- **Using `process.env` for secrets** — Workers runtime does not expose `process.env`; use `Astro.locals.runtime.env` for all bindings.
- **Skipping `mode: 'directory'` in adapter** — Without directory mode, Pages Functions cannot be split per route, reducing cold-start performance.
- **Awaiting D1 queries outside try/catch** — D1 can throw on schema mismatches or quota limits; always wrap in error boundaries.
- **Storing D1 instance in module scope** — The binding is request-scoped; capturing it at module level causes stale references across requests.

---

## Gotchas
- `getStaticPaths` does not receive `Astro.locals` — for dynamic routes that also need static generation, use a separate fetch inside `getStaticPaths` against your own API route instead of calling D1 directly.
- `revalidate` requires Astro 4.5+ and `output: 'server'`; it is silently ignored in `output: 'hybrid'` mode on older versions.
- D1 `first()` returns `null` (not `undefined`) when no row matches — check for `null` explicitly in TypeScript.
- The `@cloudflare/workers-types` package version must match your `compatibility_date`; mismatches cause missing type errors on newer APIs like `D1ExecResult`.

---

## Verification

```bash
# Confirm adapter output exists
ls dist/_worker.js

# Smoke-test API route locally
curl http://localhost:8788/api/tracks

# Confirm D1 binding is wired
npx wrangler pages dev ./dist --d1=DB --port=8788
curl http://localhost:8788/api/tracks | jq '.tracks | length'

# Run Astro type-check
npx astro check
```

---

## Related
- `workers-sveltekit-cloudflare-pages-d1.md`
- `workers-openapi-zod-swagger-ui.md`

---

## Sources
- Astro Cloudflare Adapter — https://docs.astro.build/en/guides/integrations-guide/cloudflare/
- Cloudflare D1 Documentation — https://developers.cloudflare.com/d1/
- Cloudflare Pages Functions — https://developers.cloudflare.com/pages/functions/
