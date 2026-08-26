# Vite with Cloudflare Workers Development Mode

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

You have a Cloudflare Workers project (or a full-stack app with a Workers backend) and want Vite's
fast HMR and plugin ecosystem for the frontend, while running the Worker in a real Workers runtime
during local development — not a Node.js shim. The stock `wrangler dev` command serves the Worker
but doesn't integrate with Vite's dev server, causing awkward split workflows.

## Context

Cloudflare released `@cloudflare/vite-plugin` (previously called `vite-plugin-cloudflare`) to
bridge Vite's development server with the full Workers runtime powered by `workerd`. The plugin
embeds a `workerd` process inside the Vite dev server so that both the Vite frontend and the Worker
run together under a single `vite dev` command, sharing HMR for client assets while the Worker
executes in an authentic V8 isolate (the same engine used in production).

Key capabilities:
- Vite HMR for frontend assets (React, Vue, Svelte, vanilla TS, etc.)
- Worker module executed inside the real `workerd` runtime
- KV, R2, D1, Durable Objects, Service Bindings — all usable via local Miniflare emulation
- Wrangler config (`wrangler.toml` / `wrangler.json`) is read automatically
- Works with Vite 5+ and Wrangler 3.78+

## Installation

```bash
pnpm add -D @cloudflare/vite-plugin vite wrangler
```

Minimum supported versions (as of mid-2026):

| Package                    | Minimum  |
|----------------------------|----------|
| `vite`                     | 5.4.0    |
| `wrangler`                 | 3.78.0   |
| `@cloudflare/vite-plugin`  | 1.0.0    |
| Node.js                    | 18.20.0  |

## Basic Configuration

```typescript
// vite.config.ts
import { defineConfig } from 'vite';
import { cloudflare } from '@cloudflare/vite-plugin';

export default defineConfig({
  plugins: [
    cloudflare(),
  ],
});
```

The plugin reads `wrangler.toml` from the project root by default. Point to a custom config file
when needed:

```typescript
cloudflare({
  configPath: './workers/wrangler.toml',
})
```

## Worker Entry Point

The Worker's main module must use the standard ES module format with a default export:

```typescript
// src/worker.ts
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/api/hello') {
      return Response.json({ message: 'Hello from Worker' });
    }

    // Fall through to Vite-served frontend assets
    return new Response('Not found', { status: 404 });
  },
} satisfies ExportedHandler<Env>;
```

Declare bindings in `wrangler.toml`:

```toml
name = "my-worker"
main = "src/worker.ts"
compatibility_date = "2025-01-01"

[[kv_namespaces]]
binding = "CACHE"
id = "..."
preview_id = "..."

[[d1_databases]]
binding = "DB"
database_name = "mydb"
database_id = "..."
```

## Full-Stack Setup (Frontend + Worker)

For a project where the Worker serves the frontend too (SPA or SSR), configure Vite's proxy to
route API calls through the Worker while Vite serves the client bundle:

```typescript
// vite.config.ts
import { defineConfig } from 'vite';
import { cloudflare } from '@cloudflare/vite-plugin';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [
    react(),
    cloudflare({
      // Route /api/* to the Worker; everything else is handled by Vite
      workerRoutes: ['/api/*'],
    }),
  ],
  server: {
    port: 5173,
  },
});
```

With `workerRoutes`, the plugin intercepts matching requests and forwards them to the `workerd`
process. All other requests (including Vite HMR and static assets) stay on the Vite dev server.

## Environment Variables and Secrets

Local secrets and vars are read from `.dev.vars` (same as `wrangler dev`):

```
# .dev.vars
API_SECRET=localvalue
STRIPE_KEY=sk_test_...
```

These are available as `env.API_SECRET` inside the Worker. The `.dev.vars` file is gitignored by
Wrangler's scaffolding; verify your `.gitignore` includes it.

## TypeScript Types for Bindings

Generate binding types with:

```bash
pnpm wrangler types
```

This writes `worker-configuration.d.ts` to the project root with a typed `Env` interface. Commit
this file so CI and other contributors get accurate types without running the command first.

## Running the Dev Server

```bash
pnpm vite dev
# or: pnpm vite
```

Output:

```
  VITE v5.x.x  ready in 420 ms

  ➜  Local:   http://localhost:5173/
  ➜  Network: use --host to expose
  [cloudflare] Worker "my-worker" running on workerd v1.x
```

The Worker hot-reloads on save. Unlike `wrangler dev`, there is no separate port for the Worker —
everything flows through the single Vite port.

## Build for Production

The production build uses `vite build`, which the plugin hooks into to bundle the Worker with
`esbuild` (the same bundler Wrangler uses):

```bash
pnpm vite build
```

Output:
- `dist/client/` — frontend assets for serving from Workers Sites / Pages
- `dist/worker/` — Worker bundle (or wherever `wrangler.toml` points)

Deploy with:

```bash
pnpm wrangler deploy
```

## Monorepo Configuration

In a pnpm monorepo, keep the Vite config at the app package root and ensure that `wrangler.toml`
is co-located or its path is specified:

```
apps/
  web/
    vite.config.ts
    wrangler.toml
    src/
      worker.ts
      client/
        main.tsx
```

Add a `build` script in the app's `package.json`:

```json
{
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "wrangler dev"
  }
}
```

Turborepo pipeline:

```json
{
  "tasks": {
    "dev": { "cache": false, "persistent": true },
    "build": { "dependsOn": ["^build"], "outputs": ["dist/**"] }
  }
}
```

## Anti-patterns

**Running `wrangler dev` alongside `vite dev` separately** — the two dev servers conflict on ports
and create two independent runtimes. Use the plugin to have a single unified dev server.

**Importing Node.js built-ins directly in the Worker** — Workers run on `workerd`, not Node.js.
Enable the `nodejs_compat` compatibility flag in `wrangler.toml` to get polyfills:
`compatibility_flags = ["nodejs_compat"]`.

**Forgetting `workerRoutes` with a frontend** — without it, every request goes to the Worker,
including Vite's HMR WebSocket, which breaks hot-reload.

**Using `process.env` in Workers** — the correct API is `env.VAR_NAME` from the `Env` binding
object. `process.env` is undefined in `workerd`.

## Gotchas

- The plugin does not support Wrangler's `services` array for multi-Worker dev. Use Service
  Bindings with separate Vite configs for each Worker and run multiple `vite dev` instances.
- D1 migrations must be run manually with `wrangler d1 migrations apply --local` before the dev
  server starts; the plugin does not auto-apply migrations.
- On Windows, `workerd` requires WSL2. Native Windows paths in `wrangler.toml` may need
  adjustment.
- `compatibility_date` in `wrangler.toml` gates which Workers APIs are available. If a new API
  does not appear, advance the date.

## Verification

```bash
# Confirm the Worker is running inside workerd (not Node.js)
curl http://localhost:5173/api/hello
# Expected: {"message":"Hello from Worker"}

# Confirm HMR still works — edit a client file and observe the browser update without refresh

# Verify binding availability
curl http://localhost:5173/api/kv-test
# Should return data from the local KV namespace
```

## Related

- `wrangler-dev-local-d1-r2-kv.md` — local binding emulation details
- `vitest-workers-miniflare-testing-setup.md` — unit testing Workers with Miniflare
- `turborepo-cloudflare-workers-pipeline.md` — build pipeline for Workers monorepos
- `typescript-cloudflare-workers-strict.md` — strict TypeScript config for Workers

## Sources

- Cloudflare `@cloudflare/vite-plugin` GitHub repository and README (2025)
- Cloudflare Workers documentation: "Use Vite" guide
- Wrangler 3 changelog — Vite plugin integration notes
- Cloudflare Developer blog: "Building full-stack apps with Vite and Workers" (2025)
