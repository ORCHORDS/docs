# workerd Runtime for Local Development

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to run a Cloudflare Worker locally in the *exact* same V8 isolate environment as production — not Node.js, not a simulated environment — to debug a runtime-specific issue, profile hot code paths, or wire together multiple service-binding Workers without going through `wrangler dev`'s HTTP layer. You want to control the runtime configuration directly via a capnp config file.

## Context

`workerd` is the open-source C++ runtime that Cloudflare uses in production. It hosts V8 isolates, implements the Workers API surface (fetch, KV stubs, service bindings, etc.), and compiles via capnproto configuration files. Wrangler's `dev` command is itself a Node.js wrapper around `workerd`; using `workerd` directly removes that abstraction layer.

Workerd is useful for:
- Investigating bugs that reproduce in `workerd` but not in Node-based test environments.
- Running performance profiles with V8's built-in sampling profiler.
- Composing multi-Worker service topologies locally.
- Embedding the runtime in custom CI tooling without the full Wrangler dependency.

## Solution

```bash
# Install workerd via npm (ships a prebuilt binary for Linux/macOS/Windows)
npm install --save-dev workerd
# or globally
npm install -g workerd

# Verify installation
npx workerd --version
```

```capnp
# config/workerd.capnp  — capnproto configuration for local dev
# capnp schema: https://github.com/cloudflare/workerd/blob/main/src/workerd/server/workerd.capnp

using Workerd = import "/workerd/workerd.capnp";

const config :Workerd.Config = (
  services = [
    # ── Main API Worker ──────────────────────────────────────────────────
    ( name = "api-worker",
      worker = (
        compatibilityDate = "2024-09-23",
        compatibilityFlags = ["nodejs_compat"],
        modules = [
          ( name = "worker", esModule = embed "../../dist/index.js" )
        ],
        bindings = [
          ( name = "ENVIRONMENT", text = "local" ),
          ( name = "AUTH_SERVICE", service = "auth-worker" ),
          ( name = "MY_KV",        kvNamespace = "kv-store" ),
        ],
      )
    ),

    # ── Auth service Worker (service binding target) ─────────────────────
    ( name = "auth-worker",
      worker = (
        compatibilityDate = "2024-09-23",
        modules = [
          ( name = "worker", esModule = embed "../../dist/auth.js" )
        ],
        bindings = [
          ( name = "JWT_SECRET", text = "local-dev-secret" ),
        ],
      )
    ),

    # ── KV namespace backed by a local directory ─────────────────────────
    ( name = "kv-store",
      disk = ( path = ".workerd-kv", writable = true )
    ),

    # ── Network socket exposed to localhost ──────────────────────────────
    ( name = "internet",
      network = ( allow = ["public"], deny = [] )
    ),
  ],

  sockets = [
    ( name = "http",
      address = "localhost:8787",
      http = (),
      service = "api-worker"
    ),
  ],
);
```

```typescript
// src/index.ts  — Worker that uses an AUTH_SERVICE service binding
export interface Env {
  ENVIRONMENT:  string;
  AUTH_SERVICE: Fetcher;   // service binding
  MY_KV:        KVNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Verify token via the auth service binding (zero-overhead local RPC)
    const authRes = await env.AUTH_SERVICE.fetch(
      new Request('http://auth/verify', {
        method:  'POST',
        headers: request.headers,
      }),
    );
    if (!authRes.ok) return new Response('Unauthorized', { status: 401 });

    const cached = await env.MY_KV.get('greeting');
    return Response.json({
      env:      env.ENVIRONMENT,
      greeting: cached ?? 'Hello, world!',
    });
  },
};
```

```typescript
// scripts/run-workerd.ts  — spawn workerd from Node.js for programmatic control
import { spawn, type ChildProcess } from 'node:child_process';
import * as path from 'node:path';

const WORKERD_BIN = path.resolve(
  'node_modules/.bin/workerd',
);

const CONFIG_PATH = path.resolve('config/workerd.capnp');

export async function startWorkerd(): Promise<ChildProcess> {
  const proc = spawn(
    WORKERD_BIN,
    [
      'serve',
      CONFIG_PATH,
      '--watch',           // restart on config or script file changes
      '--verbose',         // log request/response lifecycle events
    ],
    {
      stdio: ['ignore', 'inherit', 'inherit'],
      env:   { ...process.env },
    },
  );

  // Wait for workerd to be ready
  await waitForPort(8787);
  return proc;
}

async function waitForPort(port: number, timeoutMs = 10_000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`http://localhost:${port}/__health`);
      if (res.status < 500) return;
    } catch {
      // not ready yet
    }
    await new Promise((r) => setTimeout(r, 100));
  }
  throw new Error(`workerd did not start on port ${port} within ${timeoutMs}ms`);
}

export function stopWorkerd(proc: ChildProcess): void {
  proc.kill('SIGTERM');
}
```

```typescript
// scripts/profile-workerd.ts  — capture a V8 CPU profile from workerd
// workerd exposes an Inspector (Chrome DevTools Protocol) endpoint
// when launched with --inspector-addr
import WebSocket from 'ws';
import * as fs from 'node:fs';

async function captureProfile(
  inspectorUrl: string,
  durationMs:   number,
  outPath:       string,
): Promise<void> {
  const ws = new WebSocket(inspectorUrl);

  await new Promise<void>((resolve) => ws.once('open', resolve));

  const send = (method: string, params: Record<string, unknown> = {}) =>
    new Promise<unknown>((resolve) => {
      const id = Math.random();
      ws.send(JSON.stringify({ id, method, params }));
      ws.on('message', function handler(raw: Buffer) {
        const msg = JSON.parse(raw.toString());
        if (msg.id === id) {
          ws.off('message', handler);
          resolve(msg.result);
        }
      });
    });

  await send('Profiler.enable');
  await send('Profiler.setSamplingInterval', { interval: 100 });   // μs
  await send('Profiler.start');

  // Drive load while profiling (replace with your actual load script)
  await new Promise((r) => setTimeout(r, durationMs));

  const { profile } = (await send('Profiler.stop')) as { profile: unknown };
  fs.writeFileSync(outPath, JSON.stringify(profile, null, 2));
  ws.close();
  console.log(`Profile saved to ${outPath}`);
  console.log(`Open in Chrome DevTools: about:blank → Performance → Load profile`);
}

// Usage:
// npx workerd serve config/workerd.capnp --inspector-addr=localhost:9229
// npx tsx scripts/profile-workerd.ts
captureProfile('ws://localhost:9229/json', 5_000, 'profile.cpuprofile');
```

```bash
# Makefile targets for workerd-based local dev

# Start workerd with file watching
dev:
    npx workerd serve config/workerd.capnp --watch

# Start with inspector for profiling
dev-inspect:
    npx workerd serve config/workerd.capnp \
      --inspector-addr=localhost:9229 \
      --watch

# Validate the capnp config without starting the server
validate:
    npx workerd compile config/workerd.capnp

# Clean local KV storage
clean-state:
    rm -rf .workerd-kv
```

## Implementation Details

**capnp config format.** workerd's configuration is a [Cap'n Proto](https://capnproto.org) schema compiled at startup. The `embed` keyword inlines a file's bytes into the config at start time; workerd resolves paths relative to the `.capnp` file. You can also use `esModule = (code = "...")` to inline code as a string for trivial shims.

**Service bindings locally.** Services listed in the `services` array can reference each other by name in `bindings` using `service = "<name>"`. This is how multi-Worker architectures are tested locally without HTTP. The RPC is in-process — latency is sub-millisecond.

**Disk-backed KV.** workerd's `disk` service provides a filesystem-backed key-value store that maps KV `put`/`get` operations to files under the specified `path`. This is not the same as a real KV replication; it's useful for persisting state across workerd restarts during local development.

**Performance profiling.** Launch with `--inspector-addr=localhost:9229` to expose the Chrome DevTools Protocol endpoint. Connect from Chrome DevTools, VS Code's "Attach to Node" debug config (which also supports CDP), or a custom script using the CDP WebSocket protocol. The `Profiler.start`/`stop` calls return a `.cpuprofile` file loadable in the Chrome Performance tab.

**Differences from production runtime.** workerd running locally *is* the production runtime binary, so behavioral parity is very high. Key differences:
- No real KV replication, Durable Object persistence, or R2 object storage. Use Miniflare (which also wraps workerd) for those.
- No real Cache API persistence between requests.
- The `--watch` flag does a full Worker reload, not a hot-module replacement. Brief request-failure windows are expected during reloads.
- Platform metadata headers (`cf-ipcountry`, `cf-ray`, etc.) are absent or contain placeholder values.

## Anti-patterns

- **Checking in `.workerd-kv/` to git.** This directory contains local state files. Add it to `.gitignore`.
- **Using absolute paths in `embed`.** workerd resolves `embed` paths relative to the `.capnp` file. Use relative paths to keep the config portable across machines.
- **Running `wrangler dev` and `workerd serve` on the same port simultaneously.** Both default to port 8787. Use `--port` on one of them or set different ports in the capnp `address` field.
- **Expecting capnp syntax errors to be descriptive.** workerd's error messages for malformed `.capnp` files can be terse. Run `npx workerd compile config.capnp` (compile-only mode) to catch config errors before starting.

## Gotchas

- The `workerd` npm package ships a platform-specific binary (~30 MB). On Apple Silicon, ensure Rosetta is not involved: `file $(which workerd)` should report `arm64`, not `x86_64`.
- `--watch` tracks files referenced by `embed` in the capnp config. Files imported by your bundle that are *not* embedded (e.g., `.env` files read at build time) will not trigger a reload — you must trigger a rebuild via your build watcher separately.
- workerd exits with code `1` and logs `"workerd: error: failed to start"` if the bound port is already in use. Check for stale workerd or wrangler processes with `lsof -i :8787`.
- The Inspector CDP endpoint (`/json`) returns a list of inspectable targets. If you see an empty array, the Worker has not yet received a request (the isolate is lazy-initialized). Send one request first, then connect the profiler.

## Verification

```bash
# Validate config
npx workerd compile config/workerd.capnp && echo "Config OK"

# Start and smoke-test
npx workerd serve config/workerd.capnp &
sleep 1
curl -s http://localhost:8787/ | jq .

# Confirm service binding resolves
curl -s -X POST \
  -H 'Authorization: Bearer test-token' \
  http://localhost:8787/protected-route

# Profile: start with inspector, send 1000 requests, capture profile
npx workerd serve config/workerd.capnp --inspector-addr=localhost:9229 &
sleep 1
ab -n 1000 -c 10 http://localhost:8787/
# Then run: npx tsx scripts/profile-workerd.ts
```

## Related

- `documentation/categories/devtools/workers-miniflare-integration-testing.md` — Miniflare wraps workerd for testing with mock bindings
- `documentation/categories/devtools/workers-wrangler-custom-builds.md` — producing the `dist/index.js` workerd loads
- workerd GitHub: https://github.com/cloudflare/workerd

## Sources

- https://github.com/cloudflare/workerd/blob/main/README.md
- https://github.com/cloudflare/workerd/blob/main/src/workerd/server/workerd.capnp
- https://developers.cloudflare.com/workers/testing/local-development/
- https://chromedevtools.github.io/devtools-protocol/v8/Profiler/
