# Agent Clock Monotonic For Retry

## Scope

This article covers the use of monotonic clocks inside agent retry loops to compute exponential backoff, jitter, and deadline budgets. A monotonic clock is a clock whose value is guaranteed never to decrease and whose rate is independent of wall-clock adjustments. Most operating systems expose `CLOCK_MONOTONIC` on POSIX systems, `QueryPerformanceCounter` on Windows, and `performance.now()` on Node.js. The article explains why monotonic time is the right primitive for retry timing and how to use it correctly when interacting with external systems that report wall-clock timestamps.

Out of scope: clock synchronization protocols such as NTP and PTP, distributed consensus on time, and ordering of events across machines. Monotonic clocks are local to a single process; cross-machine ordering requires sequence numbers or hybrid logical clocks, not wall clocks.

## Implementation workflow

Capture a monotonic start value when the retry loop begins and store it alongside the task identity. Compute every deadline (next retry time, total retry budget, hard timeout) as a monotonic delta from this start, expressed in seconds with nanosecond or microsecond precision depending on the platform. Convert back to wall time only at the moment of acting on a deadline, and only if the deadline needs to be communicated to an external system.

The retry schedule itself is computed at scheduling time, not at retry time. Given a base delay `d`, a multiplier `m`, a maximum delay `D`, and a jitter strategy `j`, the k-th retry is scheduled for monotonic `start + min(D, d * m^k) + j(k)`. The schedule is stored in the task's persistent state so that a crash and restart resumes the same schedule rather than recomputing and double-backing off. This is the same approach used in HTTP/2 connection coalescing and TCP retransmission; both rely on a schedule that survives process restarts.

Jitter must use a cryptographic or high-entropy source for any retry loop that is shared across many agents competing for the same upstream service. Full jitter (`Uniform(0, scheduled_delay)`) decorrelates retry waves and is preferred when the upstream is the bottleneck. Equal jitter (`delay/2 + Uniform(0, delay/2)`) preserves a useful minimum spacing and is appropriate when the agent itself is rate-limited by an outbound token bucket. The AWS Architecture Blog post on exponential backoff and jitter remains a widely-cited reference for these patterns.

When an upstream returns a `Retry-After` header, parse it as wall-clock time and convert to a monotonic deadline at parse time. Do not store the wall-clock value and compare it later — by the time the agent reads it, the wall clock may have stepped. Convert once, store the monotonic deadline, and compare monotonic values throughout the retry loop. This pattern aligns with RFC 9110's guidance on `Retry-After` parsing.

When persisting a deadline that must later be communicated to a different process (for example, when handing off a partially completed task to another worker), store the deadline as both a monotonic delta and an authenticated wall-clock projection. The receiving process validates the projection against its own monotonic clock after accounting for the time spent in transit, and rejects the handoff if the validation fails.

## Controls

Monotonic clocks are not the source of truth for audit timestamps. Wall-clock UTC remains the right primitive for any timestamp that humans or external systems must read or correlate. The retry loop records both: the monotonic deadline drives local scheduling, and a wall-clock projection is included in telemetry and audit records. The two clocks are not directly comparable; never compute `wall_clock - monotonic_clock`.

Detect and respond to monotonic clock anomalies. A monotonic clock that jumps backward indicates a serious problem: a hypervisor live migration, a debugger intervention, or an operating-system bug. Treat any backward jump of more than a configured threshold (commonly 100 milliseconds) as a fault event. The agent should log the anomaly, recompute deadlines relative to the new monotonic base, and notify the supervisor that downstream timing assumptions may be invalid.

Bound the retry budget in absolute terms, not only in count. A retry loop with a count cap but no time cap can still run for an unbounded wall-clock duration on a heavily loaded system where each retry takes minutes. Express both an attempt cap and a wall-clock cap; whichever fires first terminates the loop. The retry budget article in this family elaborates on the interaction between count, time, and cost caps.

## Validation evidence

Conformance tests must cover: backoff under monotonic time stepping forward at a steady rate, backoff under wall-clock adjustment (the agent must not observe the adjustment), recovery from a simulated monotonic jump backward, conversion of `Retry-After` to monotonic deadline, persistence of the retry schedule across simulated crash, handoff of a deadline to another process with bounded clock skew, and correct behavior at both attempt and time caps. Inject wall-clock changes via test hooks and confirm the retry schedule is unaffected.

Operational evidence includes: distribution of inter-retry delays, jitter distribution (verify it is not collapsing to a constant), distribution of total retry-loop duration, count of detected monotonic anomalies, and a correlation between retry-loop duration and observed upstream recovery time. A retry loop whose total duration is uncorrelated with upstream behavior suggests the schedule has been disturbed by wall-clock interaction.

## Failure handling

When the monotonic clock source itself becomes unreliable — for example, on a system under heavy live migration — the agent must terminate any in-flight retry loops whose deadlines cannot be trusted, surface a `clock-unreliable` error to the supervisor, and refuse to begin new retry loops until the clock source has been verified. Do not silently continue; a retry loop that fires early or late under an unreliable clock can amplify load rather than relieve it.

When a `Retry-After` value cannot be parsed safely (malformed, far in the past, or implausibly far in the future), fall back to the local exponential schedule with full jitter and log the rejection. Never silently substitute the local schedule without indication; the substitution is a degraded mode that should be visible in telemetry.

When the retry budget is exhausted, do not automatically retry under a fresh budget. The retry budget article in this family discusses the broader discipline; specifically, exceeding the retry budget indicates that the upstream is not recovering as expected, and a human-in-the-loop decision or escalation is appropriate before the next attempt cycle.

## Canonical sources

- IEEE Std 1003.1-2017, POSIX.1, `clock_gettime` and `CLOCK_MONOTONIC`: https://pubs.opengroup.org/onlinepubs/9699919799/functions/clock_gettime.html
- RFC 9110, HTTP Semantics, Section 10.2.3 `Retry-After`: https://www.rfc-editor.org/rfc/rfc9110#section-10.2.3
- IETF RFC 1305 (NTP) — referenced for the limitations of wall-clock time when used for scheduling: https://www.rfc-editor.org/rfc/rfc1305
- AWS Architecture Blog, "Exponential Backoff and Jitter" (canonical reference for jitter strategies): https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/
