# Astro with Cloudflare Adapter: SSR + Static Hybrid

- Date: 2026-08-22
- Author: example.com
- Status: production

## Shipping Fast Static + Dynamic Pages from One Codebase

Astro's "hybrid" output mode lets you declare each route as either fully static (pre-rendered at build time) or server-rendered on demand, with the Cloudflare adapter executing SSR pages inside Workers. This means marketing pages and blog posts get baked to HTML at deploy time and served from Cloudflare's cache, while authenticated dashboards, API endpoints, and search routes are rendered per-request with access to D1, R2, and KV—all from a single `wrangler publish`.

The combination eliminates the classic tradeoff between developer ergonomics (one codebase) and runtime performance (static where possible, dynamic where needed). Wrangler v3's `--experimental-local` flag with Miniflare 3 emulates all Workers bindings locally, so the development loop is fast even for D1 queries.

Astro 4+ integrates natively with Cloudflare's image resizing service when the adapter's `imageService` option is set to `"cloudflare"`, offloading WebP/AVIF conversion and dimension transforms to the edge without a separate build step.

## Context

The Cloudflare adapter targets the Workers runtime, not Pages Functions. Pages deployments use the adapter too—Workers assets (formerly Pages) is the recommended deployment target for Astro 5+. The `@astrojs/cloudflare` package must be installed and configured in `astro.config.mjs`; the `output` field drives which routes pre-render versus SSR.

## Adapter Configuration

```typescript
// astro.config.mjs
import { defineConfig } from "astro/config";
import cloudflare from "@astrojs/cloudflare";

export default defineConfig({
  output: "hybrid",          // "static" | "server" | "hybrid"
  adapter: cloudflare({
    imageService: "cloudflare",
    platformProxy: {
      enabled: true,          // exposes bindings in dev via Miniflare
    },
  }),
});
```

```toml
# wrangler.toml
name = "astro-site"
compatibility_date = "2026-01-01"
compatibility_flags = ["nodejs_compat"]

[[d1_databases]]
binding = "DB"
database_name = "content"
database_id = "xxxx-yyyy-zzzz"

[[r2_buckets]]
binding = "ASSETS_BUCKET"
bucket_name = "site-assets"

[[kv_namespaces]]
binding = "CONFIG"
id = "aaaa-bbbb-cccc"
```

## D1 Queries in Astro Endpoints

```typescript
// src/pages/api/articles.ts
import type { APIRoute } from "astro";

interface Env {
  DB: D1Database;
}

export const prerender = false; // opt this route into SSR

export const GET: APIRoute = async ({ locals }) => {
  const env = locals.runtime.env as Env;

  const { results } = await env.DB.prepare(
    `SELECT id, slug, title, published_at
     FROM articles
     WHERE published = 1
     ORDER BY published_at DESC
     LIMIT 20`
  ).all<{ id: number; slug: string; title: string; published_at: string }>();

  return new Response(JSON.stringify(results), {
    headers: { "Content-Type": "application/json" },
  });
};

export const POST: APIRoute = async ({ request, locals }) => {
  const env = locals.runtime.env as Env;
  const body = await request.json<{ title: string; content: string }>();

  const id = crypto.randomUUID();
  await env.DB.prepare(
    "INSERT INTO articles (id, title, content, published, published_at) VALUES (?, ?, ?, 0, ?)"
  )
    .bind(id, body.title, body.content, new Date().toISOString())
    .run();

  return new Response(JSON.stringify({ id }), { status: 201 });
};
```

## SSR Page with D1

```astro
---
// src/pages/articles/[slug].astro
export const prerender = false;

import type { GetStaticPaths } from "astro";
import Layout from "../../layouts/Base.astro";

interface Env {
  DB: D1Database;
}

const { slug } = Astro.params;
const env = Astro.locals.runtime.env as Env;

const article = await env.DB.prepare(
  "SELECT title, content, published_at FROM articles WHERE slug = ? AND published = 1"
)
  .bind(slug)
  .first<{ title: string; content: string; published_at: string }>();

if (!article) return Astro.redirect("/404");
---

<Layout title={article.title}>
  <article>
    <h1>{article.title}</h1>
    <time datetime={article.published_at}>
      {new Date(article.published_at).toLocaleDateString()}
    </time>
    <div set:html={article.content} />
  </article>
</Layout>
```

## Image Optimization with Cloudflare Images

```astro
---
// src/components/HeroImage.astro
import { Image } from "astro:assets";
interface Props {
  src: string;
  alt: string;
}
const { src, alt } = Astro.props;
---

<!-- With imageService:"cloudflare", Astro transforms this to a
     Cloudflare Image Resizing URL automatically -->
<Image
  src={src}
  alt={alt}
  width={1200}
  height={630}
  format="webp"
  quality={85}
/>
```

```typescript
// Custom image endpoint proxying R2 through Cloudflare resizing
// src/pages/img/[...path].ts
import type { APIRoute } from "astro";

interface Env {
  ASSETS_BUCKET: R2Bucket;
}

export const prerender = false;

export const GET: APIRoute = async ({ params, locals, url }) => {
  const env = locals.runtime.env as Env;
  const key = params.path as string;
  const object = await env.ASSETS_BUCKET.get(key);
  if (!object) return new Response("Not Found", { status: 404 });

  const w = url.searchParams.get("w");
  const headers = new Headers();
  object.writeHttpMetadata(headers);
  headers.set("Cache-Control", "public, max-age=31536000, immutable");

  // Let Cloudflare resize via cf.image hint
  const response = new Response(object.body, { headers });
  return response;
};
```

## Deployment via Wrangler

```bash
# Build then deploy
npx astro build
npx wrangler deploy

# Or use the integrated command
npx astro build && npx wrangler deploy --config wrangler.toml

# D1 migration before deploy
npx wrangler d1 migrations apply content --remote

# Preview locally with real bindings
npx wrangler dev --local --persist
```

## Anti-patterns

- Setting `prerender = true` on pages that read from D1 at request time — build fails with "runtime unavailable" or silently returns stale data.
- Using `Astro.cookies` in a statically pre-rendered page — cookie access is only available in SSR mode.
- Forgetting `platformProxy: { enabled: true }` in adapter config — `locals.runtime` is `undefined` in local dev and all D1/KV calls throw.
- Importing Cloudflare Worker types (`D1Database`, `R2Bucket`) without `@cloudflare/workers-types` in `tsconfig.json` — type errors across every endpoint.

## Gotchas

- `locals.runtime.env` is typed as `unknown` by default; cast it to your `Env` interface or use module augmentation on `App.Locals`.
- Astro's `<Image>` component with `imageService: "cloudflare"` only works for images served from your own domain or R2 public bucket; external URLs are passed through unchanged.
- Hybrid mode pre-renders pages that export `const prerender = true` **or pages with no export at all**—you must explicitly opt SSR pages in with `export const prerender = false`.
- Wrangler asset upload limits: Worker bundles must be under 10 MB (compressed). Large static asset trees should be split into R2 or served via Cloudflare Pages' static asset handling.

## Verification

```bash
# Run type checks across src + env
npx astro check

# Confirm static pages are pre-rendered
cat dist/_worker.js | grep -c "prerender"

# Smoke test SSR endpoint
curl https://your-site.workers.dev/api/articles
```

## Related

- `nextjs-partial-prerendering-cloudflare.md`
- `sveltekit-cloudflare-pages-adapter.md`
- `feature-flags-cloudflare-workers-kv-edge-config.md`
- `font-loading-cloudflare-pages-mobile.md`

## Sources

- https://docs.astro.build/en/guides/integrations-guide/cloudflare/
- https://developers.cloudflare.com/images/transform-images/
- https://developers.cloudflare.com/d1/
- https://github.com/withastro/adapters/tree/main/packages/cloudflare
