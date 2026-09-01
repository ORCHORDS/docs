# Circuit Breaker Half Open State Policy

## Scope

This article addresses the half-open state of the circuit breaker pattern. It explains why the half-open state exists, what it must do to be safe, and what policies can be implemented inside it. The discussion covers the classic three-state machine (closed, open, half-open) introduced by Hystrix and formalised in the literature, and it extends to the recovery-probing strategies used in modern resilience libraries such as resilience4j, Polly, and istio's outlier detection. The article applies to any system that uses circuit breakers to protect against cascading failure: HTTP clients, RPC clients, message consumers, and database connection pools.

## Workflow or implementation guidance

The circuit breaker pattern wraps a remote call with a state machine that observes the call's success and failure. In the closed state, calls flow through normally and the breaker tracks failures. When the failure rate crosses a threshold (a count, a ratio, or a slow-call rate), the breaker trips open and subsequent calls fail fast without touching the downstream. After a cool-down period, the breaker enters the half-open state, in which a limited number of trial calls are allowed through to probe the downstream's recovery. If the trial calls succeed, the breaker closes again; if they fail, the breaker reopens and the cool-down restarts.

The half-open state is the most consequential and the most under-specified part of the pattern. Its policy decisions determine whether the system recovers gracefully or thrashes. The first decision is how many trial calls are allowed in half-open. One is the conservative default: the breaker lets exactly one request through, and that request decides the next state. More aggressive policies let a small percentage of traffic through, approximating a canary release of the recovered downstream. The second decision is what counts as success. Some libraries count any 2xx as success; others require the trial call to complete within a latency budget. The third decision is what happens to the in-flight calls during the trial. If the trial is in flight and a new call arrives, the breaker should hold it (or fail it fast) until the trial resolves; otherwise the breaker can be overwhelmed by concurrent trials that disagree about the downstream's health.

The fourth decision is how the cool-down is calculated. A fixed cool-down is simple but brittle: if the downstream recovers in less time, the breaker is slow to close; if it takes longer, the breaker thrashes by re-opening immediately after closing. Adaptive cool-downs, often based on the downstream's historical latency, give better behaviour but require observability and a feedback loop. The fifth decision is what to do with calls that arrive during the open state. The default is to fail fast and let the caller decide (fallback, retry, return cached, return error). Some libraries queue the calls with a bounded buffer; this can be useful for traffic that the system is willing to hold briefly, but it risks turning the open state into a queue with the same load-handling problems as a saturated pool.

The half-open state must also be designed against the worst case in which the downstream is intermittently healthy. A downstream that flaps between healthy and unhealthy must not cause the breaker to flap with it; this is typically handled by requiring a minimum number of successful trial calls before transitioning to closed, and by separating the half-open policy from the open policy.

## Controls

Half-open controls cover concurrency, success criteria, and observability. Concurrency: only one trial call (or one trial batch) should be in flight at a time. Success criteria: the breaker must define what counts as success, and that definition must match the downstream's contract. If a 500 indicates "downstream bug" and a 503 indicates "downstream overload," the breaker's success criterion should treat them differently. Observability: every state transition must be logged and metered. Half-open is the most informative state because it shows the downstream's recovery profile; without metrics on half-open duration, trial success rate, and recovery time, the breaker cannot be tuned.

Configuration controls include the cool-down duration, the half-open trial count, the success threshold (how many trials must succeed before closing), and the failure threshold (how many failures during trial before reopening). Each of these should be a deliberate setting, not a framework default.

## Validation evidence

Validation must prove that the breaker actually protects the caller and recovers correctly. The standard test sequence is: (1) drive the downstream into failure until the breaker opens; (2) verify that subsequent calls fail fast at the breaker and never reach the downstream; (3) wait the cool-down; (4) verify that the breaker enters half-open and lets a trial through; (5) drive the trial to success and verify the breaker closes; (6) drive the trial to failure and verify the breaker reopens. Each transition must be visible in metrics.

A second validation is the flap test: the downstream is repeatedly healthy for short bursts and unhealthy for short bursts. The breaker must eventually converge to a stable state and must not oscillate faster than the cool-down allows. A third validation is the saturation test: the breaker is open, and the caller's own load increases. The breaker must remain open and continue to fail fast; it must not be tempted into half-open by sheer volume of waiting calls.

## Failure modes and correction

The most common failure is the half-open state issuing too many trial calls. The downstream, still recovering, is bombarded with probes and pushed back into failure. The cure is a strict cap on concurrent trials. A second failure is the half-open trial succeeding too easily. A 200 response from a downstream that has only recovered its top-level handlers but not its dependencies will pass the trial but fail in production. The cure is a richer success criterion that exercises the downstream's dependency stack.

A third failure is the breaker staying half-open forever. The trial resolves successfully but the breaker never transitions to closed because the success threshold is set above what the trial produced. The cure is to set the success threshold to a value that the trial can actually meet. A fourth failure is the breaker treating "I tried and the downstream timed out" as inconclusive and leaving the breaker in half-open for an unbounded period. The cure is to treat timeout as failure and to require the breaker to either close or reopen on every trial resolution.

A fifth failure is the breaker's open state masking a real bug in the downstream. A downstream that has been failing because of a code regression will be probed on every cool-down and will continue to fail. The cure is to combine the breaker with a fallback strategy (cached value, default response) so that the system remains useful while the underlying bug is fixed.

## Limitations

The circuit breaker is a runtime defence, not a substitute for fixing the cause of the failure. It also does not protect against failures that occur inside the breaker itself: a bug in the breaker's state machine, a clock skew that miscalculates the cool-down, a missing metric that hides a half-open loop. The half-open state requires careful design because it is the only state in which the system knowingly sends traffic to a downstream that may be unhealthy; a poor half-open policy is worse than no circuit breaker at all. Finally, circuit breakers do not compose across calls. A caller may have a breaker around a downstream that itself has a breaker around its database; the breakers do not coordinate, and the system must be designed against the case where each breaker independently holds the line.

## Canonical sources

- Netflix Hystrix wiki — *How it Works*, defining the original closed/open/half-open state machine: https://github.com/Netflix/Hystrix/wiki/How-it-Works
- Martin Fowler — *CircuitBreaker* bliki entry, defining the pattern and the role of the half-open state: https://martinfowler.com/bliki/CircuitBreaker.html
- resilience4j documentation — *CircuitBreaker module*, modern treatment of half-open policy including sliding windows and trial semantics: https://resilience4j.readme.io/docs/circuitbreaker
- Microsoft Azure Architecture Center — *Circuit Breaker pattern*: https://learn.microsoft.com/en-us/azure/architecture/patterns/circuit-breaker
