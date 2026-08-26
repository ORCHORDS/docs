# Workers WASM Module Caching for Startup Latency

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

WebAssembly modules compiled inside a Cloudflare Worker add 50–400 ms of cold-start latency
because every new isolate must parse and compile the `.wasm` binary from scratch.
You see P99 request latency spikes on the first request after a deployment or after an isolate
is evicted, even though subsequent warm requests are fast.

Typical victims: image-manipulation Workers (libvips/libwebp), cryptography Workers (libsodium),
parsing Workers (tree-sitter, markdown processors), and ML inference Workers (ONNX runtime Wasm).

## Context

Cloudflare Workers runs each Worker in a V8 isolate. When a new isolate starts:
1. The Worker script is parsed and evaluated.
2. Any `WebAssembly.compile()` or `new WebAssembly.Instance()` call triggers JIT compilation.
3. The compiled module is NOT automatically reused across isolates.

Cloudflare exposes two mechanisms to avoid per-isolate recompilation:
- **Top-level module instantiation** (module Workers) — compile once at script evaluation time so
  Cloudflare can cache the compiled artifact across isolate restarts on the same machine.
- **`WebAssembly.Module` as a global** — hoist the module to a `const` at module scope so V8
  snapshots the compiled form.

The Workers runtime uses the module-syntax Workers format (ESM) natively; scripts evaluated at
module scope benefit from Cloudflare's isolate reuse pool and compiled-module caching.

## 1. Anti-pattern: compile inside the request handler

```typescript
// BAD — recompiles the Wasm binary on every cold-start isolate
export default {
  async fetch(request: Request): Promise<Response> {
    const wasmBytes = await fetch("https://cdn.example.com/parser.wasm")
      .then(r => r.arrayBuffer());
    const module = await WebAssembly.compile(wasmBytes);  // cold-path cost
    const instance = await WebAssembly.instantiate(module, {});
    // ...
  }
};
```

## 2. Hoist module compilation to top-level scope

Compile the module at the module scope so Cloudflare's isolate snapshot includes the compiled
artifact. Wasm binary must be bundled via wrangler's `[wasm_modules]` binding or imported
directly as a static asset.

```typescript
// wrangler.toml
// [[wasm_modules]]
// name = "PARSER_WASM"
// path = "src/parser.wasm"

import parserWasm from "./parser.wasm";   // bundled by wrangler as a WebAssembly.Module

// Module compiled ONCE per isolate at script-evaluation time; cached across restarts
const parserModule: WebAssembly.Module = parserWasm;

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Instantiation is cheap (~1 ms) — only compilation is expensive
    const instance = await WebAssembly.instantiate(parserModule, {
      env: { memory: new WebAssembly.Memory({ initial: 16 }) }
    });
    const result = (instance.exports.parse as CallableFunction)(
      encodeInput(await request.text())
    );
    return new Response(JSON.stringify({ result }), {
      headers: { "content-type": "application/json" }
    });
  }
};
```

## 3. Reuse Wasm instances with a module-scope singleton

Instantiation itself allocates a fresh linear memory region. For stateless Wasm modules you can
reuse a single instance across requests in the same isolate.

```typescript
import parserWasm from "./parser.wasm";

interface ParserExports extends WebAssembly.Exports {
  parse: (ptr: number, len: number) => number;
  alloc: (size: number) => number;
  dealloc: (ptr: number) => void;
  memory: WebAssembly.Memory;
}

// Compiled once, instantiated once per isolate lifetime
let sharedInstance: WebAssembly.Instance | null = null;

async function getParser(): Promise<ParserExports> {
  if (!sharedInstance) {
    sharedInstance = await WebAssembly.instantiate(parserWasm, {});
  }
  return sharedInstance.exports as ParserExports;
}

export default {
  async fetch(request: Request): Promise<Response> {
    const parser = await getParser();
    const input = new TextEncoder().encode(await request.text());

    const ptr = parser.alloc(input.byteLength);
    new Uint8Array(parser.memory.buffer).set(input, ptr);
    const resultLen = parser.parse(ptr, input.byteLength);
    const result = new Uint8Array(parser.memory.buffer, ptr, resultLen);
    const output = new TextDecoder().decode(result);
    parser.dealloc(ptr);

    return new Response(output, { headers: { "content-type": "text/plain" } });
  }
};
```

## 4. wrangler.toml configuration for Wasm bindings

```toml
# wrangler.toml — bundle Wasm as a module binding (Workers ESM format)
name = "wasm-parser-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[build]
command = "tsc"

# Wasm imported this way is compiled ONCE by Cloudflare's pipeline and served
# as a pre-compiled module to each isolate — eliminating per-isolate JIT cost
[[wasm_modules]]
name = "PARSER_WASM"
path = "src/parser.wasm"
```

When wrangler bundles a `.wasm` file via `[[wasm_modules]]`, Cloudflare's upload pipeline
pre-compiles it into a platform-native artifact. Each fresh isolate receives the pre-compiled
form rather than the raw binary, cutting cold-start compilation time to near zero.

## 5. Measuring compilation cost with Worker CPU time

```typescript
import parserWasm from "./parser.wasm";

export default {
  async fetch(request: Request): Promise<Response> {
    const t0 = Date.now();
    const module = await WebAssembly.compile(
      await (await fetch(new URL("./parser.wasm", import.meta.url))).arrayBuffer()
    );
    const compileMs = Date.now() - t0;

    const t1 = Date.now();
    await WebAssembly.instantiate(module, {});
    const instantiateMs = Date.now() - t1;

    return new Response(JSON.stringify({ compileMs, instantiateMs }), {
      headers: {
        "content-type": "application/json",
        "server-timing": `wasm-compile;dur=${compileMs}, wasm-inst;dur=${instantiateMs}`
      }
    });
  }
};
```

Check `Server-Timing` headers in Cloudflare Logpush or curl output. After migrating to the
top-level binding pattern, `wasm-compile;dur` should drop to 0 on warm isolates.

## Anti-patterns

- Fetching `.wasm` from an external URL inside the handler — adds network RTT on top of
  compilation latency.
- Using `WebAssembly.instantiateStreaming()` inside a request handler without caching the module —
  streams the binary and compiles it per-request.
- Allocating a new linear memory region per request when the Wasm module is stateless — wastes
  GC pressure without correctness benefit.
- Storing the compiled `WebAssembly.Module` in Workers KV — KV round-trips exceed the latency
  you are trying to avoid; use top-level scope instead.

## Gotchas

- Module-scope singletons are per-isolate, not global. Under high concurrency, Cloudflare spawns
  multiple isolates per Worker; each pays the instantiation cost once. This is expected and
  unavoidable.
- Large Wasm binaries (>10 MB uncompressed) still incur startup latency even with pre-compilation
  because isolate memory must be loaded. Keep binaries lean; strip debug symbols.
- Wasm linear memory persists across requests in the same isolate when using a singleton instance.
  Ensure exports are re-entrant-safe or reset memory state between calls.
- The `[[wasm_modules]]` binding syntax applies to `workers_dev` and production. `wrangler dev`
  compiles locally; production compiles server-side. Benchmark latency numbers may differ.
- Workers with very large Wasm binaries may hit the 10 MB compressed Worker script size limit;
  use R2 + streaming instantiation for binaries above that threshold.

## Verification

1. Deploy before/after versions; enable Logpush with `workers_trace_events`.
2. Compare `cpuTime` field in trace events for the first request after a deployment (cold isolate).
3. Use `curl -w "%{time_starttransfer}" -o /dev/null` to measure TTFB on the first request.
4. Use Cloudflare's Worker metrics dashboard: filter by `status_code=200` and check P99 CPU ms.
5. Add `Server-Timing` headers (as shown above) to expose compile vs instantiate split in traces.

## Related

- `workers-cold-start-optimization.md`
- `webassembly-streaming-compilation-delivery-contract.md`
- `workers-cpu-time-optimization.md`
- `workers-memory-allocation-optimization.md`

## Sources

- Cloudflare Workers WASM docs: https://developers.cloudflare.com/workers/runtime-apis/webassembly/
- Cloudflare wrangler wasm_modules: https://developers.cloudflare.com/workers/wrangler/configuration/#wasm-modules
- WebAssembly Module caching: https://v8.dev/blog/wasm-code-caching
- Cloudflare Workers limits: https://developers.cloudflare.com/workers/platform/limits/
