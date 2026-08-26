# Workers WASM Module Memory Limit Hit in Production

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare Worker serving music audio analysis (tempo detection via a Rust-compiled WASM binary) began returning 500 errors under concurrent load during a peak traffic event. Errors in `wrangler tail` showed `RuntimeError: memory access out of bounds` and requests stalled for 3-4 seconds before failing. The Worker had worked fine in staging where concurrency was low.

---

## Context

The Worker loaded a 4 MB WASM binary (compiled from Rust with `wasm-pack`) to run beat-detection on uploaded audio buffers. The binary was stored as a static asset and fetched via `fetch()` inside the request handler on every invocation. Each request compiled and instantiated the module independently. Cloudflare Workers have a hard 128 MB memory limit per isolate, and under concurrent requests in the same isolate, multiple in-flight compilations stacked memory usage past the limit. The fix was to move WASM compilation to module scope so the compiled module is shared across all requests within an isolate.

---

## What Went Wrong

```typescript
// handlers/analyze.ts — broken: module compiled per request
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const wasmResponse = await fetch(new URL('/beat-detector.wasm', request.url));
    const wasmBytes = await wasmResponse.arrayBuffer();

    // BAD: compiles a fresh 4 MB module on every request
    // Under concurrency, multiple compilations live simultaneously in the same isolate
    const wasmModule = await WebAssembly.compile(wasmBytes);
    const instance = await WebAssembly.instantiate(wasmModule, {});

    const audioBuffer = await request.arrayBuffer();
    const ptr = writeToWasmMemory(instance, audioBuffer);
    const bpm = (instance.exports.detect_bpm as CallableFunction)(ptr, audioBuffer.byteLength);

    return Response.json({ bpm });
  },
};
```

## Root Cause

`WebAssembly.compile()` is CPU- and memory-intensive. In a Cloudflare Worker isolate, multiple concurrent requests can execute in the same V8 isolate context. When each request compiled its own copy of the WASM module, the aggregate in-flight memory (each compilation holding ~30 MB during JIT) exceeded the 128 MB per-isolate cap. The error manifested as a memory access fault rather than a clean OOM error, making it hard to diagnose from logs alone. Additionally, re-fetching `beat-detector.wasm` on every request added 20-40 ms of latency per invocation even when the compilation succeeded.

## The Fix

```typescript
// handlers/analyze.ts — fixed: module compiled once at module scope
import wasmUrl from '../assets/beat-detector.wasm';

// Module-scope: compiled ONCE when the isolate is first loaded.
// All concurrent requests within this isolate share the compiled module.
const wasmModulePromise: Promise<WebAssembly.Module> = (async () => {
  // In Workers with module syntax, static WASM assets can be imported directly.
  // Alternatively, fetch + compile once and cache the result.
  const response = await fetch(wasmUrl);
  const bytes = await response.arrayBuffer();
  return WebAssembly.compile(bytes);
})();

function writeToWasmMemory(
  instance: WebAssembly.Instance,
  buffer: ArrayBuffer
): number {
  const memory = instance.exports.memory as WebAssembly.Memory;
  const view = new Uint8Array(memory.buffer);
  const ptr = (instance.exports.alloc as CallableFunction)(buffer.byteLength) as number;
  view.set(new Uint8Array(buffer), ptr);
  return ptr;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Await the shared compiled module — resolves immediately after first request
    const wasmModule = await wasmModulePromise;

    // Instantiate is cheap (no JIT recompilation); each request gets its own instance
    // so WASM linear memory is isolated per request.
    const instance = await WebAssembly.instantiate(wasmModule, {});

    const audioBuffer = await request.arrayBuffer();
    const ptr = writeToWasmMemory(instance, audioBuffer);
    const bpm = (instance.exports.detect_bpm as CallableFunction)(
      ptr,
      audioBuffer.byteLength
    );

    return Response.json({ bpm });
  },
};
```

## Prevention

```typescript
// vitest test: ensure module-scope compilation happens only once
import { describe, it, expect, vi } from 'vitest';

describe('WASM module caching', () => {
  it('compiles the module exactly once across multiple handler invocations', async () => {
    const compileSpy = vi.spyOn(WebAssembly, 'compile');

    // Simulate 10 concurrent requests
    const { default: handler } = await import('../handlers/analyze');
    const requests = Array.from({ length: 10 }, () =>
      handler.fetch(
        new Request('https://example.com/', {
          method: 'POST',
          body: new Uint8Array(1024).buffer,
        }),
        {} as Env
      )
    );

    await Promise.all(requests);
    // compile() should be called exactly once regardless of concurrency
    expect(compileSpy).toHaveBeenCalledTimes(1);
  });
});

// wrangler.toml: set memory budget alert via Analytics Engine
// Add to wrangler.toml:
// [analytics_engine_datasets]
// [[analytics_engine_datasets]]
// binding = "AE"
// dataset = "worker_metrics"
```

```typescript
// Monitoring: log memory pressure events to Analytics Engine
export default {
  async fetch(request: Request, env: Env & { AE: AnalyticsEngineDataset }): Promise<Response> {
    const wasmModule = await wasmModulePromise;
    const instance = await WebAssembly.instantiate(wasmModule, {});

    const memory = instance.exports.memory as WebAssembly.Memory;
    const usedMB = memory.buffer.byteLength / (1024 * 1024);

    // Emit data point; query via Cloudflare Analytics Engine SQL API
    env.AE.writeDataPoint({
      blobs: [request.cf?.colo ?? 'unknown'],
      doubles: [usedMB],
      indexes: ['wasm_memory_mb'],
    });

    // ... rest of handler
    return Response.json({ bpm: 0 });
  },
};
```

---

## Anti-patterns

- **Compiling WASM per request** — `WebAssembly.compile()` is expensive; doing it inside the `fetch` handler means every request pays the cost and concurrent requests stack memory usage within the same isolate.
- **Fetching the WASM binary at runtime per request** — Adds network latency and creates a failure mode if the asset origin is unavailable; prefer static imports or module-scope fetch.
- **Using `WebAssembly.instantiate(bytes)` shorthand** — This overload compiles AND instantiates in one shot with no caching opportunity; always separate `compile` (once) from `instantiate` (per request) when sharing is needed.
- **Ignoring isolate-level concurrency** — Workers can handle multiple concurrent requests in the same isolate; any module-scope side effect (like in-flight compilations) compounds across those requests.

---

## Gotchas

- `WebAssembly.instantiate(module)` (passing a compiled `WebAssembly.Module`) is cheap and safe to call per-request — each instance gets its own linear memory. Never share a `WebAssembly.Instance` across requests.
- The 128 MB limit is per isolate, not per request. Under concurrency, your effective per-request budget is `128 MB / concurrent_requests`.
- Cloudflare Workers support WASM imports natively in ES module Workers: `import wasm from './module.wasm'` gives you a pre-compiled `WebAssembly.Module` with zero runtime compilation cost — prefer this over fetch + compile.
- `wrangler tail` error messages for memory overflows can look like `RuntimeError: memory access out of bounds` rather than a clear OOM message — look for spikes in error rate correlated with concurrency metrics.
- WASM modules larger than ~1 MB trigger streaming compilation in V8; `WebAssembly.compileStreaming()` is more efficient than `compile(arrayBuffer)` because it overlaps network I/O with JIT.

---

## Verification

```bash
# Tail logs during load test to catch memory errors in real time
wrangler tail --format pretty 2>&1 | grep -i 'memory\|RuntimeError\|exceeded'

# Run a local load test with wrk (adjust URL to your Worker dev URL)
wrk -t4 -c50 -d30s --script post_audio.lua http://localhost:8787/analyze

# After deploying the fix, query Analytics Engine for memory usage
# Replace ACCOUNT_ID and DATASET_NAME with your values
curl -X POST "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/analytics_engine/sql" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"query": "SELECT AVG(_sample_interval * double1) AS avg_wasm_mb FROM worker_metrics WHERE index1 = '"'"'wasm_memory_mb'"'"' AND timestamp > NOW() - INTERVAL '"'"'1'"'"' HOUR"}'

# Confirm WASM module is imported statically (ES module Workers)
wrangler deploy --dry-run --outdir dist/
ls -lh dist/*.wasm  # should appear as a static asset, not bundled into the JS
```

---

## Related

- `lessons-workers-subrequest-fan-out-limit.md`
- `lessons-d1-import-large-csv-timeout.md`

---

## Sources

- Cloudflare Workers Limits — https://developers.cloudflare.com/workers/platform/limits/
- WebAssembly in Cloudflare Workers — https://developers.cloudflare.com/workers/runtime-apis/webassembly/
- Analytics Engine SQL API — https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- WebAssembly.compile() MDN — https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/WebAssembly/compile
