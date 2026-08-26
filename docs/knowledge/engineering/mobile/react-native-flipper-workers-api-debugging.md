# Debugging Cloudflare Workers APIs with React Native Flipper Network Inspector

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

React Native developers using Cloudflare Workers as their API backend struggle to correlate
network requests in Flipper with Workers trace IDs and KV/R2 sub-requests. Standard Flipper
network inspection shows raw fetch calls but drops Workers-specific response headers like
`CF-Ray`, `CF-Cache-Status`, and custom `X-Trace-Id` headers that are essential for debugging
edge behaviour.

## Context

Flipper's Network plugin intercepts `XMLHttpRequest` and `fetch` calls in the JS runtime via
a native module bridge. Because Workers return non-standard headers and occasionally stream
chunked responses, the default serialiser truncates or omits the debugging metadata you need.
The solution is to write a thin Workers middleware that echoes trace context into the response
body envelope, and a matching React Native fetch wrapper that forwards those fields to a custom
Flipper reporter. This approach works with both the legacy `rn-flipper-requests-inspector` and
the newer `react-native-network-logger` that ships with Expo Dev Client.

## Configuring the Workers Trace Middleware

```typescript
// workers/src/middleware/trace.ts
export interface TraceContext {
  rayId: string;
  cacheStatus: string;
  country: string | null;
  datacenter: string | null;
  durationMs: number;
}

export function withTrace<Env>(
  handler: (req: Request, env: Env, ctx: ExecutionContext) => Promise<Response>
) {
  return async (req: Request, env: Env, ctx: ExecutionContext): Promise<Response> => {
    const start = Date.now();
    const traceId = crypto.randomUUID();

    try {
      const res = await handler(req, env, ctx);
      const duration = Date.now() - start;

      // Clone so we can add headers without mutating the original
      const traced = new Response(res.body, res);
      traced.headers.set('X-Trace-Id', traceId);
      traced.headers.set('X-Duration-Ms', String(duration));
      // Expose headers to browser/native clients
      traced.headers.append(
        'Access-Control-Expose-Headers',
        'X-Trace-Id, X-Duration-Ms, CF-Ray, CF-Cache-Status'
      );
      return traced;
    } catch (err) {
      const duration = Date.now() - start;
      return Response.json(
        { error: String(err), traceId, durationMs: duration },
        { status: 500, headers: { 'X-Trace-Id': traceId } }
      );
    }
  };
}

// workers/src/index.ts
import { withTrace } from './middleware/trace';

export default {
  fetch: withTrace(async (req, env, ctx) => {
    const url = new URL(req.url);
    if (url.pathname === '/api/ping') {
      return Response.json({ ok: true, ts: Date.now() });
    }
    return new Response('Not found', { status: 404 });
  }),
};
```

## React Native Flipper Fetch Wrapper

```typescript
// src/lib/workersFetch.ts
import { addNetworkResponseHandler } from 'react-native-network-logger';

export interface WorkersResponse<T = unknown> {
  data: T;
  trace: {
    id: string;
    durationMs: number;
    ray: string;
    cacheStatus: string;
  };
}

export async function workersFetch<T>(
  url: string,
  init: RequestInit = {}
): Promise<WorkersResponse<T>> {
  const startTime = performance.now();

  const res = await fetch(url, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      ...(init.headers as Record<string, string>),
    },
  });

  const traceId = res.headers.get('X-Trace-Id') ?? 'unknown';
  const durationMs = parseFloat(res.headers.get('X-Duration-Ms') ?? '0');
  const ray = res.headers.get('CF-Ray') ?? 'unknown';
  const cacheStatus = res.headers.get('CF-Cache-Status') ?? 'MISS';

  if (!res.ok) {
    const body = await res.text();
    // Push extra metadata into Flipper via network logger
    addNetworkResponseHandler?.({
      id: traceId,
      status: res.status,
      headers: Object.fromEntries(res.headers.entries()),
      body,
      duration: performance.now() - startTime,
    });
    throw new Error(`Workers error ${res.status} [${traceId}]: ${body}`);
  }

  const data: T = await res.json();

  return {
    data,
    trace: { id: traceId, durationMs, ray, cacheStatus },
  };
}
```

## Correlating Workers Logs from Wrangler tail

```typescript
// scripts/flipper-tail-bridge.ts
// Run with: npx tsx scripts/flipper-tail-bridge.ts
// Reads `wrangler tail --format json` from stdin and prints correlated trace IDs

import * as readline from 'readline';

interface WranglerEvent {
  event: { request: { url: string; headers: Record<string, string> } };
  logs: Array<{ message: string[] }>;
  exceptions: Array<{ message: string }>;
  outcome: string;
  id?: string; // trace / ray not always present in wrangler tail
}

const rl = readline.createInterface({ input: process.stdin });

rl.on('line', (line: string) => {
  try {
    const evt: WranglerEvent = JSON.parse(line);
    const url = evt.event?.request?.url ?? '';
    const ray = evt.event?.request?.headers?.['cf-ray'] ?? 'n/a';
    const outcome = evt.outcome;

    console.log(`[FLIPPER-BRIDGE] ${outcome} | ray=${ray} | ${url}`);

    for (const log of evt.logs ?? []) {
      console.log('  log:', log.message.join(' '));
    }
    for (const ex of evt.exceptions ?? []) {
      console.error('  exception:', ex.message);
    }
  } catch {
    // non-JSON line — wrangler sometimes emits status messages
    process.stdout.write(line + '\n');
  }
});
```

## Anti-patterns

- Relying solely on `console.log` inside Workers without including the `CF-Ray` header in log
  output — the ray is the only stable cross-system correlation key between Flipper and
  Cloudflare's dashboard.
- Using `fetch` directly in React Native components instead of the `workersFetch` wrapper,
  which means Flipper never receives trace metadata even when the worker emits it.
- Setting `Access-Control-Expose-Headers: *` — the wildcard is not permitted for credentialed
  requests; enumerate each Workers header explicitly.

## Gotchas

- `performance.now()` in the React Native JS thread measures wall-clock time from the bridge
  perspective, which includes serialisation overhead; it will always be higher than the
  `X-Duration-Ms` the Worker measures server-side.
- `wrangler tail` JSON format changed in Wrangler v3.x — the `id` field was removed and
  `cf-ray` moved into request headers; always read from `event.request.headers['cf-ray']`.

## Verification

```bash
# Start the Workers dev server
npx wrangler dev --port 8787

# In a second terminal, tail logs in JSON format
npx wrangler tail --format json | npx tsx scripts/flipper-tail-bridge.ts

# From Metro bundler JS console, test the wrapper
# (paste into React Native debugger)
# workersFetch('http://localhost:8787/api/ping').then(console.log)

# Confirm CORS expose header is present
curl -si http://localhost:8787/api/ping | grep -i 'access-control-expose'
curl -si http://localhost:8787/api/ping | grep -i 'x-trace-id'
```

## Related

- `mobile/react-native-netinfo.md`
- `mobile/cloudflare-waf-false-positives-mobile-api-clients.md`
- `mobile/mobile-network-resilience-cloudflare-workers.md`

## Sources

- https://developers.cloudflare.com/workers/observability/logging/tail-workers/
- https://developers.cloudflare.com/workers/runtime-apis/response/
- https://github.com/alexbrazier/react-native-network-logger
