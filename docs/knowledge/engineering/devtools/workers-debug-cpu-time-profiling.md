# CPU Time Profiling and Debugging in Cloudflare Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

A Worker is throwing `Error: Worker exceeded CPU time limit` in production, or responding slowly despite low I/O latency. The team needs to:
- Identify which function or code path consumes the most CPU time
- Distinguish CPU-bound work from I/O-bound waiting
- Reproduce CPU limit errors locally before they hit production
- Correlate bundle size changes with CPU time changes

---

## Context

Cloudflare Workers enforce a **CPU time** limit (not wall-clock time):
- **Free tier**: 10 ms CPU time per request
- **Workers Paid**: 30 ms CPU time per request (configurable up to 5 minutes for Durable Objects and Workflows)

CPU time counts *only the time the V8 isolate is executing JavaScript*. Time spent waiting for `fetch()`, KV reads, or R2 operations does not count against the CPU limit.

Common CPU time offenders in Workers:
- Crypto operations on large payloads
- JSON parsing of large response bodies
- Complex regular expressions
- Unoptimised string concatenation in hot loops
- Imported libraries with heavy initialisation (run at startup, counted on first request)

Debugging tools available:
1. `console.time` / `console.timeEnd` — manual instrumentation
2. `performance.now()` — high-resolution timestamps
3. `wrangler tail` — live log streaming with CPU time metadata
4. Chrome DevTools CPU profiler via `wrangler dev --inspector-port`

---

## Solution

### 1. Manual instrumentation with console.time

```typescript
// src/handlers/transform.ts
export async function transformPayload(
    request: Request,
    env: Env,
): Promise<Response> {
    console.time("total");

    console.time("parse-body");
    const body = await request.json<Record<string, unknown>>();
    console.timeEnd("parse-body");

    console.time("validate");
    const validated = validateSchema(body);
    console.timeEnd("validate");

    console.time("transform");
    const result = applyTransforms(validated);
    console.timeEnd("transform");

    console.time("sign");
    const signed = await signResponse(result, env.SIGNING_KEY);
    console.timeEnd("sign");

    console.timeEnd("total");

    return Response.json(signed);
}
```

`console.timeEnd` emits a log line like `transform: 4.23ms`. View it in `wrangler tail` or in the Workers dashboard Logs tab.

### 2. High-resolution measurement with performance.now()

```typescript
// src/utils/profiler.ts
export interface TimingEntry {
    label: string;
    durationMs: number;
}

export class RequestProfiler {
    private entries: TimingEntry[] = [];
    private start = performance.now();

    mark(label: string): void {
        this.entries.push({
            label,
            durationMs: performance.now() - this.start,
        });
        this.start = performance.now();
    }

    summary(): Record<string, number> {
        return Object.fromEntries(
            this.entries.map((e) => [e.label, Math.round(e.durationMs * 100) / 100]),
        );
    }
}
```

```typescript
// src/index.ts
import type { Env } from "./types";
import { RequestProfiler } from "./utils/profiler";
import { parseAndValidate } from "./handlers/validate";
import { computeHash } from "./handlers/crypto";

export default {
    async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
        const profiler = new RequestProfiler();

        const body = await request.json<unknown>();
        profiler.mark("json-parse");

        const validated = parseAndValidate(body);
        profiler.mark("validate");

        const hash = await computeHash(JSON.stringify(validated));
        profiler.mark("hash");

        const response = Response.json({ hash, data: validated });
        profiler.mark("serialize");

        // Emit timing data as a structured log
        console.log(JSON.stringify({ type: "timing", ...profiler.summary() }));

        return response;
    },
} satisfies ExportedHandler<Env>;
```

### 3. wrangler tail for live profiling

```bash
# Stream live logs from production Worker
npx wrangler tail my-worker --env production

# Filter to only CPU-related events
npx wrangler tail my-worker --env production --filter '{"sampling_rate": 1}'

# Pipe to jq for structured parsing of timing logs
npx wrangler tail my-worker --env production --format json | \
  jq 'select(.logs[].message[0].type == "timing")'
```

`wrangler tail` output includes a `cpu_time_ms` field in the event envelope when the Worker runs on Workers Paid:

```json
{
  "outcome": "ok",
  "scriptName": "my-worker",
  "cpuTime": 12,
  "wallTime": 245,
  "logs": [
    { "message": [{ "type": "timing", "json-parse": 0.8, "validate": 2.1, "hash": 8.4, "serialize": 0.6 }] }
  ]
}
```

Note: `cpuTime: 12` ms vs `wallTime: 245` ms — the 233 ms difference is I/O wait (not counted against the limit).

### 4. Chrome DevTools CPU profiler via wrangler dev

```bash
# Start dev server with inspector enabled
npx wrangler dev --inspector-port 9229
```

Then in Chrome:
1. Navigate to `chrome://inspect`
2. Click "Configure" and add `localhost:9229`
3. Click "inspect" under the Worker target
4. Go to the "Performance" tab → Record → Send a request → Stop
5. The flame graph shows V8 function-level CPU time

This gives the most granular view — individual JavaScript functions rather than manually labelled sections.

### 5. Debugging `exceededCpuLimit` errors

```typescript
// src/index.ts — graceful handling of approaching CPU limit
export default {
    async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
        try {
            return await processRequest(request, env);
        } catch (err) {
            if (err instanceof Error && err.message.includes("exceeded CPU time")) {
                // Log context for post-mortem
                console.error(
                    JSON.stringify({
                        type: "cpu-limit-exceeded",
                        url: request.url,
                        method: request.method,
                        contentLength: request.headers.get("content-length"),
                    }),
                );
                return new Response("Request processing timeout", { status: 503 });
            }
            throw err;
        }
    },
} satisfies ExportedHandler<Env>;
```

CPU limit errors cannot be caught at runtime in the same isolate — V8 terminates the isolate. The pattern above catches them in the Workers runtime error boundary if they surface as thrown errors before the hard kill.

### 6. Identifying hot paths — JSON size correlation

```typescript
// src/middleware/size-guard.ts
export async function enforceBodySizeLimit(
    request: Request,
    maxBytes: number,
): Promise<Request> {
    const contentLength = Number(request.headers.get("content-length") ?? "0");

    if (contentLength > maxBytes) {
        throw new Response(
            JSON.stringify({
                error: "Payload too large",
                maxBytes,
                receivedBytes: contentLength,
            }),
            {
                status: 413,
                headers: { "content-type": "application/json" },
            },
        );
    }

    return request;
}
```

JSON parsing CPU time scales roughly linearly with payload size. If your Worker is hitting CPU limits, adding a body size guard upstream eliminates the class of attacks where large payloads exhaust CPU budget.

### 7. Bundle size vs CPU time correlation

Module initialisation (top-level `await`, class static blocks, module-level constants) runs once per isolate cold start. Bundle bloat increases cold start CPU time.

```bash
# Analyse bundle composition after each dependency update
npx wrangler deploy --dry-run --outdir dist
npx esbuild --bundle --analyze dist/index.js 2>&1 | head -50

# Or use source-map-explorer on the generated bundle
npm install --save-dev source-map-explorer
npx source-map-explorer dist/index.js
```

```typescript
// Avoid top-level expensive initialisations
// BAD — runs on cold start, counts against first-request CPU budget
const LARGE_LOOKUP = buildLookupTable(rawData); // expensive

// GOOD — lazy initialisation, amortised across requests
let lookupTable: Map<string, string> | null = null;
function getLookupTable(): Map<string, string> {
    if (!lookupTable) {
        lookupTable = buildLookupTable(rawData);
    }
    return lookupTable;
}
```

---

## Implementation Details

### CPU time vs wall time

| Metric | Counts against limit? | Measured by |
|---|---|---|
| JavaScript execution | Yes | `cpuTime` in tail logs |
| `await fetch(...)` wait | No | wall time delta |
| `await kv.get(...)` wait | No | wall time delta |
| `await crypto.subtle.digest(...)` | Yes (sync inside V8) | `cpuTime` |
| `TextEncoder.encode()` | Yes | `cpuTime` |
| Streaming response body | Partial (JS pump loop) | `cpuTime` |

### Durable Objects and CPU limits

Durable Objects (on Workers Paid) have a 30-second CPU time limit per request by default. Long-running synchronous loops inside DO methods hit this limit. Use `ctx.waitUntil` or break work into smaller chunks with `await`.

```typescript
// src/durable-objects/batch-processor.ts
export class BatchProcessor implements DurableObject {
    async fetch(request: Request): Promise<Response> {
        const items = await request.json<string[]>();

        // Process in chunks to yield control between batches
        const results: string[] = [];
        for (let i = 0; i < items.length; i += 100) {
            const chunk = items.slice(i, i + 100);
            results.push(...chunk.map(processItem));

            // Yield to the event loop between chunks
            // This does NOT pause CPU time accounting but prevents
            // blocking other microtasks
            await new Promise((r) => setTimeout(r, 0));
        }

        return Response.json(results);
    },
}
```

---

## Anti-patterns

- **Using `performance.now()` to estimate CPU time.** `performance.now()` measures wall time. During an `await fetch(...)`, it advances but CPU time does not. Use it to identify *where* time is spent, but read `cpuTime` from `wrangler tail` for the actual CPU budget consumption.
- **Leaving `console.time` calls in production permanently.** Each `console.time` call is a string map lookup in V8 and emits a log line. In high-throughput Workers, this adds measurable overhead. Gate verbose timing behind a debug flag or environment variable.
- **Importing large utility libraries for trivial operations.** A 200 KB bundle (e.g., lodash) increases cold start CPU time even if only one function from the library is used. Prefer native APIs or direct implementations.
- **Using synchronous crypto in hot paths.** `crypto.subtle.digest` is async but CPU-bound. For HMAC verification on every request, cache derived `CryptoKey` objects rather than re-importing the raw key bytes each time.

---

## Gotchas

- The `cpuTime` field in `wrangler tail` JSON output is available only on Workers Paid. Free tier tail logs omit it.
- `performance.now()` in Workers returns milliseconds since the isolate started, not since the Unix epoch. Do not compare values across different isolate instances.
- Chrome DevTools profiler over `--inspector-port` captures CPU samples in local `wrangler dev`. The local runtime (workerd) is not identical to the production runtime. CPU time proportions are representative but not numerically identical to production.
- Cold start CPU time (module initialisation) is counted against the *first request's* CPU budget in the same isolate. Subsequent requests in the same isolate do not pay the initialisation cost again.
- `setTimeout(r, 0)` in Workers does not truly yield the V8 thread — it schedules a macrotask. CPU time accounting continues. Use it to interleave microtasks, not to pause CPU consumption.

---

## Verification

```bash
# Start local dev with inspector
npx wrangler dev src/index.ts --inspector-port 9229

# Send a test request and observe timing output
curl -s http://localhost:8787/ -d '{"data": "test"}' -H 'content-type: application/json'

# Stream tail logs in JSON format to inspect cpuTime
npx wrangler tail my-worker --env production --format json | \
  jq '{cpu: .cpuTime, wall: .wallTime, outcome: .outcome}'

# Check bundle size after changes
npx wrangler deploy --dry-run --outdir dist && ls -lh dist/
```

---

## Related

- `documentation/docs/policies/devtools/workers-biome-linter-formatter.md`
- `documentation/observability/workers-structured-logging.md`
- `documentation/docs/policies/performance/workers-kv-cache-strategies.md`

---

## Sources

- https://developers.cloudflare.com/workers/platform/limits/#cpu-time
- https://developers.cloudflare.com/workers/observability/logs/workers-logs/
- https://developers.cloudflare.com/workers/wrangler/commands/#tail
- https://developers.cloudflare.com/workers/runtime-apis/performance/
- https://developers.cloudflare.com/workers/testing/local-development/
