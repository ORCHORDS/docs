# Pages Functions Bundle Size Optimization

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A Cloudflare Pages project with custom `/functions` route handlers fails to deploy with
`Functions bundle is too large` errors, or deploys but shows high cold-start latency on
function routes. Wrangler reports a compressed bundle exceeding the 1 MB per-function
limit. A middleware function applied to all routes (`_middleware.ts`) imports a validation
library that inflates every route's bundle, even routes that never perform validation.

## Context

Cloudflare Pages Functions are compiled and deployed as individual Cloudflare Workers
scripts. Each file under the `functions/` directory becomes an independent Worker bound
to its route. The hard limit is **1 MB compressed** per function script. Middleware files
(`_middleware.ts`) at each directory level are merged into every route beneath them,
multiplying their bundle contribution across all nested routes.

Unlike a monolithic Worker where you control the entire bundle, Pages Functions compiles
each route independently. The Wrangler build pipeline for Pages Functions uses esbuild
under the hood, respecting `tsconfig.json` and `package.json` side-effects hints. Tree
shaking is enabled but only removes unused exports from ESM modules — CommonJS modules are
fully inlined even when one function is used.

Bundle size affects two metrics: **deploy size** (hard limit) and **parse time** (soft
latency driver). A 900 KB bundle near the limit parses in 15–30 ms per new isolate, adding
measurable latency on cold starts after deploys or low-traffic periods.

## Auditing Bundle Size Per Route

Use Wrangler's built-in `pages functions build` step to see per-route output:

```bash
# Build Pages Functions and output bundle stats
npx wrangler pages functions build \
  --outdir=dist/functions \
  --build-output-directory=dist \
  --compatibility-date=2025-01-01

# Check individual route sizes
ls -lh dist/functions/

# For detailed module-level breakdown use esbuild metafile
npx wrangler pages functions build \
  --outdir=dist/functions \
  --metafile=dist/meta.json

# Inspect with esbuild bundle analyzer
npx esbuild-bundle-analyzer dist/meta.json
```

## Splitting Middleware Responsibility

The most impactful optimisation is narrowing what each `_middleware.ts` imports. Move
concerns that only apply to specific subroutes into dedicated middleware lower in the tree:

```
functions/
  _middleware.ts          ← lightweight: auth header check only (< 2 KB)
  api/
    _middleware.ts        ← heavier: rate limiting, schema validation (loads zod)
    products.ts           ← product handler, inherits api/_middleware only
  static/
    [asset].ts            ← no middleware inheritance, no validation dep
```

```typescript
// functions/_middleware.ts — keep it minimal
export async function onRequest(context: EventContext<Env, string, unknown>) {
  const token = context.request.headers.get('Authorization');
  if (!token?.startsWith('Bearer ')) {
    return new Response('Unauthorized', { status: 401 });
  }
  // simple check — no library import
  context.data.userId = token.slice(7, 43);
  return context.next();
}
```

```typescript
// functions/api/_middleware.ts — heavier deps isolated here
import { z } from 'zod';

export async function onRequest(context: EventContext<Env, string, unknown>) {
  if (context.request.method === 'POST') {
    const body = await context.request.json().catch(() => null);
    const parsed = z.record(z.unknown()).safeParse(body);
    if (!parsed.success) {
      return Response.json({ error: parsed.error.flatten() }, { status: 400 });
    }
    context.data.body = parsed.data;
  }
  return context.next();
}
```

## Replacing Heavy Dependencies

CommonJS packages and packages with large peer-dependency trees are the top offenders.
Swap them for lightweight alternatives or native Workers APIs:

```typescript
// Instead of: import jwt from 'jsonwebtoken';  (~150 KB CJS, pulls in crypto)
// Use the Web Crypto API directly:

async function verifyJWT(token: string, secret: string): Promise<JWTPayload> {
  const [headerB64, payloadB64, sigB64] = token.split('.');
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['verify'],
  );
  const data = new TextEncoder().encode(`${headerB64}.${payloadB64}`);
  const sig = Uint8Array.from(atob(sigB64.replace(/-/g, '+').replace(/_/g, '/')),
    c => c.charCodeAt(0));
  const valid = await crypto.subtle.verify('HMAC', key, sig, data);
  if (!valid) throw new Error('Invalid signature');
  return JSON.parse(atob(payloadB64));
}
```

```typescript
// Instead of: import { marked } from 'marked';  (~80 KB)
// Bind a Worker to render Markdown at a separate endpoint and call it via service binding
// Or: inline a tiny renderer for your specific subset of Markdown features
```

## Tree-Shaking ESM Dependencies

Ensure all dependencies expose ESM entry points so esbuild can remove unused exports:

```jsonc
// package.json — verify packages list "module" or "exports" with ESM paths
{
  "dependencies": {
    "zod": "^3.23.0",           // ESM-native, tree-shakes well
    "date-fns": "^3.6.0"        // has separate ESM exports per function
  }
}
```

```typescript
// Import only what you need from date-fns — not the barrel
import { formatISO } from 'date-fns/formatISO';  // ~1 KB
// Not: import { formatISO } from 'date-fns';     // ~80 KB barrel
```

## Lazy Loading Within a Function

For Pages Functions that serve multiple content types or optional features, use dynamic
`import()` to defer loading:

```typescript
// functions/api/export.ts
export async function onRequestGet(context: EventContext<Env, string, unknown>) {
  const format = new URL(context.request.url).searchParams.get('format') ?? 'json';

  if (format === 'csv') {
    // Loaded only when CSV export is requested
    const { toCsv } = await import('../lib/csv-serializer');
    const data = await fetchData(context.env);
    return new Response(toCsv(data), { headers: { 'Content-Type': 'text/csv' } });
  }

  const data = await fetchData(context.env);
  return Response.json(data);
}

async function fetchData(env: Env) {
  const result = await env.DB.prepare('SELECT * FROM exports LIMIT 1000').all();
  return result.results;
}
```

## Anti-patterns

- **Importing lodash, moment, or other CJS utility monorepos** in middleware: even one
  import from a CJS barrel drags the entire module into every route that inherits the
  middleware.
- **Placing a root `_middleware.ts` that imports a full ORM**: the ORM bundle is merged
  into every single route's function script, multiplying the bundle cost N times.
- **Using `require()` in TypeScript functions**: Wrangler cannot tree-shake CommonJS
  requires. Rewrite to ESM `import` or replace the dependency.
- **Ignoring the metafile**: deploying without inspecting `meta.json` means you cannot
  identify which module is responsible for bundle bloat.

## Gotchas

- Pages Functions middleware chains are **additive per directory level**. A root
  `_middleware.ts` is merged into every function in the project, not just its siblings.
- Wrangler's bundle limit check counts the **compressed** (gzip) size, but the parse cost
  at runtime correlates with the **uncompressed** size. A 200 KB compressed bundle may
  decompress to 900 KB and take 15 ms to parse.
- `import type` statements are stripped at compile time and do not contribute to bundle
  size. Only value imports matter.
- Pages Functions run the `modules` format (ESM). Node.js compatibility shims
  (`nodejs_compat` flag) add ~50 KB to every route. Only enable if strictly needed.
- Dynamic `import()` in Pages Functions resolves at esbuild bundle time. The module is
  inlined into the same file; dynamic import only affects V8 parse scheduling, not network
  fetch.

## Verification

1. Deploy to a preview branch and run:
   ```bash
   npx wrangler pages deploy --project-name my-site dist
   # Observe per-function size warnings in deploy output
   ```
2. Compare route cold-start latency before and after bundle reduction using Pages
   Analytics or a synthetic monitor hitting each function route immediately after deploy.
3. Validate the metafile output: any single module over 20 KB uncompressed in the
   dependency tree warrants a replacement evaluation.
4. Set a CI size budget by checking the build output:
   ```bash
   MAX_BYTES=900000
   for f in dist/functions/*.js; do
     size=$(wc -c < "$f")
     [ "$size" -gt "$MAX_BYTES" ] && echo "OVER BUDGET: $f ($size bytes)" && exit 1
   done
   ```

## Related

- `nextjs-cloudflare-pages-bundle-optimization.md`
- `workers-module-initialization-lazy-loading.md`
- `javascript-bundle-size.md`
- `dead-code-elimination.md`
- `build-tool-performance-esbuild-rolldown.md`
- `code-splitting-strategies.md`

## Sources

- Pages Functions Size Limits — https://developers.cloudflare.com/pages/functions/limits/
- Pages Functions Middleware — https://developers.cloudflare.com/pages/functions/middleware/
- Wrangler Pages Functions Build — https://developers.cloudflare.com/workers/wrangler/commands/#pages-functions-build
- esbuild Tree Shaking — https://esbuild.github.io/api/#tree-shaking
- Workers Bundle Limits — https://developers.cloudflare.com/workers/platform/limits/#worker-size
