# Dynamic OG Image Generation with Cloudflare Pages Functions

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
You need per-page Open Graph images (og:image) generated dynamically — e.g. blog post titles,
user profile cards, or product previews — without managing a separate image-generation server.

## Context
Cloudflare Pages Functions run at the edge and can produce binary image responses directly.
The `@cf/stabilityai/stable-diffusion-xl-base-1.0` binding covers AI-based generation, but for
text-on-canvas OG cards the `resvg-wasm` approach (WASM + SVG → PNG) is simpler, faster, and
deterministic. Images can be cached in Cloudflare's CDN via `Cache-Control` headers returned
from the Function, giving sub-5 ms P99 for repeat requests.

---

## Architecture / Setup

Deploy a Pages Function at `/functions/og/[slug].ts`. The route captures the slug, fetches
metadata from a KV or D1 store, renders an SVG string, rasterises it to PNG with `resvg-wasm`,
and streams the PNG back with long-lived cache headers.

```
my-pages-project/
├── functions/
│   └── og/
│       └── [slug].ts       ← Pages Function
├── public/
│   └── fonts/
│       └── Inter-Bold.woff2 ← bundled via wrangler.toml assets
└── wrangler.toml
```

`wrangler.toml` — add a KV binding for post metadata:

```toml
name = "my-pages-project"
compatibility_date = "2025-01-01"

[[kv_namespaces]]
binding = "POST_META"
id = "YOUR_KV_NAMESPACE_ID"

[build]
command = "npm run build"
```

---

## OG Function Implementation

```typescript
// functions/og/[slug].ts
import initResvg, { Resvg } from "@resvg/resvg-wasm";
// resvg-wasm ships its own .wasm; import as a module asset
import resvgWasm from "@resvg/resvg-wasm/index_bg.wasm";

interface Env {
  POST_META: KVNamespace;
}

interface PostMeta {
  title: string;
  author: string;
  date: string;
  category: string;
}

let wasmInitialised = false;

async function ensureWasm(): Promise<void> {
  if (!wasmInitialised) {
    await initResvg(resvgWasm);
    wasmInitialised = true;
  }
}

function buildSvg(meta: PostMeta, fontBase64: string): string {
  const title = meta.title.replace(/&/g, "&amp;").replace(/</g, "&lt;");
  const author = meta.author.replace(/&/g, "&amp;");

  return `
<svg width="1200" height="630" viewBox="0 0 1200 630"
     xmlns="http://www.w3.org/2000/svg">
  <defs>
    <style>
      @font-face {
        font-family: 'Inter';
        src: url('data:font/woff2;base64,${fontBase64}');
        font-weight: 700;
      }
    </style>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#0f172a"/>
      <stop offset="100%" stop-color="#1e3a5f"/>
    </linearGradient>
  </defs>

  <!-- Background -->
  <rect width="1200" height="630" fill="url(#bg)"/>

  <!-- Accent bar -->
  <rect x="60" y="60" width="6" height="100" fill="#f97316" rx="3"/>

  <!-- Category badge -->
  <rect x="78" y="60" width="160" height="36" rx="18" fill="#f97316" opacity="0.15"/>
  <text x="158" y="83" font-family="Inter,sans-serif" font-size="18"
        fill="#f97316" text-anchor="middle" font-weight="700">
    ${meta.category.toUpperCase()}
  </text>

  <!-- Title — wrapped manually at ~40 chars per line -->
  <text x="78" y="220" font-family="Inter,sans-serif" font-size="60"
        fill="white" font-weight="700" dominant-baseline="middle">
    ${title}
  </text>

  <!-- Author / date -->
  <text x="78" y="540" font-family="Inter,sans-serif" font-size="28"
        fill="#94a3b8">
    ${author} · ${meta.date}
  </text>

  <!-- Logo watermark -->
  <text x="1140" y="580" font-family="Inter,sans-serif" font-size="22"
        fill="#475569" text-anchor="end">
    example.com
  </text>
</svg>`.trim();
}

export const onRequestGet: PagesFunction<Env> = async ({ params, env, request }) => {
  const slug = Array.isArray(params.slug) ? params.slug[0] : params.slug;

  // Cache hit check — Cloudflare CDN handles this; we just need to set headers.
  const cacheKey = new Request(request.url, request);
  const cache = caches.default;
  const cached = await cache.match(cacheKey);
  if (cached) return cached;

  // Fetch metadata
  const raw = await env.POST_META.get(slug, { type: "json" }) as PostMeta | null;
  if (!raw) {
    return new Response("Not found", { status: 404 });
  }

  // Fetch font (stored as a base64 string in KV, or use fetch from assets)
  const fontBase64 = await env.POST_META.get("__font_inter_bold_b64") ?? "";

  await ensureWasm();

  const svg = buildSvg(raw, fontBase64);
  const resvg = new Resvg(svg, { fitTo: { mode: "width", value: 1200 } });
  const pngData = resvg.render().asPng();

  const response = new Response(pngData, {
    status: 200,
    headers: {
      "Content-Type": "image/png",
      "Cache-Control": "public, max-age=86400, s-maxage=604800, stale-while-revalidate=86400",
      "CDN-Cache-Control": "max-age=604800",
    },
  });

  // Populate the edge cache
  await cache.put(cacheKey, response.clone());
  return response;
};
```

---

## Referencing OG Images in HTML

In your Astro / React / plain HTML `<head>`:

```typescript
// src/layouts/BlogPost.astro
---
const { slug, title, description } = Astro.props;
const ogUrl = `${Astro.site}og/${slug}`;
---
<head>
  <meta property="og:title"       content={title} />
  <meta property="og:description" content={description} />
  <meta property="og:image"       content={ogUrl} />
  <meta property="og:image:width"  content="1200" />
  <meta property="og:image:height" content="630" />
  <meta name="twitter:card"       content="summary_large_image" />
  <meta name="twitter:image"      content={ogUrl} />
</head>
```

Seeding metadata into KV during your build step:

```typescript
// scripts/seed-og-meta.ts  (run via `wrangler kv:key put`)
import { execSync } from "node:child_process";
import posts from "../src/data/posts.json" assert { type: "json" };

for (const post of posts) {
  const value = JSON.stringify({
    title: post.title,
    author: post.author,
    date: new Date(post.date).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }),
    category: post.category,
  });
  execSync(
    `wrangler kv:key put --namespace-id=YOUR_KV_NAMESPACE_ID "${post.slug}" '${value}'`,
    { stdio: "inherit" }
  );
}
```

---

## Anti-patterns
- Returning uncached PNG responses on every request — WASM startup adds ~10 ms; always populate `caches.default`
- Embedding full SVG font files directly in the function source — use KV or Assets to store them separately
- Generating images client-side with `<canvas>` — crawlers do not execute JavaScript
- Relying on Puppeteer / headless Chrome on Workers — unsupported runtime; use the resvg approach
- Hardcoding pixel dimensions without `image:width` / `image:height` meta — Twitter will re-fetch at wrong dimensions

## Gotchas
- `resvg-wasm` global init (`initResvg`) must be called once per isolate; guard with a module-level flag
- Workers (including Pages Functions) have a 128 MB memory limit — keep SVGs simple; avoid large embedded bitmaps
- `caches.default.put()` requires the response URL to match exactly; clone the response before caching
- Wrangler v3+ supports importing `.wasm` as module assets directly; older setups need `fetch()` + `WebAssembly.compile()`
- Long titles must be manually line-broken in SVG — there is no automatic `word-wrap` in SVG 1.1

## Verification
```bash
# Check KV metadata was seeded
wrangler kv:key get --namespace-id=YOUR_KV_NAMESPACE_ID "my-first-post"

# Fetch the generated image locally
wrangler pages dev . &
curl -o test.png http://localhost:8788/og/my-first-post
file test.png   # should output: PNG image data, 1200 x 630

# Inspect cache headers
curl -I https://yoursite.pages.dev/og/my-first-post | grep -i cache
```

## Related
- `cloudflare-r2-presigned-upload-frontend.md`
- `cloudflare-workers-ai-edge-inference-ui.md`
- `wasm-cloudflare-workers-image-transform.md`
- `cloudflare-pages-functions-session-validation-middleware.md`
- `astro-cloudflare-adapter-ssr-hybrid.md`

## Sources
- https://developers.cloudflare.com/pages/functions/
- https://github.com/nicolo-ribaudo/resvg-wasm
- https://developers.cloudflare.com/workers/runtime-apis/cache/
- https://developers.cloudflare.com/workers/wasm-modules/
- https://ogp.me/
