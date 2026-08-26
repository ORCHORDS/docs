# Hot Module Replacement and Live Reload for Workers Development

- Date: 2026-08-22
- Author: example.com
- Status: production

---

## Symptom / Use-case

You're editing a Cloudflare Worker and want to see changes reflected immediately without manually restarting the dev server or refreshing the browser. The default `wrangler dev` watches files and restarts the Worker, but the process can be slow or lose in-flight state. This article covers how `wrangler dev`'s watch mode works, how to speed it up, and how to integrate Vite's Hot Module Replacement (HMR) for Workers being served through a Vite frontend.

Typical scenarios:
- Iterating quickly on Worker request-handling logic
- Developing a full-stack app where a Vite frontend talks to a local Worker backend
- Reducing the feedback loop from 5–10 seconds to under 1 second during development
- Keeping Durable Object state alive across Worker code reloads

---

## Context

Cloudflare Workers run in the V8 isolate model — there is no persistent Node.js process to hot-patch modules into. "HMR" in the traditional webpack/Vite sense (injecting updated modules without reloading) does not apply directly to Worker code. However, two complementary approaches exist:

1. **Wrangler's watch mode** — Wrangler 3+ uses esbuild's incremental builds with a file watcher. When source changes, it rebuilds only the changed entry point and sub-graphs, then hot-swaps the Worker in Miniflare without a full process restart. State held in Miniflare's in-memory Durable Object storage **persists** across reloads.

2. **Vite + `@cloudflare/vite-plugin`** — The official Vite plugin integrates Workers into Vite's dev server. Vite handles HMR for frontend assets (React, Vue, etc.) and proxies API requests to the Worker, which is served by Miniflare inside the Vite process. Frontend code gets true HMR; Worker code gets fast rebuild + re-injection.

---

## Wrangler's Built-in Watch Mode

`wrangler dev` watches source files by default. Understanding what triggers a rebuild:

```bash
# Start wrangler dev — watch mode is on by default
wrangler dev

# Verbose output to see what the file watcher detects
wrangler dev --log-level debug
```

Wrangler watches:
- The entry point specified in `wrangler.toml` (`main`)
- All files imported by the entry point (tracked by esbuild's incremental build)
- `wrangler.toml` itself (config changes trigger full restart)

Wrangler does **not** watch by default:
- Files listed in `.gitignore` (configurable)
- Static assets in `/public` (use `wrangler pages dev` for that)
- `node_modules` (expected — you reinstall, not edit)

To narrow watch scope and speed things up:

```toml
# wrangler.toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2026-01-01"

# Exclude heavy directories from the watcher
[dev]
# ip and port for local dev server
ip = "127.0.0.1"
port = 8787
# Wrangler respects .gitignore by default;
# additional patterns can be added in future wrangler versions
```

---

## Vite Plugin Integration (Full-Stack HMR)

For Workers that serve a frontend application, `@cloudflare/vite-plugin` is the recommended approach. It runs your Worker inside the same Vite dev server process:

```bash
# Install the plugin
pnpm add -D @cloudflare/vite-plugin vite
```

```typescript
// vite.config.ts
import { defineConfig } from 'vite';
import { cloudflare } from '@cloudflare/vite-plugin';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [
    react(),        // HMR for React components
    cloudflare(),   // Worker served via Miniflare inside Vite
  ],
});
```

```toml
# wrangler.toml — still required; vite-plugin reads it
name = "my-fullstack-app"
main = "src/worker/index.ts"
compatibility_date = "2026-01-01"
compatibility_flags = ["nodejs_compat"]

assets = { directory = "./dist/client" }
```

```typescript
// src/worker/index.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname.startsWith('/api/')) {
      return handleApi(request, env);
    }

    // Static assets handled by Vite in dev, Workers Assets in prod
    return env.ASSETS.fetch(request);
  }
} satisfies ExportedHandler<Env>;

async function handleApi(request: Request, env: Env): Promise<Response> {
  return Response.json({ message: 'Hello from Worker' });
}
```

```json
// package.json
{
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "wrangler dev"
  }
}
```

With this setup:
- `pnpm dev` starts Vite at `http://localhost:5173`
- React components hot-reload instantly (true HMR, no page refresh)
- Worker code rebuilds in ~200ms and re-injects without restarting Vite
- API requests from the frontend go to the Worker running in the same process

---

## Measuring and Optimizing Rebuild Speed

The rebuild time depends on your Worker's dependency graph. Profile it:

```bash
# Time a full rebuild by touching the entry point
touch src/index.ts && time wrangler dev --once

# Or use wrangler's built-in timing in verbose mode
wrangler dev --log-level debug 2>&1 | grep -E "rebuilt|bundle"
```

Key optimizations:

**1. Keep the Worker entry point lean.** Avoid importing large libraries (e.g., `zod`, `drizzle-orm`) at the top level if only a few routes use them. Use dynamic imports where supported:

```typescript
// Avoid: imports entire validation library at startup
import { z } from 'zod';

// Better for infrequent paths: dynamic import
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method === 'POST') {
      const { z } = await import('zod');
      // validate...
    }
    return new Response('OK');
  }
};
```

**2. Use esbuild's `external` for packages available in the Workers runtime.** Cloudflare Workers expose Node.js built-ins via `nodejs_compat`. Marking them external prevents bundling:

```toml
# wrangler.toml
[build]
command = ""  # wrangler uses esbuild internally, no custom build command needed

# For custom esbuild: mark node builtins external
# esbuild --bundle --external:node:* src/index.ts
```

**3. Split into multiple Workers with Service Bindings** if one module takes > 2s to rebuild. Independently-deployed Workers rebuild only when their own source changes.

---

## Preserving Durable Object State Across Reloads

Miniflare (the local runtime) persists Durable Object storage to disk in `.wrangler/state/`. This means a Worker reload does **not** wipe Durable Object data:

```bash
# Durable Object state is stored here:
ls .wrangler/state/v3/do/

# Reset all local state (useful to start fresh):
rm -rf .wrangler/state/
wrangler dev
```

```typescript
// Durable Object state survives hot reloads in local dev
export class Counter implements DurableObject {
  private count: number = 0;

  constructor(private state: DurableObjectState) {
    // storage.get() returns the persisted value even after Worker reload
    this.state.blockConcurrencyWhile(async () => {
      this.count = (await this.state.storage.get<number>('count')) ?? 0;
    });
  }

  async fetch(request: Request): Promise<Response> {
    this.count++;
    await this.state.storage.put('count', this.count);
    return Response.json({ count: this.count });
  }
}
```

---

## WebSocket Dev with Auto-Reconnect

When developing Workers that upgrade HTTP connections to WebSockets, a Worker reload disconnects all clients. Add client-side reconnect logic during development:

```typescript
// In your frontend / test client (dev only)
function connectWithReconnect(url: string) {
  let ws: WebSocket;
  let reconnectTimer: ReturnType<typeof setTimeout>;

  function connect() {
    ws = new WebSocket(url);

    ws.onopen = () => {
      console.log('[dev] WebSocket connected');
      clearTimeout(reconnectTimer);
    };

    ws.onclose = () => {
      console.log('[dev] WebSocket closed — reconnecting in 1s');
      reconnectTimer = setTimeout(connect, 1000);
    };

    ws.onerror = () => {
      ws.close();
    };

    ws.onmessage = (event) => {
      console.log('[dev] Message:', event.data);
    };
  }

  connect();
  return () => {
    clearTimeout(reconnectTimer);
    ws.close();
  };
}

// Usage
const disconnect = connectWithReconnect('ws://localhost:8787/ws');
```

---

## VS Code Integration for Watch Mode

Add a VS Code task to run `wrangler dev` as a background process that shows in the Terminal panel:

```json
// .vscode/tasks.json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "wrangler dev",
      "type": "shell",
      "command": "wrangler dev",
      "isBackground": true,
      "problemMatcher": {
        "pattern": {
          "regexp": "^(.*):(\\d+):(\\d+): (error|warning): (.*)$",
          "file": 1,
          "line": 2,
          "column": 3,
          "severity": 4,
          "message": 5
        },
        "background": {
          "activeOnStart": true,
          "beginsPattern": "^\\[wrangler:info\\] Reloading local Worker\\.\\.\\.",
          "endsPattern": "^\\[wrangler:info\\] Ready on http://"
        }
      },
      "group": "build",
      "presentation": {
        "echo": true,
        "reveal": "always",
        "focus": false,
        "panel": "dedicated"
      }
    }
  ]
}
```

Use `Ctrl+Shift+B` (Run Build Task) to start the watcher, and the output panel shows rebuild events in real time.

---

## Anti-Patterns

**Running `tsc --watch` alongside `wrangler dev`.** Wrangler runs esbuild internally which transpiles TypeScript without type checking. Running `tsc --watch` in parallel is fine for catching type errors, but outputting `.js` files to a `dist/` folder and pointing `main` at them adds a second unnecessary build step. Instead, point `main` at your `.ts` source and let Wrangler's esbuild handle transpilation.

**Using `nodemon` or `chokidar` to restart wrangler.** This adds a process-manager layer that competes with Wrangler's own watch mode, causing double rebuilds. Wrangler's built-in watcher is sufficient.

**Disabling the watcher with `--no-watch` in CI.** The `--no-watch` flag (or `--once`) is correct for CI where you want a single build, but don't add it to your dev script — it defeats the purpose.

**Importing the entire `hono` package when only routing is needed.** Hono's tree-shaking works well with esbuild, but `import * as hono from 'hono'` disables it. Use named imports: `import { Hono } from 'hono'`.

---

## Gotchas

- **Wrangler reloads on `wrangler.toml` changes**, including whitespace changes. This causes a full restart (slower than an esbuild hot-swap). Avoid saving `wrangler.toml` frequently during active dev.

- **The Vite plugin and `wrangler dev` are mutually exclusive** — don't run both simultaneously on the same project. Use Vite plugin for full-stack projects and `wrangler dev` for API-only Workers.

- **Source maps in watch mode.** Wrangler generates source maps in dev by default (`--source-map` is implied). If you see cryptic stack traces, check that your editor is pointing at `.wrangler/tmp/` where the built file lives, not the original source.

- **`--port` conflicts with Vite's default port 5173.** When using both `wrangler dev` and a frontend dev server, set `wrangler dev --port 8787` explicitly to avoid the two servers fighting over a port.

- **Compatibility date mismatches between dev and prod.** The `compatibility_date` in `wrangler.toml` controls runtime behavior. If you update it, restart `wrangler dev` — the file watcher detects the change but the updated compat date only applies after a full restart of the Miniflare runtime.

---

## Verification

```bash
# 1. Start wrangler dev
wrangler dev

# 2. Confirm the Worker serves requests
curl http://localhost:8787/
# Expected: your Worker's response

# 3. Edit src/index.ts — change a string in the response
# Expected in terminal: "[wrangler:info] Reloading local Worker..."
# Followed by: "[wrangler:info] Ready on http://localhost:8787"

# 4. Curl again — should show the changed response without restarting wrangler
curl http://localhost:8787/

# 5. Measure rebuild time
time (echo "" >> src/index.ts && curl -s http://localhost:8787/ > /dev/null)
# Typical: 0.2–0.8s for small Workers
```

---

## Related

- `vite-cloudflare-workers-dev-mode.md` — Vite plugin deep dive
- `vitest-workers-miniflare-testing-setup.md` — Testing setup with Miniflare
- `wrangler-dev-remote-d1-r2-bindings.md` — Using remote resources in dev
- `durable-objects-local-debugging.md` — Debugging DO state across reloads
- `typescript-path-aliases-workers.md` — TypeScript aliases in Workers builds

---

## Sources

- Wrangler dev documentation: https://developers.cloudflare.com/workers/wrangler/commands/#dev
- Cloudflare Vite plugin: https://developers.cloudflare.com/workers/frameworks/framework-guides/react/
- `@cloudflare/vite-plugin` npm: https://www.npmjs.com/package/@cloudflare/vite-plugin
- Miniflare state persistence: https://miniflare.dev/storage/d1
- esbuild incremental builds: https://esbuild.github.io/api/#incremental
