# resilience-circuit-breaker-testing

**Issue:** Production code is full of resilience machinery: circuit breakers, retries with exponential backoff, timeouts, bulkheads, and fallbacks, configured through libraries such as Resilience4j or hand-rolled equivalents. This machinery exists precisely for the conditions unit tests never create (dependencies slow, failing, or recovered), so it tends to sit untested until a real outage reveals that the breaker never opens, the retry storm makes things worse, or the fallback throws. Resilience patterns are behavior, and testing them means driving failures deliberately, controlling time, and asserting on state transitions and side effects rather than just happy-path return values.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Circuit breaker state machine tests

1. **Assert the full state cycle: CLOSED to OPEN to HALF_OPEN and back.** Drive enough consecutive failures to trip the breaker, assert calls are rejected fast (no network attempt) while OPEN, let the wait duration elapse, assert a probe call passes and the breaker closes again. Libraries expose state (Resilience4j CircuitBreaker.getState), so assertions are direct, not inferred from call counts alone.
2. **Verify the failure-rate threshold, not just "eventually opens."** Assert the exact configured threshold behavior: below the threshold the breaker stays closed, at or above it, it opens, based on the sampling window. Off-by-one bugs in threshold logic are common and only surface with precise assertions.
3. **Test that OPEN means no downstream calls.** Wrap the dependency in a counting fake; once the breaker is open, calls must fail locally with zero invocations of the dependency, proving the breaker actually protects the failing service from retry floods.
4. **Test slow-call handling, not just exceptions.** Breakers that trip on duration (slow-call rate) need tests where the dependency hangs rather than errors; a hanging dependency is the more realistic outage, and it exercises timeout-plus-breaker interaction.
5. **Assert HALF_OPEN admits only the permitted probes.** During the half-open window, only the configured number of trial calls should reach the dependency; concurrent callers must be rejected until the probe resolves.

## Retry and backoff verification

1. **Count attempts, not just outcomes.** The retry test's core assertion is that exactly N attempts occurred with the final result propagated; a counting test double provides both. This catches silent retry (masking instability) and missing retry (failing fast when resilience was the point).
2. **Assert exponential backoff with jitter, compressed in time.** Real backoff delays of seconds make tests crawl; inject a fake or virtual clock and assert the delay sequence matches the configured curve within jitter bounds. Testing real sleeps proves only that the test suite is slow.
3. **Verify retry is for transient failures only.** A 4xx business error or validation rejection must not be retried; assert that non-retryable failures surface immediately after one attempt, or a client bug becomes a latency and load problem.
4. **Retry budget and cap enforcement.** Assert the maximum attempts cap holds even when all attempts fail, and that the total wall-clock budget is bounded by the outer timeout; unbounded retry-plus-backoff composition is a self-inflicted outage.
5. **Interaction with the breaker ordering.** The conventional stack orders retry inside the breaker (or breaker outside retry), so the breaker sees the final outcome of retries rather than counting each attempt as a fresh failure; test that the chosen composition counts failures at the intended layer, because the inverse ordering opens the breaker prematurely.

## Fault injection technique

1. **Use the library's test amenities before building custom ones.** Resilience4j integrates with test frameworks and exposes registries, metrics (via Micrometer), and state listeners; asserting through these official surfaces is less brittle than reaching into internals.
2. **Make the dependency fake programmable per failure mode.** A single fake supporting fail-n-times, always-fail, hang-for-duration, and fail-then-recover covers every resilience scenario; ad-hoc stubs per test duplicate this endlessly.
3. **Inject failures at the network boundary for integration depth.** Contract-test and service-virtualization tools (WireMock-style fault injection: connection reset, latency, truncated responses) verify resilience behavior over the real HTTP stack, catching cases like retry-on-reset that mocks at the client interface miss.
4. **Verify fallbacks actually work.** Assert the fallback's output is usable by callers (correct shape, degraded-but-valid data) and that the fallback itself is not a decorated call back into the failing dependency.

## Keeping resilience honest over time

1. **Assert resilience metrics in tests.** Because resilience libraries emit metrics (calls, failures, state transitions), tests can assert on metric deltas, which doubles as protection against config drift silently disabling a breaker.
2. **Pin resilience configuration in reviewed config tests.** A test that snapshots breaker thresholds, retry caps, and timeout values fails when someone edits the YAML without updating the expected contract, forcing the change to be deliberate.
3. **Chaos-style scheduled runs.** On a schedule, run the suite against an environment where a dependency is actually stopped or delayed; library-level tests verify mechanics, the scheduled run verifies wiring (that the production config actually routes this call through the breaker).
4. **Assert outage recovery, not just survival.** After failures clear, the system must return to full throughput: breakers close, retry rates drop to baseline, and cache-fallback state drains. Recovery assertions prevent half-degraded systems lingering after an incident.
