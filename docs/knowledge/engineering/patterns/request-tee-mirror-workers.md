# Request Tee and Traffic Mirroring in Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
You want to shadow-test a new backend, collect analytics on live traffic, or run a canary comparison without altering the user-facing response. A Worker intercepts every request and forks it — the primary path returns normally while the mirror path runs fire-and-forget.

## Context
Cloudflare Workers can issue multiple subrequests per invocation (up to 1000 on the paid tier). `Request` objects are single-use by default; cloning them before dispatch is necessary. `ctx.waitUntil()` keeps the isolate alive after the primary response is sent so the mirror subrequest can complete without adding to user-perceived latency. This pattern enables dark-launch testing, A/B logging, and traffic replay without additional infrastructure.

## Cloning and Teeing a Request
`Request` bodies are single-use streams. Clone the request before reading the body for primary processing, and clone again for the mirror.

```typescript
interface Env {
  PRIMARY_BACKEND: string;
  MIRROR_BACKEND: string;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // Clone once for primary, once for mirror — cloning is O(headers) not O(body)
    const primaryReq = request.clone();
    const mirrorReq = request.clone();

    // Fire mirror asynchronously; do NOT await — it must not block the response
    ctx.waitUntil(mirrorRequest(mirrorReq, env.MIRROR_BACKEND));

    // Forward to primary and return to the client
    return fetch(new Request(env.PRIMARY_BACKEND + new URL(request.url).pathname, primaryReq));
  },
};

async function mirrorRequest(req: Request, mirrorBase: string): Promise<void> {
  try {
    const url = new URL(req.url);
    const mirrorUrl = mirrorBase + url.pathname + url.search;
    const resp = await fetch(new Request(mirrorUrl, req), { signal: AbortSignal.timeout(5000) });
    // Optionally log the status; do not surface errors to the client
    if (!resp.ok) {
      console.warn('mirror non-200', resp.status, mirrorUrl);
    }
    await resp.body?.cancel(); // Consume and discard — prevent resource leak
  } catch (err) {
    console.error('mirror failed', (err as Error).message);
  }
}
```

## Shadow Testing with Response Comparison
Log diffs between primary and shadow responses to KV or Logpush for offline analysis. Never let shadow latency affect the client.

```typescript
async function shadowCompare(
  primaryResp: Response,
  shadowResp: Response,
  requestId: string,
  env: Env,
): Promise<void> {
  const [primaryBody, shadowBody] = await Promise.all([
    primaryResp.text(),
    shadowResp.text(),
  ]);

  if (primaryBody !== shadowBody) {
    const diff = {
      requestId,
      primaryStatus: primaryResp.status,
      shadowStatus: shadowResp.status,
      primaryLength: primaryBody.length,
      shadowLength: shadowBody.length,
      match: false,
      timestamp: new Date().toISOString(),
    };
    // Write diff to KV with a short TTL for offline review
    await (env as unknown as { DIFF_LOG: KVNamespace }).DIFF_LOG.put(
      `diff:${requestId}`,
      JSON.stringify(diff),
      { expirationTtl: 86400 },
    );
  }
}

export const shadowHandler = {
  async fetch(request: Request, env: Env & { DIFF_LOG: KVNamespace }, ctx: ExecutionContext): Promise<Response> {
    const requestId = crypto.randomUUID();
    const [primaryReq, shadowReq] = [request.clone(), request.clone()];

    const primaryPromise = fetch(new Request(env.PRIMARY_BACKEND + new URL(request.url).pathname, primaryReq));
    const shadowPromise = fetch(new Request(env.MIRROR_BACKEND + new URL(request.url).pathname, shadowReq))
      .catch((): Response => new Response(null, { status: 502 }));

    const [primaryResp, shadowResp] = await Promise.all([primaryPromise, shadowPromise]);
    const [primaryForClient, primaryForCompare] = primaryResp.clone ? [primaryResp.clone(), primaryResp] : [primaryResp, primaryResp.clone()];

    ctx.waitUntil(shadowCompare(primaryForCompare, shadowResp, requestId, env));

    return primaryForClient;
  },
};
```

## Sampling-Based Mirroring
Mirror only a percentage of traffic to reduce load on the shadow backend and subrequest budget.

```typescript
function shouldMirror(sampleRate: number): boolean {
  // sampleRate: 0.0–1.0
  return Math.random() < sampleRate;
}

export const sampledMirror = {
  async fetch(request: Request, env: Env & { MIRROR_SAMPLE_RATE: string }, ctx: ExecutionContext): Promise<Response> {
    const rate = parseFloat(env.MIRROR_SAMPLE_RATE ?? '0.1');
    const primary = fetch(request.clone());

    if (shouldMirror(rate)) {
      const mirror = request.clone();
      ctx.waitUntil(
        fetch(new Request(env.MIRROR_BACKEND + new URL(request.url).pathname, mirror))
          .then(r => r.body?.cancel())
          .catch(err => console.error('sampled mirror error', err)),
      );
    }

    return primary;
  },
};
```

## Fire-and-Forget Analytics Beacon
Send a lightweight structured event to an analytics collector without blocking the response path.

```typescript
interface AnalyticsEvent {
  url: string;
  method: string;
  cf: Record<string, unknown>;
  ts: number;
  requestId: string;
}

function emitAnalytics(request: Request, env: Env & { ANALYTICS_ENDPOINT: string }, ctx: ExecutionContext): void {
  const event: AnalyticsEvent = {
    url: request.url,
    method: request.method,
    cf: request.cf as Record<string, unknown> ?? {},
    ts: Date.now(),
    requestId: request.headers.get('x-request-id') ?? crypto.randomUUID(),
  };

  ctx.waitUntil(
    fetch(env.ANALYTICS_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(event),
      signal: AbortSignal.timeout(3000),
    }).then(r => r.body?.cancel()).catch(() => {}),
  );
}
```

## Anti-patterns
- Awaiting the mirror subrequest before returning the primary response — this adds shadow latency directly to client latency.
- Forgetting to call `resp.body?.cancel()` on the mirror response — the body stream stays open and counts against the subrequest budget.
- Mirroring at 100% to an unscaled shadow backend — it will receive the same peak QPS as production.
- Sending authentication headers to an untrusted mirror endpoint — strip `Authorization`, `Cookie`, and internal headers before mirroring.
- Using `Request.clone()` after the body has already been consumed — clone before any `await req.json()` or `await req.text()`.

## Gotchas
- `ctx.waitUntil` budget is still bounded by the worker's wall-clock limit (30 s on Bundled, unlimited on Unbound); long mirror timeouts can block isolate recycling.
- Workers on the Free tier have 50 subrequests per invocation; count both primary and mirror against that limit.
- `request.cf` (geo, ASN, datacenter) is only available in production; it is `undefined` in `wrangler dev` local mode.
- If the primary upstream returns a non-buffered streaming response, `primaryResp.clone()` buffers the entire body — avoid cloning streaming responses; tee the stream instead.
- A `fetch()` to `localhost` or RFC-1918 addresses is blocked by Workers; the mirror backend must be reachable over the public internet or via a Service Binding.

## Verification
1. Set `MIRROR_SAMPLE_RATE=1.0` in a staging environment and assert every request appears in both primary and mirror access logs.
2. Inject a deliberate response body difference in the shadow backend and verify the diff shows up in the KV DIFF_LOG key within 5 seconds.
3. Use `wrangler tail` to confirm mirror errors are logged and do not surface as 5xx to clients.
4. Load-test with `k6` at 100 RPS and confirm primary P99 latency is unchanged from a no-mirror baseline.

## Related
- `/documentation/docs/policies/patterns/scatter-gather-parallel-workers.md`
- `/documentation/docs/policies/patterns/correlation-id-propagation-workers.md`
- `/documentation/docs/policies/patterns/fan-out-queues-workers.md`

## Sources
- https://developers.cloudflare.com/workers/runtime-apis/fetch/
- https://developers.cloudflare.com/workers/runtime-apis/context/
- https://developers.cloudflare.com/workers/platform/limits/#subrequests
