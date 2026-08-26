# JS Self-Profiling API bounded sampling

**Issue:** Production JavaScript profiling is either disabled entirely or enabled for every page with an unbounded trace. Profiling overhead harms Core Web Vitals, stack metadata creates privacy risk, and buffer exhaustion silently ends the session.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** experimental — WICG draft, feature-detect

## API model

The WICG JS Self-Profiling draft defines `Profiler` with required `sampleInterval` and `maxBufferSize` options. Sampling is best effort: the user agent is not required to sample at exactly the requested interval and may pause a session when the context is not foregrounded.

When the sample buffer reaches its limit, the profiler fires `samplebufferfull` and moves to stopped. `stop()` returns the trace; calling it again rejects with `InvalidStateError`. Treat “buffer full” and “manually stopped” as explicit terminal paths.

## Controlled experiment

1. Feature-detect `globalThis.Profiler` and required policy support. Keep normal instrumentation as the fallback.
2. Select a small, stable cohort server-side before page work begins. Exclude sensitive routes and respect the product's consent/privacy contract.
3. Set a coarse interval and a strict sample cap derived from an overhead and upload budget. Never accept either directly from query parameters.
4. Start only for a bounded scenario (page load or a named operation). Attach the buffer-full listener immediately and funnel all termination through one stop-once owner.
5. Sanitize/aggregate traces before upload. Resource URLs, function names, line/column data, timing, and route context can reveal application or user information.
6. Compress, rate-limit, sample uploads, apply retention limits, and separate test/live datasets.
7. Correlate with coarse performance metrics using pseudonymous experiment IDs, not user content or stable cross-site identifiers.
8. Automatically disable the cohort when overhead, errors, upload bytes, or vital regressions cross a budget.

## Document Policy tradeoff

The draft defines `js-profiling-mode=eager` and `lazy`. Eager authorizes and prepares for profiling during load but can add FCP/LCP overhead even when no profiler is used. Lazy defers initialization, which avoids unconditional load cost but can add interaction-time work that affects INP. Choose from the experiment's measurement window and verify actual browser behavior.

The older boolean `js-profiling` policy is deprecated in the draft in favor of `js-profiling-mode`.

## Verification

Test unsupported/disallowed policy, valid eager/lazy mode, background pause, empty stack, cross-origin/muted script attribution, buffer full, manual stop, double stop, navigation, page lifecycle, slow upload, offline state, and cohort disabled. Use the draft's WebDriver force-sample extension where supported for deterministic tests.

Compare FCP, LCP, INP, CPU, memory, battery proxy, and bytes for profiled versus control cohorts. Profiling is acceptable only if its own cost stays inside the declared budget.

## Gotchas

- Requested interval is not guaranteed sampling frequency.
- Traces are diagnostic data and need data-minimization review.
- WICG draft shape and browser support can change.
- Multiple profilers multiply overhead; enforce a page-level session budget.

## Sources

- [WICG — JS Self-Profiling API](https://wicg.github.io/js-self-profiling/)
