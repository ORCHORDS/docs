# workers-nodejs-compatibility

Using the expanded Node.js compatibility layer in Cloudflare Workers. As of
Birthday Week 2025, hundreds of Node.js APIs are now available in the Workers
runtime, meaning many npm packages that previously required `nodejs_compat`
workarounds (or didn't work at all) now run natively. This article covers how
to enable compat, which APIs work, and the gotchas that still bite.

## Symptom

You're trying to use a popular npm package (e.g., a JWT library, a crypto
helper, an HTML parser, or a database driver) in a Cloudflare Worker, and you
hit one of these errors:

```text
Error: Cannot find module 'node:crypto'
Error: require is not defined
Error: process is not defined
Error: Buffer is not defined
Error: The module 'node:fs' is not available in this Workers runtime
```

Or the package installs fine but crashes at runtime because it internally
relies on a Node.js API that isn't implemented. You're stuck between "rewrite
the dependency from scratch using Web APIs" and "deploy a container instead of
a Worker."

## Background: The Node.js compat evolution

The Workers runtime was originally a pure Web-standards environment (Fetch,
Streams, Crypto.subtle, etc.). No `require`, no `Buffer`, no `process`, no
`node:*` built-in modules. This was intentional (security, startup speed) but
made a large fraction of npm unusable.

Cloudflare progressively added compatibility:

```text
2023  nodejs_compat flag → Buffer, process.env, basic node: crypto
2024  Expanded: node:stream, node:util, node:path, node:assert, more
2025  Birthday Week: hundreds more APIs, near-full Node.js compat layer
```

The compatibility is provided by `unenv` (a Node.js polyfill for edge runtimes)
and native built-in implementations of the most common `node:*` modules.

## Solution: Enable and use Node.js compat

### Step 1: Set compatibility flags in wrangler.toml

```toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2025-09-01"

# Enable Node.js compatibility
compatibility_flags = ["nodejs_compat"]
```

The `compatibility_date` must be recent enough for `nodejs_compat` to include
the expanded API set. Use a 2025 date to get the full range.

### Step 2: Import Node.js built-in modules

```typescript
// These now work with nodejs_compat enabled
import { createHash, randomBytes } from "node:crypto";
import { Buffer } from "node:buffer";
import path from "node:path";
import { Readable } from "node:stream";

export default {
  async fetch(request: Request): Promise<Response> {
    // node:crypto — createHash works (no streaming hash edge cases)
    const hash = createHash("sha256").update("hello").digest("hex");

    // Buffer — convert between formats
    const buf = Buffer.from("some data", "utf8");
    const base64 = buf.toString("base64");

    // randomBytes — CSPRNG
    const token = randomBytes(32).toString("hex");

    return Response.json({ hash, base64, token });
  },
};
```

### Step 3: Use npm packages that depend on Node APIs

```typescript
// Many popular packages now work directly:
import jwt from "jsonwebtoken";           // uses node:crypto
import Stripe from "stripe";              // uses node:crypto, Buffer
import { marked } from "marked";          // pure JS, always worked
import { JSDOM } from "jsdom";            // uses node: internals — check compat

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // jsonwebtoken now works with nodejs_compat
    const token = jwt.sign({ userId: 123 }, env.JWT_SECRET, { expiresIn: "1h" });
    return Response.json({ token });
  },
};
```

### Step 4: Handle `process.env` and globals

```typescript
// process.env works but only contains what you define in [vars] / secrets
// It does NOT contain shell environment variables from your machine.
const apiKey = process.env.API_KEY;  // reads from wrangler.toml [vars] or secrets

// process.platform, process.version are stubbed (not real)
console.log(process.platform);  // "linux" (stubbed, always)
```

## Which Node APIs work (as of late 2025)

| Module              | Status      | Notes                                    |
|---------------------|-------------|------------------------------------------|
| `node:crypto`       | Full        | createHash, createHmac, randomBytes, etc.|
| `node:buffer`       | Full        | Buffer.from, alloc, toString             |
| `node:stream`       | Full        | Readable, Writable, Transform, pipeline  |
| `node:util`         | Full        | promisify, inspect, types                |
| `node:path`         | Full        | join, resolve, parse, extname            |
| `node:url`          | Full        | parse, fileURLToPath, URL                 |
| `node:assert`       | Full        | strict and loose assertions              |
| `node:events`       | Full        | EventEmitter                             |
| `node:string_decoder`| Full       | StringDecoder                            |
| `node:zlib`         | Partial     | gzip/deflate via polyfill, not native    |
| `node:net`          | No          | Use `connect()` (TCP sockets API) instead|
| `node:http`         | Partial     | Use native `fetch()` instead             |
| `node:fs`           | No          | Workers have no filesystem               |
| `node:child_process`| No          | No process spawning (use Containers)     |
| `node:os`           | Stubbed     | Most methods return stubs                 |

## Gotchas

- **`node:fs` and `node:child_process` will NEVER work.** Workers have no
  filesystem access and cannot spawn processes. If a package imports these,
  it won't work in a Worker — period. Use Containers for filesystem/process
  needs.
- **`node:http` is polyfilled but you should use `fetch()` instead.** The
  polyfill exists for compatibility but `fetch()` is the native, optimized
  path. Packages using `http.get()` or `https.request()` may work but are
  slower and may not support all features (e.g., HTTP/2).
- **`node:net` (raw TCP) is NOT available via compat.** Use the Workers
  `connect()` API from `cloudflare:sockets` for TCP connections instead.
  Packages expecting `net.Socket` won't work directly.
- **Polyfills can increase bundle size significantly.** `nodejs_compat` adds
  the unenv polyfill layer. A Worker that was 50KB might become 200KB+. Watch
  the 3MB compressed limit for paid plans (1MB for free).
- **`process.env` is NOT populated from your shell.** It only contains vars
  defined in `wrangler.toml` `[vars]` section or Cloudflare Secrets. Don't
  expect `PATH`, `HOME`, etc. to exist.
- **`Buffer` is global with the flag, but explicit imports are safer.** With
  `nodejs_compat`, `Buffer` is available as a global. But if you bundle with
  certain tools (esbuild, Vite), explicit `import { Buffer } from "node:buffer"`
  avoids ambiguity and tree-shaking issues.
- **Some packages detect "is this Node?" and break.** Packages that check
  `typeof process !== 'undefined'` may take the Node code path and then hit
  unimplemented APIs. The compat layer makes the runtime look like Node, which
  can mislead packages into using `node:fs` when Web APIs would work.
- **`node:crypto` subtle differences from Web Crypto.** `createHash` returns
  a Node Hash object, not a Web Crypto `SubtleCrypto` digest. Don't mix the
  two APIs in the same code path — pick one (prefer Web Crypto `crypto.subtle`
  unless you need the Node API for package compatibility).
- **Performance: Node polyfills are slower than native Web APIs.** `Buffer`
  operations allocate more memory than `Uint8Array`. `node:crypto` may have
  different performance characteristics than `crypto.subtle`. Benchmark if
  performance-critical.
- **`__dirname` and `__filename` are not defined.** These are CommonJS
  concepts. Workers use ES modules. Use `import.meta.url` if you need the
  module URL, and `new URL('.', import.meta.url)` for a base path.
- **`require()` is not available unless you use the `commonjs` compat flag.**
  If you must import a CommonJS package, use a bundler (esbuild/rollup) that
  converts it to ESM at build time. Don't rely on runtime `require()`.

## When compat helps vs. when it doesn't

### Compat helps when:
- Package uses only `node:crypto`, `Buffer`, `node:stream`, `node:util`
- You need to reuse existing server-side code in a Worker
- The package has no Web-API equivalent (e.g., a specific JWT library)

### Compat won't help when:
- Package uses `node:fs` (filesystem) — use R2, KV, or Containers instead
- Package uses `node:child_process` — use Containers
- Package needs raw TCP — use `cloudflare:sockets` `connect()`
- Package is a native addon (`.node` binary) — impossible in Workers

## Sources

- [Node.js Compatibility — Workers Docs](https://developers.cloudflare.com/workers/runtime-apis/nodejs/)
- [Birthday Week 2025 — Node.js Expansion](https://www.cloudflare.com/innovation-week/birthday-week-2025/updates/)
- [nodejs_compat flag — Compatibility Dates](https://developers.cloudflare.com/workers/configuration/compatibility-dates/)
