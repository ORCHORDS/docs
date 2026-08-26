# Proxy Pattern: Service Binding Auth and Retry Wrapper for Workers

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Your Worker calls three internal services via Service Bindings. Each call site manually adds the `Authorization` header, checks for 401 and retries after refreshing the token, logs the outbound call, and handles 429 rate-limit responses. When a new service is added, the same boilerplate is repeated. When the token-refresh logic changes, it must be updated in every call site.

Classic signs:
- `.fetch()` calls on Service Bindings peppered with `headers.set("Authorization", ...)` spread across 15+ files
- A forgotten auth header causes a mysterious 401 in production on the third day
- Token refresh races where two concurrent requests both refresh simultaneously, burning two tokens
- No consistent place to record outbound latency for internal service calls

---

## Context

The Proxy pattern provides a surrogate that controls access to another object. Here the proxy wraps a `Fetcher` (the Workers runtime type for Service Bindings and `fetch`) with cross-cutting concerns: authentication injection, transparent token refresh, retry on transient errors, and structured logging. Consumers call the proxy exactly as they would call `env.SOME_SERVICE.fetch(url, init)` and get the cross-cutting behaviour for free.

```
Consumer
  │ .fetch(url, init)
  ▼
ServiceProxy
  ├─ inject Authorization header
  ├─ call underlying Fetcher
  ├─ on 401 → refresh token → retry once
  ├─ on 429 → wait Retry-After → retry
  ├─ on 5xx → exponential backoff → retry up to N times
  └─ log { service, method, status, durationMs }
  │
  ▼
env.TARGET_SERVICE (Fetcher)
```

---

## Token Store

```typescript
// src/proxy/token-store.ts

/** In-memory singleton that caches the current service-to-service token per isolate.
 *  Production: store in KV with a TTL equal to token expiry minus a 30-second buffer. */
export class TokenStore {
  private tokens = new Map<string, { value: string; expiresAt: number }>();
  private refreshing = new Map<string, Promise<string>>();

  constructor(
    private readonly refresh: (service: string) => Promise<{ token: string; expiresInMs: number }>
  ) {}

  async get(service: string): Promise<string> {
    const cached = this.tokens.get(service);
    if (cached && cached.expiresAt > Date.now() + 5_000) return cached.value;

    // Coalesce concurrent refreshes: if one is in flight, wait for it
    const inFlight = this.refreshing.get(service);
    if (inFlight) return inFlight;

    const refreshPromise = this.refresh(service).then(({ token, expiresInMs }) => {
      this.tokens.set(service, { value: token, expiresAt: Date.now() + expiresInMs });
      this.refreshing.delete(service);
      return token;
    });

    this.refreshing.set(service, refreshPromise);
    return refreshPromise;
  }

  invalidate(service: string) {
    this.tokens.delete(service);
  }
}
```

---

## ServiceProxy Class

```typescript
// src/proxy/service-proxy.ts
import type { TokenStore } from "./token-store";

export interface ProxyOptions {
  service: string;       // logical name for logging
  maxRetries?: number;   // default 3
  baseDelayMs?: number;  // default 200 ms
}

function sleep(ms: number) {
  return new Promise<void>((resolve) => setTimeout(resolve, ms));
}

export class ServiceProxy {
  private readonly maxRetries: number;
  private readonly baseDelayMs: number;

  constructor(
    private readonly fetcher: Fetcher,
    private readonly tokenStore: TokenStore,
    private readonly opts: ProxyOptions
  ) {
    this.maxRetries = opts.maxRetries ?? 3;
    this.baseDelayMs = opts.baseDelayMs ?? 200;
  }

  async fetch(url: string | Request, init: RequestInit = {}): Promise<Response> {
    const urlStr = typeof url === "string" ? url : url.url;
    const method = init.method ?? (typeof url === "object" ? url.method : "GET");

    for (let attempt = 0; attempt <= this.maxRetries; attempt++) {
      const token = await this.tokenStore.get(this.opts.service);
      const headers = new Headers(init.headers);
      headers.set("Authorization", `Bearer ${token}`);

      const start = Date.now();
      let response: Response;

      try {
        response = await this.fetcher.fetch(url, { ...init, headers });
      } catch (err) {
        // Network-level error — retry with backoff
        const delay = this.backoff(attempt);
        console.error(
          JSON.stringify({ service: this.opts.service, method, url: urlStr, attempt, error: String(err) })
        );
        if (attempt === this.maxRetries) throw err;
        await sleep(delay);
        continue;
      }

      const durationMs = Date.now() - start;
      this.log(method, urlStr, response.status, durationMs, attempt);

      if (response.status === 401 && attempt === 0) {
        // Token was rejected — invalidate and retry once with a fresh token
        this.tokenStore.invalidate(this.opts.service);
        continue;
      }

      if (response.status === 429) {
        const retryAfter = Number(response.headers.get("Retry-After") ?? 1) * 1000;
        if (attempt < this.maxRetries) {
          await sleep(retryAfter);
          continue;
        }
      }

      if (response.status >= 500 && attempt < this.maxRetries) {
        await sleep(this.backoff(attempt));
        continue;
      }

      return response;
    }

    // Unreachable, but TypeScript needs a return
    throw new Error(`${this.opts.service}: max retries exceeded`);
  }

  private backoff(attempt: number): number {
    // Exponential with full jitter
    const cap = 30_000;
    const base = this.baseDelayMs * 2 ** attempt;
    return Math.random() * Math.min(cap, base);
  }

  private log(method: string, url: string, status: number, durationMs: number, attempt: number) {
    console.log(
      JSON.stringify({ service: this.opts.service, method, url, status, durationMs, attempt })
    );
  }
}
```

---

## Wiring Proxies in the Worker Entry Point

```typescript
// src/worker.ts
import type { Env } from "./types";
import { TokenStore } from "./proxy/token-store";
import { ServiceProxy } from "./proxy/service-proxy";

// Module-scope singleton: token cache survives across requests in the same isolate
let tokenStore: TokenStore | undefined;

function getTokenStore(env: Env): TokenStore {
  if (!tokenStore) {
    tokenStore = new TokenStore(async (service) => {
      // Exchange a client_credentials grant against your auth service
      const resp = await env.AUTH_SERVICE.fetch("https://auth/token", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ grant_type: "client_credentials", service }),
      });
      const { access_token, expires_in } = await resp.json<{
        access_token: string;
        expires_in: number;
      }>();
      return { token: access_token, expiresInMs: expires_in * 1000 };
    });
  }
  return tokenStore;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const store = getTokenStore(env);

    const inventoryProxy = new ServiceProxy(env.INVENTORY_SERVICE, store, {
      service: "inventory",
      maxRetries: 3,
      baseDelayMs: 100,
    });

    const pricingProxy = new ServiceProxy(env.PRICING_SERVICE, store, {
      service: "pricing",
    });

    // Consumers call the proxy identically to the raw binding
    const [invResp, priceResp] = await Promise.all([
      inventoryProxy.fetch("https://inventory/stock?sku=abc"),
      pricingProxy.fetch("https://pricing/price?sku=abc"),
    ]);

    const stock = await invResp.json();
    const price = await priceResp.json();

    return Response.json({ stock, price });
  },
};
```

---

## Testing the Proxy

```typescript
// src/proxy/__tests__/service-proxy.test.ts
import { describe, it, expect, vi } from "vitest";
import { ServiceProxy } from "../service-proxy";
import { TokenStore } from "../token-store";

function makeStore(token = "tok"): TokenStore {
  return { get: vi.fn().mockResolvedValue(token), invalidate: vi.fn() } as unknown as TokenStore;
}

function makeFetcher(responses: Response[]): Fetcher {
  let i = 0;
  return { fetch: vi.fn().mockImplementation(() => Promise.resolve(responses[i++])) } as unknown as Fetcher;
}

it("injects Authorization header", async () => {
  const fetcher = makeFetcher([new Response("ok", { status: 200 })]);
  const proxy = new ServiceProxy(fetcher, makeStore("my-token"), { service: "svc" });
  await proxy.fetch("https://svc/path");
  const call = (fetcher.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
  expect(call[1].headers.get("Authorization")).toBe("Bearer my-token");
});

it("invalidates token and retries on 401", async () => {
  const store = makeStore("old");
  const fetcher = makeFetcher([
    new Response("Unauthorized", { status: 401 }),
    new Response("ok", { status: 200 }),
  ]);
  const proxy = new ServiceProxy(fetcher, store, { service: "svc", maxRetries: 1 });
  const resp = await proxy.fetch("https://svc/path");
  expect(resp.status).toBe(200);
  expect(store.invalidate).toHaveBeenCalledWith("svc");
  expect(fetcher.fetch).toHaveBeenCalledTimes(2);
});

it("retries on 500 up to maxRetries", async () => {
  const fetcher = makeFetcher([
    new Response("err", { status: 500 }),
    new Response("err", { status: 500 }),
    new Response("ok", { status: 200 }),
  ]);
  const proxy = new ServiceProxy(fetcher, makeStore(), { service: "svc", maxRetries: 3, baseDelayMs: 0 });
  const resp = await proxy.fetch("https://svc/path");
  expect(resp.status).toBe(200);
  expect(fetcher.fetch).toHaveBeenCalledTimes(3);
});
```

---

## Anti-patterns

- **Constructing a new `TokenStore` per request**: Token refresh will never be coalesced; every concurrent request triggers a separate refresh. Store the `TokenStore` at module scope.
- **Catching and retrying 4xx errors other than 401 and 429**: Client errors (400, 403, 404, 422) are deterministic; retrying them wastes quota and increases tail latency.
- **Silently swallowing the original response after exhausting retries**: Callers need to observe the final non-successful response to decide how to handle it (e.g., surface 404 to the end user). Return the last response rather than throwing after exhausting retries in non-network-error scenarios.
- **Cloning the request body on every retry**: `Request` bodies are single-read streams. If the body must be sent on retry, buffer it to a string or `ArrayBuffer` before the first attempt and reconstruct each `Request` from the buffer.
- **Using the proxy for read-only idempotent calls only**: The pattern is equally valid for `POST`/`PATCH` calls, but retry semantics must account for non-idempotency; limit retries to network errors and 5xx for mutating endpoints, and add an idempotency key header.

---

## Gotchas

- Service Binding `Fetcher.fetch` in Workers does not support streaming request bodies on retry because the body stream is consumed. If the upstream service requires a large body, buffer it with `request.arrayBuffer()` or `request.text()` before entering the retry loop.
- `setTimeout` inside a Worker only counts wall-clock time toward CPU limits if the isolate is actively running. Sleeping between retries is safe but counts against the 30-second wall-clock limit per request. For very long retry chains use a Queue with delayed delivery instead.
- The `TokenStore` module-scope singleton is not shared across isolate instances. Each isolate that starts cold will perform one token refresh. This is correct and expected, not a bug.
- When the target service returns `429` with `Retry-After: 60`, sleeping 60 seconds will exceed the Workers CPU time limit. In that case, return a 503 to the caller and let the caller retry, or route the request through a Durable Object alarm.
- Service Bindings do not traverse `waitUntil`; a proxy call inside `ctx.waitUntil` still counts against the isolate's total CPU time. Set a conservative overall timeout using `AbortSignal.timeout`.

---

## Verification

1. Observe logs for a successful call: `{ service: "inventory", method: "GET", status: 200, durationMs: ≈X, attempt: 0 }`.
2. Make the underlying service return 401 on the first call and 200 on the second; confirm `store.invalidate` is called and the proxy returns 200.
3. Make the service always return 500; confirm the proxy retries `maxRetries` times and the final response status is 500.
4. Check that all outbound requests carry `Authorization: Bearer <token>` using a `wrangler dev` intercept or a mock fetcher.
5. Verify that two concurrent requests to the proxy with an expired token trigger exactly one token refresh (coalesced via `this.refreshing` map).

---

## Related

- `exponential-backoff-jitter-workers.md` — detailed backoff calculation and jitter strategies
- `circuit-breaker-workers-d1-fetch.md` — open the circuit after sustained failures instead of retrying indefinitely
- `lazy-init-module-cache-workers.md` — module-scope singleton patterns for Workers
- `request-hedging-latency.md` — speculatively issuing a second request instead of waiting for retry

---

## Sources

- Gamma et al. — Design Patterns: Elements of Reusable Object-Oriented Software (1994): Proxy
- Cloudflare Service Bindings: https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- Cloudflare Workers Fetcher type: https://developers.cloudflare.com/workers/runtime-apis/handlers/fetch/
- OAuth 2.0 Client Credentials: https://datatracker.ietf.org/doc/html/rfc6749#section-4.4
