# Node stream.compose abort and destroy propagation

**Issue:** `stream.compose(...streams)` builds a Duplex by piping each component through `stream.pipeline`. If any component errors, Node destroys every component and the outer Duplex. Code that tries to reuse a component or treats one error as locally recoverable can lose data, leak listeners, or double-run cleanup.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Give each composed pipeline exclusive ownership of its component streams; do not reuse a source, transform, or sink after failure or destruction.
- Make `_destroy`, iterator `return`, generator `finally`, and resource-release handlers idempotent.
- Attach error handling to the returned outer Duplex and observe component failures for diagnostics without consuming them as success.
- Propagate one AbortSignal through the operation and translate abort to a distinct terminal outcome.
- Stop producers when downstream backpressure, error, close, or abort occurs.
- Define partial-output commit rules; stage externally visible results until the composed operation is accepted.
- Verify support and stability against the exact Node version—`stream.compose` was marked stable in Node 26.2.0.

## Implementation and tests

Compose a readable source, transform or async generator, and writable sink. Inject an error into each component in turn and assert all components plus the outer Duplex are destroyed, resources close once, and no further chunk is accepted. Abort before the first chunk, during backpressure, during an awaited transform, and after normal completion.

Also test premature consumer close, synchronous factory throw, Web Stream interop, duplicate errors, and downstream pipeline composition. Track `close`, `error`, `finish`, and `end` ordering without assuming all events fire on every terminal path.

## Gotchas

Destruction is not transactional rollback: bytes already written or remote side effects already performed remain. The outer Duplex is part of the destruction set. `readable.compose(stream, { signal })` destroys the composed stream when aborted; generic AbortSignal attachment similarly behaves like destruction with an `AbortError`.

Older supported Node lines may expose the API with a different stability status or behavior. Run the failure matrix on every deployed runtime.

## Official sources

- [Node.js stream documentation: stream.compose](https://nodejs.org/api/stream.html#streamcomposestreams)
- [Node.js stream documentation: readable.compose](https://nodejs.org/api/stream.html#readablecomposestream-options)
- [Node.js stream documentation: stream.addAbortSignal](https://nodejs.org/api/stream.html#streamaddabortsignalsignal-stream)
