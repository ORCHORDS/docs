# Node TracingChannel late-subscriber and context gaps

**Issue:** Node `TracingChannel` publishes a coherent action lifecycle only when subscribers are present before the trace starts. Adding instrumentation mid-operation can produce no later events for that trace, and using the wrong wrapper shape can omit asynchronous lifecycle events or lose AsyncLocalStorage context.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented; API stability varies by Node release

## Controls

- Create and reuse one top-level channel; register subscribers before accepting work and unsubscribe during controlled shutdown.
- Match `traceSync`, `tracePromise`, or `traceCallback` to the actual function contract; validate callback position explicitly.
- Bind AsyncLocalStorage on start and restore it on asynchronous phases where required; keep correlation data minimal and non-sensitive.
- Pin the Node release and re-check stability before using experimental BoundedChannel or store-scope APIs.

## Verification

1. Trace success, synchronous throw, rejected promise, callback error, and callback success; assert the expected start/end/error/async events and shared context object.
2. Subscribe after start and prove the operation is deliberately absent rather than partially represented.
3. Exercise nested traces, concurrent requests, worker threads, and known context-loss boundaries.
4. Confirm subscriber exceptions or telemetry backpressure cannot alter application results.

## Gotchas

A non-Promise returned to `tracePromise` yields no async start/end lifecycle. Late subscriptions do not join an in-flight trace. Diagnostics context can contain application objects, so publishing it without minimisation can leak data.

## Official sources

- https://nodejs.org/api/diagnostics_channel.html#class-tracingchannel
- https://nodejs.org/api/async_context.html
