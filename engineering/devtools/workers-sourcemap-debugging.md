# Source Map Upload for Production Workers Debugging

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Stack traces in the Cloudflare dashboard (and in Workers Logs / Tail) show minified output like `at Object.<anonymous> (worker.js:1:43821)`. You cannot correlate the error to the original TypeScript source without source maps. You want symbolicated stack traces in the dashboard and in your external error tracker (e.g., Sentry) with zero extra manual steps on each deploy.

## Context

Wrangler v3.39+ supports automatic source map upload as part of `wrangler deploy`. When `upload_source_maps = true` is set in `wrangler.toml`, Wrangler uploads the `.js.map` file alongside the Worker bundle. The Cloudflare dashboard's **Workers & Pages → your-worker → Logs → Exceptions** view uses the uploaded map to symbolicate stack traces automatically. Source maps are stored encrypted and are never served to end-users.

## Solution

```toml
# wrangler.toml
name               = "my-worker"
compat_date        = "2024-09-23"
main               = "dist/index.js"
upload_source_maps = true        # <── enables automatic upload on every deploy

[build]
command = "NODE_ENV=production node --import tsx/esm build.ts"
```

```typescript
// build.ts  — produce an external source map alongside the bundle
import * as esbuild from 'esbuild';
import * as fs from 'node:fs';
import * as path from 'node:path';

const outdir = 'dist';

async function build(): Promise<void> {
  fs.mkdirSync(outdir, { recursive: true });

  await esbuild.build({
    entryPoints: ['src/index.ts'],
    bundle:      true,
    outdir,
    format:      'esm',
    target:      'es2022',
    platform:    'browser',
    minify:      true,
    sourcemap:   'external',   // produces dist/index.js.map
    // 'external' keeps the map in a separate file.
    // 'linked'   adds a sourceMappingURL comment pointing to the .map file.
    // 'inline'   embeds the map as a base64 data URL in the .js file.
    // Wrangler expects 'external' for upload_source_maps = true.
  });
}

build().catch((e) => { console.error(e); process.exit(1); });
```

```typescript
// src/index.ts  — structured error logging for dashboard correlation
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    try {
      return await handleRequest(request, env);
    } catch (err: unknown) {
      // Log the full error object so the dashboard captures the stack
      const error = err instanceof Error ? err : new Error(String(err));
      console.error(
        JSON.stringify({
          message:    error.message,
          stack:      error.stack,
          url:        request.url,
          cf_ray:     request.headers.get('cf-ray'),
          timestamp:  new Date().toISOString(),
        }),
      );
      return new Response('Internal Server Error', { status: 500 });
    }
  },
};

async function handleRequest(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  if (url.pathname === '/api/data') {
    return fetchData(env);
  }
  return new Response('Not Found', { status: 404 });
}

async function fetchData(env: Env): Promise<Response> {
  const row = await env.MY_DB
    .prepare('SELECT * FROM items WHERE id = ?')
    .bind(1)
    .first<{ id: number; name: string }>();

  if (!row) throw new Error('Item not found');   // line shown in symbolicated trace

  return Response.json(row);
}

interface Env {
  MY_DB: D1Database;
}
```

```typescript
// src/sentry.ts  — integrating source-map-aware error reporting with Sentry
// Uses @sentry/cloudflare (Sentry's official Workers SDK)
import * as Sentry from '@sentry/cloudflare';

export function withSentry(
  handler: ExportedHandler<Env>,
  env: Env,
): ExportedHandler<Env> {
  return Sentry.withSentry(
    (_env) => ({
      dsn:              env.SENTRY_DSN,
      release:          env.WORKER_VERSION,   // set via wrangler.toml [vars]
      environment:      env.ENVIRONMENT,
      tracesSampleRate: 0.1,
      // Sentry can apply source maps client-side using the artifacts it receives
      // via `sentry-cli sourcemaps upload` run as a post-deploy step.
    }),
    handler,
  );
}

// src/index.ts (updated)
import { withSentry } from './sentry';

const handler: ExportedHandler<Env> = {
  async fetch(request, env, ctx) {
    return handleRequest(request, env);
  },
};

export default withSentry(handler, {} as Env);

interface Env {
  MY_DB:          D1Database;
  SENTRY_DSN:     string;
  WORKER_VERSION: string;
  ENVIRONMENT:    string;
}
```

```bash
# deploy-and-upload.sh  — full deploy pipeline with Sentry source map upload
#!/usr/bin/env bash
set -euo pipefail

VERSION=$(git rev-parse --short HEAD)

# 1. Build (produces dist/index.js + dist/index.js.map)
NODE_ENV=production WORKER_VERSION="$VERSION" node --import tsx/esm build.ts

# 2. Deploy to Cloudflare (Wrangler uploads the .js.map automatically)
wrangler deploy --env production --var WORKER_VERSION:"$VERSION"

# 3. Upload source maps to Sentry for Sentry-side symbolication
#    Requires SENTRY_AUTH_TOKEN, SENTRY_ORG, SENTRY_PROJECT env vars in CI
sentry-cli sourcemaps inject dist/          # inject debug IDs into .js files
sentry-cli sourcemaps upload                \
  --release "$VERSION"                      \
  --dist   "production"                     \
  dist/

echo "Deploy complete: $VERSION"
```

```typescript
// scripts/filter-sensitive-source.ts
// If you ship generated code with embedded secrets in comments (e.g. schema
// generators that include connection strings), strip them from the source map
// before uploading by post-processing the .map JSON.
import * as fs from 'node:fs';

interface SourceMap {
  version:        number;
  sources:        string[];
  sourcesContent: (string | null)[];
  mappings:       string;
}

const SENSITIVE_PATTERNS: RegExp[] = [
  /password\s*=\s*['"][^'"]+['"]/gi,
  /secret\s*[:=]\s*['"][^'"]+['"]/gi,
  /Bearer\s+[A-Za-z0-9._-]{20,}/g,
];

function redactSensitive(content: string): string {
  let out = content;
  for (const pattern of SENSITIVE_PATTERNS) {
    out = out.replace(pattern, '[REDACTED]');
  }
  return out;
}

const mapPath = 'dist/index.js.map';
const raw: SourceMap = JSON.parse(fs.readFileSync(mapPath, 'utf8'));

raw.sourcesContent = raw.sourcesContent.map((content) =>
  content == null ? null : redactSensitive(content),
);

// Optionally strip source content for files under src/internal/
const INTERNAL_SOURCE_PREFIX = 'src/internal/';
raw.sources.forEach((src, i) => {
  if (src.startsWith(INTERNAL_SOURCE_PREFIX)) {
    raw.sourcesContent[i] = null;   // map still works for line numbers, no source shown
  }
});

fs.writeFileSync(mapPath, JSON.stringify(raw));
console.log('Source map sanitized.');
```

## Implementation Details

**How Cloudflare stores and uses source maps.** Uploaded source maps are stored in Cloudflare's internal artifact storage, encrypted at rest. They are associated with the specific Worker version hash. When an exception is captured by Workers Runtime, the dashboard fetches the map for the matching version and applies [mozilla/source-map](https://github.com/mozilla/source-map) symbolication server-side. Maps are never exposed via public URLs.

**`upload_source_maps = true` requirements.** The `main` file must have an adjacent `.map` file with a matching name (`dist/index.js` → `dist/index.js.map`). The `.map` file must not exceed 15 MB. Wrangler validates both during the upload step and fails the deploy if either condition is not met.

**Correlating error IDs to source lines.** Every exception in Workers Logs has an `errorId` field (a UUID). You can look up a specific error ID in **Dashboard → Workers → your-worker → Logs** and see the symbolicated stack trace. When logging from the Worker, emit the `cf-ray` header value alongside the error message — it links the Worker exception to the edge request in Cloudflare's system.

**Sentry integration workflow.** Sentry's `@sentry/cloudflare` package wraps your handler and captures unhandled exceptions automatically. Separately, `sentry-cli sourcemaps inject` stamps a `debug_id` comment into each `.js` file and its corresponding `.map`; `sentry-cli sourcemaps upload` ships both to Sentry. Sentry then matches captured stack frames to the uploaded maps using the debug ID, regardless of file paths.

## Anti-patterns

- **Using `sourcemap: 'inline'` in production.** Inline maps embed the full source as base64 in the `.js` file, roughly doubling its size. This increases cold-start time and uses your Worker size quota. Always use `sourcemap: 'external'` in production.
- **Uploading maps to Sentry without injecting debug IDs first.** Without `sentry-cli sourcemaps inject`, Sentry cannot match frames to maps reliably when file paths differ between environments. Always run `inject` before `upload`.
- **Not stripping `sourcesContent` from maps shipped to external parties.** The `sourcesContent` field embeds your raw TypeScript source. If you share maps with a third-party observability tool, sanitize or null out `sourcesContent` for sensitive modules.

## Gotchas

- `upload_source_maps = true` requires Wrangler ≥ 3.39. Older Wrangler versions silently ignore the key and upload no map.
- Source maps uploaded to Cloudflare are scoped to a specific Worker version. Rolling back to a previous version restores the previously uploaded map automatically.
- If you run a post-processing script on `dist/index.js` (e.g., banner injection), re-generate or update the source map afterward — any offset change will desync the map.
- The Cloudflare dashboard symbolication works only for exceptions captured by the Workers runtime itself. Errors swallowed and logged as strings (not Error objects) will not have stack traces to symbolicate.

## Verification

```bash
# Confirm the .map file is produced
ls -lh dist/index.js dist/index.js.map

# Validate map with source-map-cli
npx source-map resolve dist/index.js.map 1 43821
# → should print the original TypeScript file, line, and column

# Deploy and check the Cloudflare dashboard upload
wrangler deploy --env production
# Look for: "Uploading source map for dist/index.js" in Wrangler output

# Sentry: verify the release has uploaded artifacts
sentry-cli releases files "$(git rev-parse --short HEAD)" list
```

## Related

- `documentation/categories/devtools/workers-wrangler-custom-builds.md` — configuring esbuild's `sourcemap` option
- `documentation/categories/devtools/workers-bundle-size-analysis.md` — keeping bundle + map sizes in budget
- Cloudflare docs: [Source maps](https://developers.cloudflare.com/workers/observability/source-maps/)

## Sources

- https://developers.cloudflare.com/workers/observability/source-maps/
- https://docs.sentry.io/platforms/javascript/guides/cloudflare/
- https://docs.sentry.io/cli/releases/#upload-source-maps
- https://esbuild.github.io/api/#sourcemap
