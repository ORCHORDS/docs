# Circuit Breaker Pattern Retry Budget

## Scope

This article covers the composition of the circuit breaker with a retry budget: a distributed conservation mechanism that caps the total retry traffic a system may generate, so that retries — individually reasonable — cannot collectively become the outage. Scope includes client-side retry ceilings for calls to one dependency, cluster-wide retry quotas shared across instances, and the interaction rules between the breaker state machine and the budget admission decision. It does not cover single-call retry policies in isolation (backoff shape, jitter), which are prerequisites, nor server-side load shedding, which is the receiving system's own defense. The pattern matters at scale: below a few hundred requests per second, polite retries are noise; above that, unbudgeted retries are a failure amplifier with a documented history of turning partial degradation into total collapse.

## Workflow or implementation guidance

Implement the budget as a token quota with a fill rate, not as a counter of retries attempted. Each retry request consumes a token; when tokens are exhausted, callers fail fast instead of retrying, converting a marginal extra failure into an immediate, cheap one. The fill rate expresses the tolerated retry ratio: a 20 percent budget means that for every five requests at most one may be a retry, so the dependency's worst-case load is 1.2 times its offered load regardless of client-side retry counts.

Compose the two mechanisms in a fixed order on the failure path: consult the breaker first, then the budget, then schedule the retry with jittered exponential backoff. Breaker first, because an open breaker makes the budget question moot — there is nothing to retry. Budget second, because a closed breaker does not imply headroom for retries. A reference decision function:

```ts
function shouldRetry(state: BreakerState, budget: RetryBudget, attempt: number): Decision {
  if (state === 'open') return failFast('breaker_open');
  if (attempt > MAX_ATTEMPTS) return failFast('attempts_exhausted');
  if (!budget.tryConsume()) return failFast('retry_budget_exhausted');
  return schedule(backoffWithJitter(attempt));
}
```

Make the budget cluster-aware where the runtime allows. Per-instance budgets multiply by instance count: ten isolates each allowed a 20 percent retry ratio can jointly emit 20 percent extra load, which is correct only if each instance sees a fair traffic sample — under skewed routing they do not. Where a single-writer primitive is available, hold the budget there and batch token acquisition; where it is not, size per-instance budgets as the global target divided by the steady-state instance count and alert when instance count deviates.

Count retries offered, not just retries issued: budget exhaustion is itself a signal that the primary failure rate has crossed what the budget can absorb, and it should feed the breaker's failure accounting so a sustained budget drought trips the breaker rather than persisting as a stream of fail-fasts.

## Controls

Pin the budget in configuration with an owner and a rationale, and change it through review like capacity planning, because the retry ratio is effectively a capacity multiplier on the dependency. Enforce a hard ceiling on attempts per logical request — two retries beyond the initial attempt is a defensible default — so no configuration error can turn a slow dependency into a request storm. Require jitter everywhere backoff is computed; deterministic backoff under contention produces synchronized waves that defeat both the breaker's recovery probes and the budget's smoothing. Instrument the composition in three counters that must be readable together: breaker state transitions, budget exhaustion rate, and the ratio of retries to total attempts. Alert on the joint condition "breaker closed, budget persistently exhausted" — that is a partially degraded dependency hiding behind a healthy breaker, and it is the specific pathology this composition exists to expose.

## Validation evidence

Validate under load, because quota behavior is invisible at unit-test scale. Fault-injection run: drive steady traffic against a dependency, inject a failure window covering a known fraction of requests, and assert three telemetry facts — total attempts sent to the dependency never exceed offered load times one plus the budget ratio; the retry ratio converges to the budget rather than exceeding it; and after the window, the ratio decays as tokens refill. Amplification check: compare dependency-side request volume during the fault window with and without the budget enabled; the delta is the collapse you prevented, and it is the number that justifies the pattern's complexity. Probe-path check: with the breaker open, verify zero retries reach the dependency and half-open probes are exempt from budget consumption (or drawn from a separate tiny allocation), so recovery testing is never starved by the very outage that caused it. Soak evidence: at least one multi-hour run with the composition enabled under organic traffic, confirming the retry ratio's steady-state distribution sits inside the configured envelope.

## Failure modes and correction

The signature failure is budget accounting that never refills — tokens leak on exception paths, retries decline to zero over hours, and the system silently loses its recovery ability. Correct with a token bucket whose refill is time-based rather than event-based, and alert when the issued-retry count falls to zero for longer than a threshold under nonzero failure rate. The opposite failure is the uncounted retry: a timeout implemented as an internal second attempt, a redirect followed automatically, or a library-level retry beneath your abstraction, all of which bypass the budget and re-create the storm the budget prevents. Correct by auditing every HTTP client's default retry behavior and disabling implicit retries inside the budgeted layer. A third failure is double-counting when the breaker and budget disagree about what a failure is — the breaker counts connection errors, the budget counts 5xx, and the two metrics diverge until operators distrust both. Correct by sharing one failure-classification function. A fourth is per-instance budget multiplication under autoscaling, where instance count doubles and so does effective retry pressure; correct by making the fill rate a function of measured instance count or by centralizing the bucket.

## Limitations

A retry budget bounds amplification, not latency: retried requests still add tail latency, and a 20 percent budget of retries against a dependency with 30-second timeouts can still tie up caller capacity. The budget's ratio is a policy choice with a real trade — a generous budget improves recovery odds for transient faults and worsens collapse risk, and no default is right for all dependencies; it must be tuned per dependency reliability class. Cluster-wide budgets require either shared state (adding a coordination dependency that itself needs resilience handling) or conservative per-instance division (giving up some accuracy). The mechanism also does nothing for non-retry load amplification such as fan-out queries or reconnect storms, which need their own admission control. Finally, in heterogeneous fleets where different clients run different budget implementations, the effective global ratio is unmanageable by any single operator — standardizing the client library is a prerequisite for the numbers to mean anything.

## Canonical sources

- Netflix Hystrix Wiki — How it Works (circuit breaker and retry semantics in a production resilience library): https://github.com/Netflix/Hystrix/wiki/How-it-Works
- AWS Builders' Library — Timeouts, retries, and backoff with jitter (retry budgets and avoiding retry storms): https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/
- Microsoft Azure Architecture Center — Circuit Breaker pattern: https://learn.microsoft.com/en-us/azure/architecture/patterns/circuit-breaker
- Resilience4j documentation — Circuit Breaker (failure-rate and slow-call thresholds): https://resilience4j.readme.io/docs/circuitbreaker
