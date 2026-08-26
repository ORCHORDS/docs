# WebAssembly-Based Edge Plugin Architecture

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

You run a SaaS platform on Cloudflare Workers and want to let customers extend your platform's
behaviour: custom transformation logic for API responses, tenant-specific validation rules, or
bespoke request routing. You need a plugin system that:

1. Executes customer-supplied code with hard isolation guarantees (a tenant's plugin must not
   read another tenant's data or exhaust the platform's CPU budget).
2. Requires no process or container boundary per plugin — the overhead of spawning a new
   isolate or container per invocation is too high at edge scale.
3. Supports plugins written in multiple languages (TypeScript, Rust, Go, Python via Wasm targets).

WebAssembly satisfies all three constraints. A Wasm module runs inside the existing Workers
isolate with a memory sandbox, a deterministic execution model, capability-based I/O (no
arbitrary network or file-system access), and microsecond startup time. Cloudflare's
`WebAssembly` global is available in every Worker with no additional configuration.

---

## Context

**WebAssembly (Wasm) inside Workers** runs in the same V8 isolate as your Worker JavaScript.
There is no separate process. The Wasm module shares the isolate's CPU budget and is subject to
the same 10 ms–30 ms CPU time limit. Wasm modules access the host environment only through
explicitly exported/imported functions — this is the capability model.

**WebAssembly Component Model** (WASI 0.2, enabled in Workers via the `nodejs_compat_v2` flag
or by bundling with `wasm-bindgen`) defines a higher-level interface: WIT (WebAssembly Interface
Types) lets you describe host–plugin contracts in a language-neutral schema, compiled to efficient
binary bindings. This is the basis of the plugin architecture described here.

**Threat model**: a malicious tenant plugin can:
- Exhaust CPU budget (mitigated by per-plugin CPU limits using `setInterval`-based watchdogs or
  by capping Wasm execution time using the Wasm timeout API)
- Consume linear memory (mitigated by setting `maximumMemory` on the `WebAssembly.Memory`)
- Attempt to access other tenants' data (mitigated by capability injection — the plugin only
  receives handles to its own tenant's data)

---

## 1. Loading and Caching Wasm Modules from R2

Tenant plugins are stored as compiled `.wasm` files in R2. The platform Worker fetches and
compiles the module once per isolate lifetime using `WebAssembly.compileStreaming`, then caches
the `WebAssembly.Module` in the module-scope cache (which persists for the lifetime of the
isolate).

```typescript
// platform/src/plugin-loader.ts
import type { Env } from './env';

// Module-scope cache: lives for the lifetime of the isolate (minutes to hours)
const moduleCache = new Map<string, WebAssembly.Module>();

export async function loadPlugin(
  tenantId: string,
  pluginId: string,
  env: Env
): Promise<WebAssembly.Module> {
  const cacheKey = `${tenantId}:${pluginId}`;
  const cached = moduleCache.get(cacheKey);
  if (cached) return cached;

  const r2Key = `plugins/${tenantId}/${pluginId}.wasm`;
  const obj = await env.PLUGINS_BUCKET.get(r2Key);
  if (!obj) throw new Error(`Plugin not found: ${r2Key}`);

  // WebAssembly.compileStreaming requires a Response with correct Content-Type
  const response = new Response(obj.body, {
    headers: { 'Content-Type': 'application/wasm' },
  });

  const wasmModule = await WebAssembly.compileStreaming(response);
  moduleCache.set(cacheKey, wasmModule);
  return wasmModule;
}

/**
 * Invalidate cache entry when a tenant deploys a new plugin version.
 * Called by the platform's plugin management Worker on deploy.
 */
export function invalidatePlugin(tenantId: string, pluginId: string): void {
  moduleCache.delete(`${tenantId}:${pluginId}`);
}
```

Compilation is the expensive step (~1–5 ms for a typical plugin). Instantiation (creating a
`WebAssembly.Instance` from a compiled module) is cheap (~0.05 ms) and is done per-request.

---

## 2. Plugin Host Interface — Capability Injection

The plugin's Wasm module imports host functions declared in a WIT interface. The platform
provides only the capabilities each plugin is allowed to use. The implementation below uses
a simple import-based contract without the full Component Model toolchain (compatible with
any Wasm target that exports a `transform` function).

```typescript
// platform/src/plugin-host.ts
export interface TransformInput {
  body: string;      // JSON-encoded request/response body
  headers: Record<string, string>;
  tenantId: string;
}

export interface TransformOutput {
  body: string;
  headers: Record<string, string>;
  status?: number;
}

export interface PluginInstance {
  transform(inputPtr: number, inputLen: number): number; // returns output ptr (null-terminated)
  alloc(size: number): number;       // request linear memory from the plugin
  dealloc(ptr: number): void;        // release memory
  memory: WebAssembly.Memory;
}

/**
 * Create a scoped import object for a tenant plugin.
 * The plugin gets ONLY these capabilities — nothing else.
 */
function buildImports(
  tenantId: string,
  env: Env
): WebAssembly.Imports {
  return {
    env: {
      // Allow plugin to read tenant KV (read-only, tenant-scoped)
      kv_get: async (keyPtr: number, keyLen: number, mem: WebAssembly.Memory): Promise<number> => {
        const key = readString(mem, keyPtr, keyLen);
        const value = await env.TENANT_KV.get(`${tenantId}:${key}`);
        if (!value) return 0; // null sentinel
        // Write value into plugin's linear memory and return pointer
        return writeString(mem, value);
      },
      // Allow plugin to log (rate-limited, tenant-prefixed)
      log: (level: number, msgPtr: number, msgLen: number, mem: WebAssembly.Memory): void => {
        const msg = readString(mem, msgPtr, msgLen);
        console.log(`[plugin:${tenantId}:${level}]`, msg.slice(0, 500));
      },
      // Explicitly NOT provided: network fetch, storage write, cross-tenant KV
    },
  };
}

function readString(memory: WebAssembly.Memory, ptr: number, len: number): string {
  const bytes = new Uint8Array(memory.buffer, ptr, len);
  return new TextDecoder().decode(bytes);
}

function writeString(memory: WebAssembly.Memory, value: string): number {
  // This is a simplified example — real implementation uses the plugin's alloc()
  const encoded = new TextEncoder().encode(value);
  // In practice: call plugin.alloc(encoded.length), then write into memory.buffer
  return 0; // placeholder
}
```

---

## 3. Per-Request Plugin Invocation with CPU Budgeting

Each request instantiates the pre-compiled module, runs the plugin, and enforces a CPU time
limit using a `Promise.race` with a timeout signal.

```typescript
// platform/src/plugin-runner.ts
import { loadPlugin } from './plugin-loader';

const PLUGIN_CPU_TIMEOUT_MS = 5; // maximum 5 ms CPU for a plugin

export async function runTransformPlugin(
  request: Request,
  tenantId: string,
  pluginId: string,
  env: Env,
  ctx: ExecutionContext
): Promise<Response> {
  const wasmModule = await loadPlugin(tenantId, pluginId, env);

  // Instantiate per-request (cheap — ~0.05 ms)
  const instance = await WebAssembly.instantiate(wasmModule, buildImports(tenantId, env));
  const exports = instance.exports as unknown as PluginInstance;

  // Serialize the input
  const input: TransformInput = {
    body: await request.text(),
    headers: Object.fromEntries(request.headers.entries()),
    tenantId,
  };
  const inputJson = JSON.stringify(input);
  const inputEncoded = new TextEncoder().encode(inputJson);

  // Write input into plugin's linear memory
  const inputPtr = exports.alloc(inputEncoded.byteLength);
  const memView = new Uint8Array(exports.memory.buffer, inputPtr, inputEncoded.byteLength);
  memView.set(inputEncoded);

  // Invoke the plugin with a timeout guard
  const transformPromise = Promise.resolve().then(
    () => exports.transform(inputPtr, inputEncoded.byteLength)
  );

  const timeoutPromise = new Promise<never>((_, reject) =>
    setTimeout(() => reject(new Error(`Plugin ${pluginId} exceeded CPU budget`)), PLUGIN_CPU_TIMEOUT_MS)
  );

  let outputPtr: number;
  try {
    outputPtr = await Promise.race([transformPromise, timeoutPromise]);
  } catch (err) {
    // Plugin timed out or crashed — return original request, log the failure
    console.error(`Plugin ${pluginId} error for tenant ${tenantId}:`, err);
    ctx.waitUntil(reportPluginError(tenantId, pluginId, (err as Error).message, env));
    return fetch(request); // passthrough on plugin failure
  } finally {
    exports.dealloc(inputPtr);
  }

  // Read the output from plugin memory
  const outputView = new Uint8Array(exports.memory.buffer, outputPtr);
  const nullTerminator = outputView.indexOf(0);
  const outputJson = new TextDecoder().decode(outputView.slice(0, nullTerminator));
  exports.dealloc(outputPtr);

  const output: TransformOutput = JSON.parse(outputJson);
  return new Response(output.body, {
    status: output.status ?? 200,
    headers: output.headers,
  });
}

async function reportPluginError(
  tenantId: string,
  pluginId: string,
  error: string,
  env: Env
): Promise<void> {
  await env.PLUGIN_ERROR_QUEUE.send({ tenantId, pluginId, error, at: new Date().toISOString() });
}
```

---

## 4. Plugin Deployment Pipeline

Tenant developers write plugins in Rust (or any Wasm target language) and submit them via the
platform API. The platform compiles, validates, and stores them in R2.

```bash
# Plugin development in Rust (example)
# Cargo.toml: [lib] crate-type = ["cdylib"]
cargo build --target wasm32-unknown-unknown --release

# Validate: check the Wasm binary is safe (no WASI imports, only expected imports)
wasm-validate target/wasm32-unknown-unknown/release/my_plugin.wasm

# Check for forbidden imports (e.g., networking, filesystem)
wasm-objdump -x target/wasm32-unknown-unknown/release/my_plugin.wasm \
  | grep 'Import' | grep -v 'env\.' && echo "FORBIDDEN IMPORTS FOUND" || echo "Import check passed"

# Upload via platform API
curl -X POST https://platform.example.com/api/plugins \
  -H "Authorization: Bearer ${TENANT_API_KEY}" \
  -H "Content-Type: application/wasm" \
  --data-binary @target/wasm32-unknown-unknown/release/my_plugin.wasm
```

The platform's upload Worker validates the binary before storing it:

```typescript
// plugin-upload-worker/src/index.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const wasmBytes = await request.arrayBuffer();

    // 1. Size limit (250 KB per plugin)
    if (wasmBytes.byteLength > 256 * 1024) {
      return new Response('Plugin too large (max 256 KB)', { status: 413 });
    }

    // 2. Compile to validate well-formedness
    let module: WebAssembly.Module;
    try {
      module = await WebAssembly.compile(wasmBytes);
    } catch {
      return new Response('Invalid Wasm binary', { status: 400 });
    }

    // 3. Check required exports exist
    const exports = WebAssembly.Module.exports(module);
    const exportNames = exports.map((e) => e.name);
    const requiredExports = ['transform', 'alloc', 'dealloc', 'memory'];
    const missing = requiredExports.filter((r) => !exportNames.includes(r));
    if (missing.length > 0) {
      return new Response(`Missing required exports: ${missing.join(', ')}`, { status: 400 });
    }

    // 4. Store in R2
    const tenantId = request.headers.get('x-tenant-id')!;
    const pluginId = crypto.randomUUID();
    await env.PLUGINS_BUCKET.put(`plugins/${tenantId}/${pluginId}.wasm`, wasmBytes, {
      httpMetadata: { contentType: 'application/wasm' },
      customMetadata: { tenantId, uploadedAt: new Date().toISOString() },
    });

    return new Response(JSON.stringify({ pluginId }), { status: 201 });
  },
};
```

---

## Anti-patterns

- **Caching `WebAssembly.Instance` across requests.** A Wasm instance's linear memory persists
  state between calls. If you reuse an instance, previous request data can leak into the next
  request's plugin execution. Always create a new instance per request.
- **No import validation at upload time.** A plugin that imports `wasi_snapshot_preview1.fd_write`
  (file system write) will fail at instantiation with an import error. Reject such binaries at
  upload time, not at request time.
- **Synchronous plugin execution without a CPU watchdog.** An infinite loop in a Wasm plugin
  will consume the entire Worker CPU budget and cause a 503. Implement the `Promise.race` timeout
  pattern from section 3.
- **Giving plugins access to the full KV namespace without tenant scoping.** Always prefix KV
  keys with `tenantId:` and expose only a scoped accessor to the plugin. Never pass raw KV
  bindings into the import object.
- **Storing uncompiled Wasm in KV.** KV values are limited to 25 MB but compilation is
  idempotent. Store `.wasm` in R2 (no size limit on individual objects) and cache the compiled
  `WebAssembly.Module` in the Worker's module scope.

---

## Gotchas

- **`WebAssembly.compileStreaming` requires `application/wasm` Content-Type.** R2 does not set
  this automatically. Wrap the R2 object body in a `new Response(obj.body, { headers: { 'Content-Type': 'application/wasm' } })`.
- **Linear memory growth across instantiations.** Each `WebAssembly.instantiate` call allocates
  fresh linear memory. In a high-traffic Worker that instantiates a new Wasm module per request,
  memory pressure builds within the isolate. Cap `maximumMemory` in the module's memory import
  and monitor via `performance.measureUserAgentSpecificMemory()` in local dev.
- **Wasm modules compiled with WASI (`wasm32-wasip1`) import WASI host functions** that are not
  provided by the Workers runtime. Use `wasm32-unknown-unknown` (bare Wasm) for plugin targets.
- **Wasm execution is single-threaded.** The plugin cannot spawn threads. Parallelism must come
  from running multiple plugin invocations concurrently in separate `Promise`-based tasks.

---

## Verification

```bash
# Confirm the plugin binary has no forbidden imports
wasm-objdump -x ./my_plugin.wasm | grep "^ - " | grep -v "env\."

# Verify expected exports are present
wasm-objdump -x ./my_plugin.wasm | grep Export

# Benchmark instantiation overhead
wrangler dev --local &
curl -X POST http://localhost:8787/benchmark \
  -H "x-tenant-id: test-tenant" \
  -d '{"iterations": 1000}'

# Confirm R2 key exists with correct content-type
wrangler r2 object get PLUGINS_BUCKET plugins/test-tenant/my-plugin-id.wasm \
  | head -4
```

---

## Related

- `webassembly-component-model-patterns.md`
- `edge-computing-patterns.md`
- `multi-tenancy-isolation-patterns.md`
- `caching-layers-cloudflare-workers-kv-r2.md`
- `function-as-a-service-patterns.md`
- `bulkhead-pattern.md`

---

## Sources

- Cloudflare Workers WebAssembly documentation: https://developers.cloudflare.com/workers/runtime-apis/webassembly/
- WebAssembly Component Model specification: https://component-model.bytecodealliance.org/
- Bytecode Alliance: wasm-bindgen and wasm-pack: https://rustwasm.github.io/
- "Wasm as a Universal Plugin System" — Lin Clark, Bytecode Alliance (2022)
- Cloudflare R2 documentation: https://developers.cloudflare.com/r2/
- WebAssembly Core Specification 2.0: https://webassembly.github.io/spec/core/
- "Extending the Edge" — Cloudflare Blog on Wasm in Workers
