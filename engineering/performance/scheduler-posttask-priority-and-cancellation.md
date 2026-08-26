# scheduler.postTask priority and cancellation control

**Issue:** An application queues all deferred main-thread work through timers. Urgent interaction work sits behind background maintenance, canceled views still commit results, and developers raise every task to the highest priority to compensate, creating starvation and unstable responsiveness.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** limited availability; feature-detect

## Problem and applicability

The Prioritized Task Scheduling API exposes scheduler.postTask with user-blocking, user-visible, and background priorities. It supports cancellation through AbortSignal and, with TaskController, mutable task priority where implemented.

Use it to express relative scheduling intent for bounded main-thread tasks. Move sustained CPU-heavy work to a Worker; scheduling priority does not make expensive work cheap.

## Controls and implementation

1. Classify work from user impact, not team ownership. Reserve user-blocking for the shortest work required for an active interaction, use user-visible for near-term rendering, and put speculative maintenance in background.
2. Pass an AbortSignal for any task owned by a route, component, request, or view generation. Abort when the owner disappears and also check application freshness before committing a result.
3. Choose either an explicit postTask priority or a TaskSignal-based priority contract intentionally. An explicitly supplied priority is not retroactively changed just because some external controller changes.
4. Use TaskController only when a queued activity genuinely needs dynamic reprioritization. Centralize priority changes and bound them so unrelated modules cannot turn all background work into user-blocking work.
5. Keep each callback short and yield or split at correctness-safe boundaries. A high-priority long task still blocks input and rendering.
6. Handle promise rejection from cancellation and callback failure. Do not report an expected AbortError as an application crash.
7. Feature-detect scheduler.postTask and preserve semantic ordering in a fallback queue built on ordinary tasks. Document that fallback priority is approximate.
8. Add fairness controls for producer loops: cap queued tasks, coalesce superseded work, and allow lower-priority maintenance to progress during sustained interaction.

## Verification

Test all priority levels, FIFO behavior within relevant cohorts, abort before queueing and while waiting, task failure, route teardown, dynamic priority change, repeated reprioritization, queue saturation, hidden tabs, unsupported browsers, and long callback chunking.

Profile input delay and total completion time on slow devices. Assert canceled or stale tasks never mutate current UI and background work eventually advances under a realistic interaction stream.

## Gotchas

- Priority is a scheduling hint within the user agent, not a deadline or CPU reservation.
- postTask callbacks still run on the main thread.
- Promise microtasks created inside a callback can extend its blocking work.
- scheduler.yield continuation ordering is related but has a different chunking role; do not duplicate whole jobs across both APIs.

## Official sources

- [WICG — Prioritized Task Scheduling API](https://wicg.github.io/scheduling-apis/)
- [WHATWG HTML — Event loops](https://html.spec.whatwg.org/multipage/webappapis.html#event-loops)
