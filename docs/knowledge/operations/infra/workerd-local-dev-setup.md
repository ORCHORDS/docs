# Workerd Local Development Environment Setup

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Cloudflare Workers behave differently from Node.js. Code that runs fine with `node` or
`ts-node` can silently fail or produce different results inside the actual Workers runtime
because Workers expose a subset of the Web Platform APIs rather than the Node.js standard
library. Relying on a pure-Node local dev loop means you only discover runtime divergence
at deploy time — often in production.

`workerd` is the open-source C++ runtime that Cloudflare runs your Workers code on. By
running `workerd` locally you get byte-for-byte parity with the cloud environment: the same
V8 version, the same API surface, and the same limits. This article covers standing up a
`workerd`-backed local environment from scratch, both through `wrangler dev` (the quick
path) and by driving `workerd` directly (the surgical path for debugging and integration
tests).

## Context

Prior to wrangler 3 (released mid-2023), `wrangler dev` ran your code in a Node.js sandbox
that shimmed Workers APIs. That approach accumulated a long tail of subtle divergences.
Since wrangler 3, `wrangler dev` embeds `workerd` via the `miniflare` v3 layer; the binary
is downloaded automatically on first use and pinned to the compatibility date you declare in
`wrangler.toml`.

`workerd` can also be run as a standalone daemon — useful when you need to spin up a
persistent local server for integration tests, benchmark harnesses, or multi-service local
meshes that `wrangler dev` does not expose.

The `workerd` binary is published on GitHub Releases under
`cloudflare/workerd` and is also available as an npm package (`workerd`) so it can be
installed into a project's `devDependencies`.

## Quick path — wrangler dev

The simplest local runtime is just:

```bash
npx wrangler dev
# or with explicit compatibility date
npx wrangler dev --compatibility-date 2026-06-01
```

`wrangler dev` accepts the same flag set as `wrangler deploy`, so bindings declared in
`wrangler.toml` (KV, R2, D1, Queues, Durable Objects, etc.) are available locally via
local stubs backed by in-memory or on-disk stores.

### Binding stubs in local mode

```toml
# wrangler.toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2026-06-01"

[[kv_namespaces]]
binding = "MY_KV"
id = "abc123"

[[r2_buckets]]
binding = "MY_BUCKET"
bucket_name = "my-bucket"

[[d1_databases]]
binding = "DB"
database_id = "def456"
database_name = "my-db"
```

Run `wrangler dev --local` to force all bindings to use local persistent state
(default since wrangler 3.x). Local state lands in `.wrangler/state/` and survives
restarts. To wipe it: `rm -rf .wrangler/state`.

### Remote bindings in dev mode

When local stubs are not faithful enough — for example, your D1 schema has triggers that
differ from the SQLite stub — you can point individual bindings at the real Cloudflare
resource while keeping the Worker local:

```toml
# wrangler.toml [env.dev] override — or pass flags:
# wrangler dev --remote
```

Use `--remote` sparingly: it consumes real API quota and can accidentally mutate
production data if the wrong bindings are resolved.

## Standalone workerd daemon

### Install

```bash
# Via npm (recommended for CI reproducibility)
npm install --save-dev workerd
# Binary path: node_modules/.bin/workerd

# Or download the release binary directly
curl -Lo workerd https://github.com/cloudflare/workerd/releases/download/v1.20250610.0/workerd-linux-64
chmod +x workerd
```

### Configuration format

`workerd` uses a Cap'n Proto-based config file. The syntax looks like structured
assignment blocks:

```capnp
# local-dev.capnp
using Workerd = import "/workerd/workerd.capnp";

const config :Workerd.Config = (
  services = [
    ( name = "main",
      worker = .myWorker ),
  ],

  sockets = [
    ( name = "http",
      address = "*:8787",
      http = (),
      service = "main" ),
  ]
);

const myWorker :Workerd.Worker = (
  modules = [
    (name = "worker", esModule = embed "dist/index.js"),
  ],
  compatibilityDate = "2026-06-01",
  bindings = [
    ( name = "MY_SECRET", text = "local-secret-value" ),
  ]
);
```

Start it:

```bash
workerd serve local-dev.capnp
# Listening on http://127.0.0.1:8787
```

### Multi-service local mesh

When you have Worker A calling Worker B via service bindings, model both in one
`workerd` config:

```capnp
const config :Workerd.Config = (
  services = [
    ( name = "api",   worker = .apiWorker ),
    ( name = "auth",  worker = .authWorker ),
  ],
  sockets = [
    ( name = "http", address = "*:8787", http = (), service = "api" ),
  ]
);

const apiWorker :Workerd.Worker = (
  modules = [ (name = "worker", esModule = embed "dist/api.js") ],
  compatibilityDate = "2026-06-01",
  bindings = [
    ( name = "AUTH_SERVICE",
      service = ( name = "auth" ) ),
  ]
);

const authWorker :Workerd.Worker = (
  modules = [ (name = "worker", esModule = embed "dist/auth.js") ],
  compatibilityDate = "2026-06-01",
);
```

This is useful for integration tests that span multiple Workers without a Cloudflare
account.

## Integration test harness

Combine workerd with a test runner for reliable CI:

```typescript
// vitest.config.ts
import { defineConfig } from "vitest/config";
import { unstable_dev } from "wrangler";

export default defineConfig({
  test: {
    globalSetup: "./test/setup.ts",
  },
});

// test/setup.ts
import { unstable_dev } from "wrangler";
import type { UnstableDevWorker } from "wrangler";

let worker: UnstableDevWorker;

export async function setup() {
  worker = await unstable_dev("src/index.ts", {
    experimental: { disableExperimentalWarning: true },
    local: true,
    persist: false,          // fresh state per test run
  });
  (globalThis as any).__WORKER__ = worker;
}

export async function teardown() {
  await worker.stop();
}

// test/handler.test.ts
import { describe, it, expect } from "vitest";

describe("GET /health", () => {
  it("returns 200", async () => {
    const worker = (globalThis as any).__WORKER__;
    const resp = await worker.fetch("http://localhost/health");
    expect(resp.status).toBe(200);
  });
});
```

Run with: `npx vitest run`

## Compatibility date management

The compat date governs which V8 flags and API deprecations are active. Mismatches
between local and deployed compat dates cause subtle failures.

| Strategy                | Command                                      | Risk                          |
|-------------------------|----------------------------------------------|-------------------------------|
| Pin to wrangler.toml    | `wrangler dev` (default)                     | Low — matches deploy config   |
| Override for testing    | `wrangler dev --compatibility-date 2026-07-01` | Test future flags early      |
| Force old compat date   | `wrangler dev --compatibility-date 2022-01-01` | Reveal legacy flag effects   |

Keep `compatibility_date` in `wrangler.toml` under version control. Update it
deliberately, not automatically.

## Anti-patterns

- Running workers code with plain `node src/index.js` for local dev — Node.js globals
  (`process`, `Buffer`, `require`, `__dirname`) are absent in workerd; you get misleading
  errors or silent undefined behavior.
- Using `--remote` for routine local dev — latency is high and you can mutate live data.
- Checking `.wrangler/state/` into git — it contains generated local DB files and can be
  hundreds of MB.
- Ignoring the `compatibilityDate` — workers behavior changes between dates; always
  match local to production.
- Using `workerd` directly for everyday iteration — it requires a build step; prefer
  `wrangler dev` with `--watch` for hot-reload.

## Gotchas

- `workerd` downloads a platform-specific binary at install time. In CI, install
  `workerd` in the same step as your other `devDependencies` and rely on npm/pnpm cache
  to avoid re-downloading on every run.
- Durable Objects in local mode use SQLite on disk inside `.wrangler/state/v3/do/`. The
  SQLite schema differs from Cloudflare's Durable Object storage and does not support
  point-in-time restore.
- Queues are not fully emulated locally; you can enqueue messages but the consumer is
  not automatically triggered. Call `wrangler queues consume` or trigger via HTTP for
  local testing.
- Service bindings between workers in `wrangler dev` only work if all services are
  listed under `services` in `wrangler.toml` (or via `--config` multi-worker config).
- On Apple Silicon, the `workerd` binary is x86_64 running under Rosetta 2. Performance
  is lower than on native x86 CI; don't use local benchmarks to predict cloud throughput.

## Verification

After `wrangler dev` starts, confirm the runtime by inspecting the version header:

```bash
curl -s http://127.0.0.1:8787/__health | jq .
# Your own health endpoint

# Confirm workerd version matches what wrangler expects:
npx wrangler --version
# wrangler 3.x.y (workerd 1.20250610.0)
```

For the standalone daemon, hit the socket and verify no Node.js globals are present:

```bash
curl -s http://127.0.0.1:8787/debug-env
# Should return 404 or your handler — not "process is not defined"
```

Run `npm test` (vitest / jest with `unstable_dev`) to confirm all bindings resolve
and handlers behave identically to production.

## Related

- wrangler-toml-multi-environment-config.md
- wrangler-deploys.md
- keda-cloudflare-queue-consumers.md
- cloudflare-workers-limits-resource-planning.md

## Sources

- https://github.com/cloudflare/workerd
- https://developers.cloudflare.com/workers/wrangler/commands/#dev
- https://developers.cloudflare.com/workers/testing/vitest-integration/
- https://miniflare.dev/
- https://blog.cloudflare.com/workerd-open-source-workers-runtime/
