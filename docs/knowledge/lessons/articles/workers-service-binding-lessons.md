# Workers Service Binding Lessons

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You split Orchords into micro-Workers and connect them with Service Bindings expecting zero-latency internal calls. In production, some bindings add 15–30 ms of latency you did not see in `wrangler dev --local`. A binding that works in `fetch()` throws in `scheduled()`. Deploying Worker B with a new interface breaks Worker A (the caller) silently. Circular bindings crash the entire request chain without a clear error. You cannot figure out why `wrangler dev` works but the deployed version does not.

---

## Context

Service Bindings let one Worker call another Worker by name, using an in-memory RPC-style call when both Workers are co-located on the same edge node. When they are on different nodes (which happens during rollouts, traffic spikes, and geographic spread), the call traverses Cloudflare's internal network, adding latency. Service Bindings are only available inside the `fetch()` handler; they are not available in `scheduled()`, `queue()`, or standalone alarm handlers by default.

Orchords uses Service Bindings for auth validation, feature flags, and content moderation — all high-frequency, latency-sensitive paths.

---

## Solution

```typescript
// workers-service-binding-lessons.ts

// ─────────────────────────────────────────────────────────────
// LESSON 1: Service Bindings are NOT available in scheduled()
// ─────────────────────────────────────────────────────────────
//
// The `scheduled()` handler runs without an incoming Request
// context. Service Bindings require a Request context to route
// the internal call. Attempting to use a binding in scheduled()
// throws: "TypeError: Cannot use service bindings in this context"
//
// Fix: issue an internal HTTP call to yourself (or to the target
// Worker via its public URL or a custom domain) using fetch().
// Use a shared secret header to authenticate internal calls.

interface Env {
  AUTH_WORKER: Fetcher;       // Service Binding — available in fetch() only
  MODERATION_WORKER: Fetcher; // Service Binding
  INTERNAL_SECRET: string;    // Secret for internal auth
}

export default {
  // Works: Service Binding available here
  async fetch(request: Request, env: Env): Promise<Response> {
    const authResult = await env.AUTH_WORKER.fetch(
      new Request('https://auth-worker/validate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Internal-Secret': env.INTERNAL_SECRET,
        },
        body: JSON.stringify({ token: request.headers.get('Authorization') }),
      })
    );

    if (!authResult.ok) {
      return new Response('Unauthorized', { status: 401 });
    }

    return handleMain(request, env);
  },

  // WRONG: Service Bindings throw here
  // async scheduled(event, env) {
  //   await env.AUTH_WORKER.fetch(...); // TypeError!
  // }

  // CORRECT: use internal fetch with a shared secret
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    // Self-invoke via fetch to a known internal path
    // This triggers a new fetch() invocation where bindings work
    const response = await fetch('https://orchords-api.internal/cron/daily-digest', {
      method: 'POST',
      headers: {
        'X-Internal-Secret': env.INTERNAL_SECRET,
        'X-Cron-Trigger': event.cron,
      },
    });

    if (!response.ok) {
      console.error('Scheduled task failed', await response.text());
    }
  },
};

async function handleMain(request: Request, env: Env): Promise<Response> {
  return new Response('ok');
}

// ─────────────────────────────────────────────────────────────
// LESSON 2: Service Binding latency is not always zero
// ─────────────────────────────────────────────────────────────
//
// In wrangler dev --local, all Workers run in the same process.
// In production, the two Workers may be on different edge nodes,
// making the call a real network round-trip (15–50 ms).
// Profile Service Binding latency in production before relying
// on it for sub-10 ms SLAs.

async function callWithLatencyTracking(
  binding: Fetcher,
  url: string,
  options?: RequestInit
): Promise<Response> {
  const start = Date.now();
  const response = await binding.fetch(new Request(url, options));
  const latencyMs = Date.now() - start;

  // Log latency to analytics or observability pipeline
  console.log(JSON.stringify({ event: 'service_binding_call', url, latencyMs }));

  if (latencyMs > 30) {
    console.warn(`Service binding latency ${latencyMs}ms exceeds threshold`);
  }

  return response;
}

// ─────────────────────────────────────────────────────────────
// LESSON 3: Versioning mismatch between caller and callee
// ─────────────────────────────────────────────────────────────
//
// When you deploy Worker B with a new API shape before updating
// Worker A (which calls B), A's requests may hit the new B.
// The response shape changes and A's parsing breaks silently.
//
// Fix: version your internal APIs, or always deploy callee
// changes backward-compatibly before updating the caller.

interface AuthResponseV1 {
  valid: boolean;
  userId: string;
}

interface AuthResponseV2 {
  valid: boolean;
  userId: string;
  scopes: string[]; // added in v2
  sessionId: string; // added in v2
}

async function validateTokenVersioned(
  authBinding: Fetcher,
  token: string
): Promise<AuthResponseV1 | AuthResponseV2> {
  const res = await authBinding.fetch(
    new Request('https://auth-worker/validate', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        // Pass caller version so callee can respond in the right schema
        'X-Api-Version': '2',
      },
      body: JSON.stringify({ token }),
    })
  );

  if (!res.ok) {
    throw new Error(`Auth failed: ${res.status}`);
  }

  return res.json<AuthResponseV2>();
}

// ─────────────────────────────────────────────────────────────
// LESSON 4: Testing Service Bindings — local vs remote
// ─────────────────────────────────────────────────────────────
//
// `wrangler dev` without --remote runs all bindings in-process.
// This masks network latency AND skips real Worker isolation.
// Always run at least one integration test pass with:
//   wrangler dev --remote
// to catch production-only issues like cross-node latency,
// compatibility date mismatches, and binding resolution errors.
//
// In unit tests with Miniflare, bind a mock Fetcher:

class MockAuthWorker implements Fetcher {
  private readonly validTokens: Set<string>;

  constructor(validTokens: string[]) {
    this.validTokens = new Set(validTokens);
  }

  async fetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
    const request = new Request(input, init);
    const body = await request.json<{ token: string }>();
    const valid = this.validTokens.has(body.token);

    return Response.json({ valid, userId: valid ? 'user-1' : null });
  }

  connect(): never {
    throw new Error('Not implemented in mock');
  }
}

// Usage in tests:
// const env = { AUTH_WORKER: new MockAuthWorker(['valid-token-123']) };

// ─────────────────────────────────────────────────────────────
// LESSON 5: Circular binding detection
// ─────────────────────────────────────────────────────────────
//
// Worker A → Worker B → Worker A creates an infinite call chain.
// Cloudflare does not automatically detect circular bindings;
// the request will exhaust the subrequest limit (1000) and
// return a 524 timeout to the original caller.
//
// Pattern: propagate a call-chain header to detect cycles.

const MAX_CHAIN_DEPTH = 5;

function detectCircularBinding(
  request: Request,
  workerName: string
): void {
  const chain = request.headers.get('X-Call-Chain') ?? '';
  const hops = chain ? chain.split(',') : [];

  if (hops.includes(workerName)) {
    throw new Error(
      `Circular Service Binding detected: ${[...hops, workerName].join(' → ')}`
    );
  }

  if (hops.length >= MAX_CHAIN_DEPTH) {
    throw new Error(
      `Service Binding chain depth ${hops.length} exceeds maximum ${MAX_CHAIN_DEPTH}`
    );
  }
}

function buildChainedRequest(
  url: string,
  init: RequestInit,
  incomingRequest: Request,
  callerName: string
): Request {
  const existingChain = incomingRequest.headers.get('X-Call-Chain') ?? '';
  const newChain = existingChain ? `${existingChain},${callerName}` : callerName;

  return new Request(url, {
    ...init,
    headers: {
      ...(init.headers as Record<string, string>),
      'X-Call-Chain': newChain,
    },
  });
}

// Usage in a Worker that calls another Service Binding:
export const chainedWorker = {
  async fetch(request: Request, env: Env): Promise<Response> {
    detectCircularBinding(request, 'orchords-api');

    const downstreamRequest = buildChainedRequest(
      'https://moderation-worker/check',
      {
        method: 'POST',
        body: request.body,
        headers: { 'Content-Type': 'application/json' },
      },
      request,
      'orchords-api'
    );

    const moderationResult = await env.MODERATION_WORKER.fetch(downstreamRequest);
    return moderationResult;
  },
};

// ─────────────────────────────────────────────────────────────
// LESSON 6: Graceful degradation when a binding is unavailable
// ─────────────────────────────────────────────────────────────
//
// Service Bindings to another Worker that is being deployed
// or has errors can return 503 or throw. Always handle errors
// from bindings and implement fallback logic for non-critical paths.

async function callWithFallback<T>(
  binding: Fetcher,
  url: string,
  fallback: T
): Promise<T> {
  try {
    const response = await Promise.race([
      binding.fetch(new Request(url)),
      new Promise<never>((_, reject) =>
        setTimeout(() => reject(new Error('Service binding timeout')), 2000)
      ),
    ]);

    if (!response.ok) {
      console.error(`Service binding ${url} returned ${response.status}`);
      return fallback;
    }

    return response.json<T>();
  } catch (err) {
    console.error('Service binding error, using fallback', err);
    return fallback;
  }
}
```

---

## Implementation Details

**`scheduled()` handler restriction** exists because scheduled invocations do not carry a Request object, and Service Bindings route calls via the request's context. The workaround — fetching a known internal URL with a shared secret header — creates a new fetch context where bindings are available. Protect the internal URL with a server-side secret check, not just network-level controls.

**Latency variability** stems from Cloudflare's anycast routing. Two Workers with Service Bindings will be co-located on the same machine most of the time (especially on the same PoP), but during deployments, failovers, and traffic imbalances, calls can cross PoP boundaries. The Cloudflare dashboard does not expose per-call latency breakdowns for Service Bindings; you must instrument at the application level.

**Backward-compatible API evolution** — the safest pattern is to add optional fields to response objects rather than changing existing field names. Callers that parse JSON should ignore unknown fields. Use an explicit `X-Api-Version` header to let the callee adapt its response format when breaking changes are unavoidable.

**Circular binding detection via header** adds a small overhead (header parsing) but prevents a category of bugs that consume the entire subrequest budget (1000 subrequests per Worker invocation). Log the chain header in your observability pipeline to trace inter-Worker call paths.

---

## Anti-patterns

- Using a Service Binding in `scheduled()` without wrapping it in a `fetch()` call.
- Assuming sub-millisecond latency for all Service Binding calls in production.
- Deploying callee Workers with breaking API changes before updating the caller.
- Testing only with `wrangler dev --local` (no real isolation or network effects).
- Not handling 5xx responses from Service Bindings (treating them as always-available).
- Building deep call chains without a depth limit or cycle detection.

---

## Gotchas

- Service Bindings count against the calling Worker's subrequest limit (1000 per invocation). A Worker that fans out to 10 bindings each making 5 sub-calls is at 50 subrequests before doing any other work.
- The `Fetcher` type for Service Bindings is different from the global `fetch` function type — it accepts `RequestInfo | URL` as the first argument but does not accept a plain string in all runtime versions. Always wrap strings in `new Request(url)`.
- Environment variable names for Service Bindings in `wrangler.toml` must match exactly what the Worker code references in `env.BINDING_NAME`.
- Service Bindings in `wrangler.toml` reference the other Worker's `name` field, not its route. If the other Worker is renamed, the binding breaks silently at deploy time (not at runtime).
- You cannot bind to a Worker in a different Cloudflare account, even within the same organisation structure.

---

## Verification

```bash
# Verify binding works in --remote mode (catches production-only issues)
wrangler dev --remote

# Check that circular binding throws before exhausting subrequest limit
curl -X POST https://orchords-api.workers.dev/test \
  -H 'X-Call-Chain: orchords-api' \
  -H 'Authorization: Bearer test-token'
# Expected: 500 with body "Circular Service Binding detected"

# Measure real Service Binding latency in production
wrangler tail orchords-api --format json | jq 'select(.logs[].message | contains("service_binding_call")) | .logs[].message'
```

---

## Related

- `documentation/docs/policies/lessons/subrequest-limit-patterns.md`
- `documentation/docs/policies/lessons/workers-wrangler-deploy-surprises.md`
- Cloudflare Service Bindings documentation: Configuration, RPC

---

## Sources

- Cloudflare Workers Service Bindings docs (2025)
- Orchords production incident log #SB-002 (scheduled() binding error), #SB-008 (circular binding timeout)
- Cloudflare Discord: "Service binding not available in cron trigger" thread
