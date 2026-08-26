# Astro Content Collections with Cloudflare R2 Integration

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Your Astro site has content (blog posts, documentation, product listings) stored in Cloudflare R2 as Markdown or MDX files rather than committed to the repository. At build time or on demand (SSR), Astro's content layer must fetch that content from R2 and make it available through the typed `getCollection()` API. You also need media assets (images, videos) stored in R2 and served via a public CDN URL without embedding them in the repo.

## Context

Astro 5 introduced a stable Content Layer API that allows custom loaders as first-class citizens alongside the traditional `src/content/` filesystem approach. A custom R2 loader runs during the Astro build (or at request time in SSR mode) and fetches Markdown/JSON from an R2 bucket using the S3-compatible API or the native Workers `env.R2` binding. The loaded entries are validated with Zod schemas and exposed through the standard `getCollection()` / `getEntry()` functions with full TypeScript types.

---

## R2 Bucket Setup

```bash
# Create the bucket via Wrangler
wrangler r2 bucket create blog-content

# Upload a test post
echo '---
title: Hello World
date: 2026-08-23
tags: [astro, cloudflare]
---
# Hello World
This post lives in R2.' > /tmp/hello-world.md

wrangler r2 object put blog-content/posts/hello-world.md \
  --file /tmp/hello-world.md \
  --content-type text/markdown
```

---

## Custom R2 Loader for Astro Content Layer

```typescript
// src/loaders/r2-loader.ts
import type { Loader, LoaderContext } from 'astro/loaders';
import matter from 'gray-matter';
import { z } from 'astro:content';

interface R2LoaderOptions {
  /** R2 bucket binding name – must match wrangler.toml */
  bucket: string;
  /** Key prefix to list; defaults to '' */
  prefix?: string;
  /** Strip the prefix from the generated slug */
  stripPrefix?: boolean;
}

/**
 * Astro content loader that reads Markdown files from Cloudflare R2.
 * Works in both build-time (via S3 API) and SSR (via native R2 binding).
 */
export function r2Loader(options: R2LoaderOptions): Loader {
  return {
    name: 'r2-loader',
    schema: z.object({
      title: z.string(),
      date: z.coerce.date(),
      tags: z.array(z.string()).default([]),
      draft: z.boolean().default(false),
    }),

    async load({ store, logger, parseData, meta }: LoaderContext) {
      // Access the R2 binding from the Cloudflare platform proxy
      // During `astro build`, this requires platformProxy: { enabled: true }
      const runtime = (globalThis as Record<string, unknown>).__cf_runtime as
        | { env: Record<string, R2Bucket> }
        | undefined;

      if (!runtime) {
        logger.warn('R2 runtime not available; skipping R2 content load');
        return;
      }

      const r2 = runtime.env[options.bucket];
      if (!r2) {
        logger.error(`R2 bucket binding "${options.bucket}" not found`);
        return;
      }

      const listed = await r2.list({ prefix: options.prefix ?? '' });
      logger.info(`Found ${listed.objects.length} objects in R2`);

      for (const obj of listed.objects) {
        if (!obj.key.endsWith('.md') && !obj.key.endsWith('.mdx')) continue;

        const r2Object = await r2.get(obj.key);
        if (!r2Object) continue;

        const raw = await r2Object.text();
        const { data: frontmatter, content } = matter(raw);

        const slug = options.stripPrefix
          ? obj.key.replace(options.prefix ?? '', '').replace(/\.mdx?$/, '')
          : obj.key.replace(/\.mdx?$/, '');

        const parsed = await parseData({ id: slug, data: frontmatter });

        store.set({
          id: slug,
          data: parsed,
          body: content,
          rendered: { html: '' },  // will be rendered by Astro's MD pipeline
        });
      }

      meta.set('lastSync', new Date().toISOString());
      logger.info(`Loaded ${listed.objects.length} entries from R2`);
    },
  };
}
```

---

## Wiring the Loader in astro.config.mjs

```typescript
// astro.config.mjs
import { defineConfig } from 'astro/config';
import cloudflare from '@astrojs/cloudflare';
import { r2Loader } from './src/loaders/r2-loader';

export default defineConfig({
  output: 'hybrid',
  adapter: cloudflare({
    platformProxy: { enabled: true },  // exposes CF bindings at build time
  }),
  integrations: [],
});
```

```typescript
// src/content/config.ts
import { defineCollection } from 'astro:content';
import { r2Loader } from '../loaders/r2-loader';

export const collections = {
  blog: defineCollection({
    loader: r2Loader({
      bucket: 'BLOG_CONTENT',   // matches wrangler.toml binding name
      prefix: 'posts/',
      stripPrefix: true,
    }),
  }),
};
```

---

## wrangler.toml Binding

```toml
# wrangler.toml
name = "my-astro-site"
compatibility_date = "2026-08-01"

[[r2_buckets]]
binding = "BLOG_CONTENT"
bucket_name = "blog-content"

# For local development
[[r2_buckets]]
binding = "BLOG_CONTENT"
bucket_name = "blog-content"
preview_bucket_name = "blog-content-dev"
```

---

## Querying R2-Backed Collections

```typescript
// src/pages/blog/[slug].astro
---
import { getCollection, getEntry, render } from 'astro:content';

export async function getStaticPaths() {
  const posts = await getCollection('blog', ({ data }) => !data.draft);
  return posts.map((post) => ({
    params: { slug: post.id },
    props: { post },
  }));
}

const { post } = Astro.props;
const { Content, headings } = await render(post);
---

<article>
  <h1>{post.data.title}</h1>
  <time datetime={post.data.date.toISOString()}>
    {post.data.date.toLocaleDateString('en-US', { dateStyle: 'long' })}
  </time>
  <ul>
    {post.data.tags.map((tag) => <li>{tag}</li>)}
  </ul>
  <Content />
</article>
```

---

## Serving R2 Media Assets via Public CDN URL

For images and other media stored in R2, expose a public bucket domain and reference it in content frontmatter.

```typescript
// R2 bucket: blog-media (set as public in Cloudflare dashboard)
// Public URL: https://media.example.com/

// src/content/config.ts – extended schema
import { z, defineCollection } from 'astro:content';

export const collections = {
  blog: defineCollection({
    loader: r2Loader({ bucket: 'BLOG_CONTENT', prefix: 'posts/', stripPrefix: true }),
    schema: ({ image }) =>
      z.object({
        title: z.string(),
        date: z.coerce.date(),
        tags: z.array(z.string()).default([]),
        draft: z.boolean().default(false),
        // coverImage stores the R2 key; we resolve the full URL at render time
        coverImage: z.string().optional(),
      }),
  }),
};
```

```astro
---
// src/pages/blog/[slug].astro
const R2_MEDIA_BASE = import.meta.env.R2_MEDIA_BASE ?? 'https://media.example.com';
const coverUrl = post.data.coverImage
  ? `${R2_MEDIA_BASE}/${post.data.coverImage}`
  : null;
---
{coverUrl && (
  <img
    src={coverUrl}
    alt={post.data.title}
    width="1200"
    height="630"
    loading="eager"
    fetchpriority="high"
  />
)}
```

---

## On-Demand Revalidation via Workers Queue

When content changes in R2 (uploaded by a CMS webhook), trigger an Astro rebuild or invalidate the SSR cache:

```typescript
// functions/api/webhook/r2-changed.ts
import type { PagesFunction } from '@cloudflare/workers-types';

interface Env {
  DEPLOY_HOOK_SECRET: string;
  DEPLOY_HOOK_URL: string;  // Cloudflare Pages deploy hook URL
}

export const onRequestPost: PagesFunction<Env> = async ({ request, env }) => {
  const secret = <redacted-secret>'x-webhook-secret');
  if (secret !== env.DEPLOY_HOOK_SECRET) {
    return new Response('Unauthorized', { status: 401 });
  }

  // Trigger a Cloudflare Pages deploy
  const deployRes = await fetch(env.DEPLOY_HOOK_URL, { method: 'POST' });

  return Response.json({
    triggered: deployRes.ok,
    status: deployRes.status,
  });
};
```

---

## Anti-patterns

- **Listing R2 objects without a prefix** – listing the entire bucket on every build is slow and expensive; always scope with a `prefix`.
- **Storing large binary assets as content entries** – R2 Loader is for text content (Markdown, JSON); binary assets belong in a public R2 bucket served directly via CDN URL.
- **Fetching R2 in `getStaticPaths` directly** – use the content layer loader so Astro can cache and deduplicate; direct R2 calls in `getStaticPaths` bypass the cache and run on every build.
- **Using the S3 API at SSR runtime** – the S3-compatible API requires signing each request; in SSR (Cloudflare Workers runtime), use the native `env.BUCKET.get()` binding which is zero-overhead.
- **Embedding R2 credentials in the repo** – use Wrangler secrets (`wrangler secret put`) and access them as environment variables; never commit `AWS_ACCESS_KEY_ID` to source control.

---

## Gotchas

- Astro's Content Layer `store` is ephemeral per build; content loaded from R2 is re-fetched on every `astro build` unless you implement `meta`-based incremental sync checking `obj.uploaded` timestamps.
- `r2.list()` returns at most 1000 objects per call; paginate with the `cursor` property for large buckets.
- `platformProxy: { enabled: true }` in the Cloudflare adapter is required to access R2 bindings during `astro build` (local dev); without it, `globalThis.__cf_runtime` is undefined.
- Astro's `render()` function for content entries requires the loader to store the raw Markdown body, not pre-rendered HTML; set `body` to the raw string from `gray-matter`.
- R2 egress within Cloudflare's network (Worker to R2) is free; egress to external clients is metered — always serve media assets through R2's CDN, not by piping through a Worker.

---

## Verification

```bash
# List R2 objects to confirm they're uploaded
wrangler r2 object list blog-content --prefix posts/

# Test the loader locally
npx astro dev
# Check http://localhost:4321/blog/ renders posts

# Build and check output
npx astro build
ls dist/blog/
```

```typescript
// src/pages/api/content-check.ts (SSR debug endpoint; remove in production)
import type { APIRoute } from 'astro';
import { getCollection } from 'astro:content';

export const GET: APIRoute = async () => {
  const posts = await getCollection('blog');
  return Response.json({
    count: posts.length,
    slugs: posts.map((p) => p.id),
  });
};
```

---

## Related

- `astro-cloudflare-adapter-ssr-hybrid.md`
- `cloudflare-r2-presigned-upload-frontend.md`
- `cloudflare-workers-ai-edge-inference-ui.md`
- `islands-architecture-cloudflare-pages-partial-hydration.md`
- `build-time-env-baking-chunk-hash.md`

---

## Sources

- https://docs.astro.build/en/reference/content-loader-reference/
- https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- https://developers.cloudflare.com/r2/buckets/public-buckets/
- https://docs.astro.build/en/guides/content-collections/
