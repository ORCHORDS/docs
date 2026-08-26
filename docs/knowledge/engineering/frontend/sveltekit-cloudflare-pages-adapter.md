# SvelteKit on Cloudflare Pages

- Date: 2026-08-22
- Author: example.com
- Status: production

## SvelteKit at the Edge with Full Binding Access

`@sveltejs/adapter-cloudflare` compiles SvelteKit's server-side routes (load functions, form actions, API endpoints) into Cloudflare Pages Functions, inheriting the full Workers runtime. Static assets are served directly from Cloudflare's edge network while dynamic routes execute in isolates with sub-millisecond warm latency and direct access to D1, KV, R2, and Durable Objects.

The adapter generates a `_worker.js` bundle in the Pages-compatible format. Wrangler v3 and the Cloudflare dashboard both recognise this output, making the deploy pipeline a single `wrangler pages deploy .svelte-kit/cloudflare` command. Because SvelteKit uses platform-specific environment via the `platform` object, the same component and load function code runs identically in local dev (Vite + Miniflare), preview deployments, and production.

Form actions are a killer feature in this stack: a `+page.server.ts` file colocated with its route contains both the `load` function (D1 reads) and `actions` (D1 writes), eliminating the separate API layer entirely while keeping progressive enhancement—forms submit and redirect without JavaScript.

## Context

SvelteKit's file-based routing maps `+page.svelte`, `+page.server.ts`, `+layout.server.ts`, and `+server.ts` to different responsibilities. Only files with `.server.ts` suffixes run in the Pages Function; plain `.ts` imports shared on both client and server. The `platform` object injected by the adapter exposes `env` (bindings), `cf` (the incoming CF request object), and `ctx` (execution context).

## Adapter and Wrangler Setup

```bash
npm install -D @sveltejs/adapter-cloudflare
```

```typescript
// svelte.config.js
import adapter from "@sveltejs/adapter-cloudflare";
import { vitePreprocess } from "@sveltejs/vite-plugin-svelte";

export default {
  preprocess: vitePreprocess(),
  kit: {
    adapter: adapter({
      routes: {
        include: ["/*"],
        exclude: ["<all>"], // exclude static asset paths
      },
    }),
  },
};
```

```toml
# wrangler.toml  (also used by vite-plugin-cloudflare for local dev)
name = "sveltekit-app"
compatibility_date = "2026-01-01"
compatibility_flags = ["nodejs_compat"]
pages_build_output_dir = ".svelte-kit/cloudflare"

[[d1_databases]]
binding = "DB"
database_name = "app"
database_id = "xxxx-yyyy-zzzz"

[[kv_namespaces]]
binding = "CONFIG"
id = "aaaa-bbbb-cccc"

[[r2_buckets]]
binding = "FILES"
bucket_name = "user-files"
```

## Server Load Functions with D1

```typescript
// src/routes/posts/+page.server.ts
import type { PageServerLoad } from "./$types";
import { error } from "@sveltejs/kit";

interface Env {
  DB: D1Database;
}

export const load: PageServerLoad = async ({ platform, url }) => {
  const env = platform?.env as Env;
  const page = Number(url.searchParams.get("page") ?? "1");
  const limit = 20;
  const offset = (page - 1) * limit;

  const [postsResult, countResult] = await Promise.all([
    env.DB.prepare(
      "SELECT id, slug, title, excerpt, published_at FROM posts WHERE published = 1 ORDER BY published_at DESC LIMIT ? OFFSET ?"
    )
      .bind(limit, offset)
      .all<{ id: string; slug: string; title: string; excerpt: string; published_at: string }>(),
    env.DB.prepare("SELECT COUNT(*) as total FROM posts WHERE published = 1").first<{ total: number }>(),
  ]);

  if (!postsResult.success) error(500, "Database error");

  return {
    posts: postsResult.results,
    total: countResult?.total ?? 0,
    page,
    limit,
  };
};
```

## Form Actions with D1 Writes

```typescript
// src/routes/posts/new/+page.server.ts
import type { Actions, PageServerLoad } from "./$types";
import { fail, redirect } from "@sveltejs/kit";
import { z } from "zod";

interface Env {
  DB: D1Database;
}

const PostSchema = z.object({
  title: z.string().min(1).max(200),
  content: z.string().min(1),
  slug: z.string().regex(/^[a-z0-9-]+$/),
});

export const load: PageServerLoad = async ({ platform }) => {
  // check auth via KV session, etc.
  return {};
};

export const actions: Actions = {
  create: async ({ request, platform }) => {
    const env = platform?.env as Env;
    const data = Object.fromEntries(await request.formData());
    const parsed = PostSchema.safeParse(data);

    if (!parsed.success) {
      return fail(422, { errors: parsed.error.flatten().fieldErrors });
    }

    const { title, content, slug } = parsed.data;
    const id = crypto.randomUUID();

    try {
      await env.DB.prepare(
        "INSERT INTO posts (id, title, content, slug, published, published_at) VALUES (?, ?, ?, ?, 0, ?)"
      )
        .bind(id, title, content, slug, new Date().toISOString())
        .run();
    } catch (e) {
      if ((e as Error).message.includes("UNIQUE constraint")) {
        return fail(409, { errors: { slug: ["Slug already taken"] } });
      }
      return fail(500, { errors: { _: ["Database error"] } });
    }

    redirect(303, `/posts/${slug}`);
  },
};
```

## Edge Config via KV

```typescript
// src/lib/server/config.ts
interface Env {
  CONFIG: KVNamespace;
}

export async function getConfig<T>(
  platform: App.Platform,
  key: string,
  fallback: T
): Promise<T> {
  const env = platform.env as Env;
  try {
    const raw = await env.CONFIG.get(key, { type: "json" });
    return raw !== null ? (raw as T) : fallback;
  } catch {
    return fallback;
  }
}

// Usage in load
export const load: PageServerLoad = async ({ platform }) => {
  const flags = await getConfig(platform!, "feature_flags", {
    newEditor: false,
    betaDashboard: false,
  });
  return { flags };
};
```

## R2 File Handling

```typescript
// src/routes/files/+server.ts
import type { RequestHandler } from "./$types";

interface Env {
  FILES: R2Bucket;
}

export const POST: RequestHandler = async ({ request, platform }) => {
  const env = platform?.env as Env;
  const formData = await request.formData();
  const file = formData.get("file") as File;
  if (!file) return new Response("No file", { status: 400 });

  const key = `${crypto.randomUUID()}/${file.name}`;
  await env.FILES.put(key, await file.arrayBuffer(), {
    httpMetadata: { contentType: file.type },
    customMetadata: { originalName: file.name },
  });

  return new Response(JSON.stringify({ key }), {
    headers: { "Content-Type": "application/json" },
  });
};

export const GET: RequestHandler = async ({ url, platform }) => {
  const env = platform?.env as Env;
  const key = url.searchParams.get("key");
  if (!key) return new Response("Missing key", { status: 400 });

  const object = await env.FILES.get(key);
  if (!object) return new Response("Not Found", { status: 404 });

  const headers = new Headers();
  object.writeHttpMetadata(headers);
  headers.set("Cache-Control", "public, max-age=3600");
  return new Response(object.body, { headers });
};
```

## Anti-patterns

- Accessing `platform.env` in a `+page.ts` (client-side load) — it is `undefined` in the browser; bindings are only available in `*.server.ts` files.
- Using `NODE_ENV` or `process.env.SECRET` inside Pages Functions — use `platform.env.MY_SECRET` for secrets set via Wrangler/dashboard.
- Skipping `fail()` and throwing plain errors in actions — SvelteKit expects `fail()` to return validation state back to the form; throwing causes a 500.
- Neglecting `pages_build_output_dir` in `wrangler.toml` — Wrangler defaults to `dist/` and the deploy silently contains no Functions.

## Gotchas

- `platform` is `undefined` when running `vite dev` without the Vite plugin for Cloudflare (`@cloudflare/vite-plugin`). Use `platform?.env ?? {}` defensively in shared helpers.
- D1's `.all()` returns `{ results, success, meta }` — destructure `results`, not the raw return value, before mapping.
- SvelteKit 2.x changed `redirect()` to throw internally; wrapping it in a `try/catch` swallows the redirect. Let it propagate.
- KV `get()` with `type: "json"` returns `null` (not `undefined`) on cache miss — always provide a fallback.

## Verification

```bash
# Local dev with real D1/KV bindings
npx wrangler pages dev --compatibility-date=2026-01-01

# Type check including platform types
npx svelte-kit sync && npx tsc --noEmit

# Deploy
npx svelte-kit build
npx wrangler pages deploy .svelte-kit/cloudflare
```

## Related

- `remix-cloudflare-workers-adapter.md`
- `astro-cloudflare-adapter-ssr-hybrid.md`
- `feature-flags-cloudflare-workers-kv-edge-config.md`
- `react-query-optimistic-mutations-cloudflare-workers.md`

## Sources

- https://kit.svelte.dev/docs/adapter-cloudflare
- https://developers.cloudflare.com/pages/framework-guides/deploy-a-svelte-kit-site/
- https://developers.cloudflare.com/d1/
- https://github.com/sveltejs/kit/tree/main/packages/adapter-cloudflare
