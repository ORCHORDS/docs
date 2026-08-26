# circuit-breaker-pattern

**Issue:** When vendor calls consistently fail, stop calling for a while
**Date:** 2026-08-09
**Status:** documented

## Symptom
A vendor (e.g. NOWPayments, Stripe, Twilio) has a partial outage.
Your service retries 3 times per request. Your service gets 10k
RPS. The vendor is drowning in retries. Your p99 latency goes
from 200ms to 60s. Your error rate spikes. Your users see timeouts.

## Root cause
Without a circuit breaker, every request independently retries
3 times. When the vendor fails, every request wastes 3 attempts
before giving up. The vendor's load goes up at exactly the wrong
time.

**Source:** Martin Fowler — Circuit Breaker:
https://martinfowler.com/bliki/CircuitBreaker.html

> "The basic idea behind the circuit breaker is very simple. You
> wrap a protected function call in a circuit breaker object, which
> monitors for failures. Once the failures reach a certain
> threshold, the circuit breaker trips, and all further calls
> return an error immediately."

## Fix
A circuit breaker has 3 states:

```ts
type State = 'closed' | 'open' | 'half-open';

class CircuitBreaker {
  private state: State = 'closed';
  private failureCount: number = 0;
  private lastFailure: number = 0;
  private readonly failureThreshold: number = 5;
  private readonly cooldownMs: number = 30_000;

  async call<T>(fn: () => Promise<T>): Promise<T> {
    if (this.state === 'open') {
      if (Date.now() - this.lastFailure > this.cooldownMs) {
        this.state = 'half-open';
      } else {
        throw new Error('Circuit open');
      }
    }

    try {
      const result = await fn();
      this.onSuccess();
      return result;
    } catch (err) {
      this.onFailure();
      throw err;
    }
  }

  private onSuccess(): void {
    if (this.state === 'half-open') {
      this.state = 'closed';  // recovered
    }
    this.failureCount = 0;
  }

  private onFailure(): void {
    this.failureCount++;
    this.lastFailure = Date.now();
    if (this.failureCount >= this.failureThreshold) {
      this.state = 'open';
    }
  }
}
```

- **closed:** normal operation, count failures
- **open:** reject all calls immediately, save the vendor's load
- **half-open:** try one call to see if the vendor recovered

## Tuning

- **failureThreshold:** 5 consecutive failures? 50% failure rate
  over 100 requests? Pick based on the vendor's reliability.
- **cooldownMs:** 30s for fast-recovery vendors, 5min for slow.
  Match the vendor's incident-response time.
- **Per-vendor vs per-endpoint:** Stripe has separate circuit
  breakers for `/charges` vs `/refunds`. A bug in one doesn't
  take down the other.
- **Failure modes:** count 5xx as failures. Don't count 4xx (the
  vendor is rejecting your bad request, which is correct).

## Verification
- **Test:** `test/circuit-breaker.test.ts` — 5 failures → state
  = open, 30s cooldown, 1 half-open success → state = closed
- **Live:** Vendor outage → 0 retries to the vendor after 5
  failures (visible in vendor's metrics); user-facing errors
  return fast with a clear "vendor unavailable" message

## Gotchas
- **A circuit breaker is not a load balancer.** It doesn't
  redirect traffic; it just short-circuits it.
- **The "half-open" probe call is not special.** It's a normal
  call that happens to test recovery. If it fails, the breaker
  re-opens.
- **Don't share a circuit breaker across tenants.** A noisy
  tenant shouldn't trip the breaker for everyone.
- **The breaker's state lives where?** If in memory of a single
  isolate, it resets on every deploy. If in D1, adds latency.
  Most apps use in-memory + accept the reset cost.
- **Alert when a breaker opens.** PagerDuty / Slack notification
  so the on-call knows to investigate.

## Related
- `retry-with-jitter.md` (composes with circuit breaker)
- `per-tenant-durable-object.md` (DO is a good home for the
  breaker state)
- Martin Fowler: https://martinfowler.com/bliki/CircuitBreaker.html
