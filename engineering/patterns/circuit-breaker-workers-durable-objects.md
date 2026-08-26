# Circuit Breaker with Durable Objects

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Worker calls a third-party API and that API starts returning errors or timing out. Without a circuit breaker, every incoming request hammers the broken upstream, wasting quota, adding latency, and cascading failures back to your users. A Durable Object–backed circuit breaker trips after a failure threshold, stops forwarding traffic during an open window, and automatically probes for recovery.

---

## Context

Durable Objects provide per-key singleton state with `ctx.storage` and `ctx.storage.setAlarm()`, making them a natural fit for a circuit breaker that must track failure counts and schedule automatic state resets. The DO exposes a single `check()` method via a stub call from the Worker middleware; the Worker aborts the upstream fetch if the circuit is OPEN and records the outcome afterward. HALF_OPEN lets exactly one probe request through to test recovery without re-opening prematurely on a single success.

---

## Wrangler Config

```toml
[[durable_objects.bindings]]
name       = "CIRCUIT_BREAKER"
class_name = "CircuitBreakerDO"

[[migrations]]
tag  = "v1"
new_classes = ["CircuitBreakerDO"]
```

---

## Implementation — CircuitBreakerDO

```typescript
// circuit-breaker-do.ts

type State = 'CLOSED' | 'OPEN' | 'HALF_OPEN';

interface CBState {
  state:        State;
  failures:     number;
  lastFailureAt: number; // epoch ms
}

const FAILURE_THRESHOLD = 5;
const OPEN_DURATION_MS  = 30_000; // 30 s before moving to HALF_OPEN

export class CircuitBreakerDO implements DurableObject {
  private storage: DurableObjectStorage;

  constructor(state: DurableObjectState) {
    this.storage = state.storage;
  }

  async fetch(request: Request): Promise<Response> {
    const url    = new URL(request.url);
    const action = url.pathname.split('/').pop();

    switch (action) {
      case 'check':   return Response.json(await this.check());
      case 'success': return Response.json(await this.recordSuccess());
      case 'failure': return Response.json(await this.recordFailure());
      case 'status':  return Response.json(await this.getState());
      default:        return new Response('Not found', { status: 404 });
    }
  }

  // Called before every upstream request — returns whether to allow
  private async check(): Promise<{ allow: boolean; state: State }> {
    const cb = await this.loadState();

    if (cb.state === 'CLOSED') {
      return { allow: true, state: 'CLOSED' };
    }

    if (cb.state === 'OPEN') {
      const elapsed = Date.now() - cb.lastFailureAt;
      if (elapsed >= OPEN_DURATION_MS) {
        // Transition to HALF_OPEN: allow one probe
        await this.setState({ ...cb, state: 'HALF_OPEN' });
        return { allow: true, state: 'HALF_OPEN' };
      }
      return { allow: false, state: 'OPEN' };
    }

    // HALF_OPEN: allow probe; set back to OPEN in case probe is slow and
    // another request races in before recordSuccess/recordFailure is called.
    return { allow: true, state: 'HALF_OPEN' };
  }

  private async recordSuccess(): Promise<CBState> {
    const cb = await this.loadState();
    const next: CBState = { state: 'CLOSED', failures: 0, lastFailureAt: 0 };
    await this.setState(next);
    // Cancel any pending alarm
    await this.storage.deleteAlarm();
    return next;
  }

  private async recordFailure(): Promise<CBState> {
    const cb       = await this.loadState();
    const failures = cb.failures + 1;
    const now      = Date.now();

    if (failures >= FAILURE_THRESHOLD || cb.state === 'HALF_OPEN') {
      const next: CBState = { state: 'OPEN', failures, lastFailureAt: now };
      await this.setState(next);
      // Alarm auto-resets the DO so HALF_OPEN probe can be attempted
      await this.storage.setAlarm(now + OPEN_DURATION_MS);
      return next;
    }

    const next: CBState = { state: 'CLOSED', failures, lastFailureAt: now };
    await this.setState(next);
    return next;
  }

  // Alarm fires after OPEN_DURATION_MS; transition to HALF_OPEN
  async alarm(): Promise<void> {
    const cb = await this.loadState();
    if (cb.state === 'OPEN') {
      await this.setState({ ...cb, state: 'HALF_OPEN' });
    }
  }

  private async loadState(): Promise<CBState> {
    return (
      (await this.storage.get<CBState>('cb')) ??
      { state: 'CLOSED', failures: 0, lastFailureAt: 0 }
    );
  }

  private async setState(s: CBState): Promise<void> {
    await this.storage.put('cb', s);
  }

  private async getState(): Promise<CBState> {
    return this.loadState();
  }
}
```

---

## Implementation — Worker Middleware

```typescript
// worker.ts
import { CircuitBreakerDO } from './circuit-breaker-do';
export { CircuitBreakerDO };

export interface Env {
  CIRCUIT_BREAKER: DurableObjectNamespace;
  UPSTREAM_URL:    string;
}

// One CB instance per upstream service name (or region, or endpoint)
function getBreaker(env: Env, service: string): DurableObjectStub {
  const id = env.CIRCUIT_BREAKER.idFromName(service);
  return env.CIRCUIT_BREAKER.get(id);
}

async function cbFetch(
  stub: DurableObjectStub,
  upstreamUrl: string,
  init?: RequestInit
): Promise<Response> {
  // 1. Check circuit state
  const checkRes  = await stub.fetch('https://cb/check');
  const { allow, state } = await checkRes.json<{ allow: boolean; state: string }>();

  if (!allow) {
    return new Response(
      JSON.stringify({ error: 'Service unavailable — circuit OPEN' }),
      { status: 503, headers: { 'Content-Type': 'application/json' } }
    );
  }

  // 2. Attempt upstream
  try {
    const upstream = await fetch(upstreamUrl, {
      ...init,
      signal: AbortSignal.timeout(5_000), // 5 s timeout
    });

    if (!upstream.ok) {
      await stub.fetch('https://cb/failure');
      return upstream;
    }

    await stub.fetch('https://cb/success');
    return upstream;
  } catch (err) {
    await stub.fetch('https://cb/failure');
    throw err;
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const stub = getBreaker(env, 'payment-service');

    try {
      return await cbFetch(stub, `${env.UPSTREAM_URL}${new URL(request.url).pathname}`, {
        method:  request.method,
        headers: request.headers,
        body:    request.body,
      });
    } catch (err) {
      return new Response(
        JSON.stringify({ error: 'Upstream request failed', detail: String(err) }),
        { status: 502, headers: { 'Content-Type': 'application/json' } }
      );
    }
  },
};
```

---

## Anti-patterns

- **Global in-memory counter** — Worker isolates are ephemeral and not shared across instances; in-memory failure counts reset on eviction and are invisible to other isolates.
- **Opening on 4xx responses** — Client errors (400, 401, 422) are not upstream failures; only open the circuit on 5xx or network timeouts.
- **Infinite OPEN state** — Without the alarm-based auto-reset the circuit never recovers without manual intervention.
- **Single threshold for all services** — Different upstream SLAs warrant different thresholds; namespace the DO by service name.

---

## Gotchas

- DO alarms fire at least once but may fire slightly late; the HALF_OPEN check in `check()` provides a belt-and-suspenders transition.
- `stub.fetch()` uses synthetic `https://` URLs because the DO runtime requires a valid URL; the host part is ignored inside the DO.
- During HALF_OPEN, if multiple Worker requests race before the probe completes, more than one probe may slip through; this is acceptable for most use cases.
- `ctx.storage.setAlarm()` replaces any existing alarm; calling it on every failure harmlessly extends the reset window.

---

## Verification

```bash
# Deploy
wrangler deploy

# Check current state
curl https://<worker>.workers.dev/status

# Inspect DO storage directly (local dev)
wrangler dev
curl http://localhost:8787/status

# Simulate failures until circuit opens
for i in $(seq 1 6); do
  curl -s http://localhost:8787/force-fail || true
done

# Expect 503 once OPEN
curl -i http://localhost:8787/any-path

# Wait 30 s then probe — expect HALF_OPEN → CLOSED
sleep 31 && curl -i http://localhost:8787/any-path
```

---

## Related

- `outbox-pattern-workers-d1-queues.md`
- `event-driven-saga-compensation-workers.md`
- `scatter-gather-workers-queues.md`

---

## Sources

- Cloudflare Durable Objects — https://developers.cloudflare.com/durable-objects/
- Durable Object Alarms — https://developers.cloudflare.com/durable-objects/api/alarms/
- Circuit Breaker Pattern (Martin Fowler) — https://martinfowler.com/bliki/CircuitBreaker.html
