# WebAssembly JS Promise Integration JSPI Suspension

## Scope

Using JavaScript Promise Integration (JSPI) to let Wasm code await JavaScript promises without unwinding: the `WebAssembly.Suspending` wrapper for imports, `WebAssembly.promising` for exports, `processExitingError` behavior, stack-switch mechanics, and the restrictions on suspending inside non-suspendable contexts. Covers the embedding-side contract for compiled languages that call async I/O; excludes the toolchain's internal lowering (which varies per compiler) and excludes the Wasm GC proposal.

## Workflow or implementation guidance

Before JSPI, a Wasm module calling a JS import that returns a promise had two options: block the main thread (never acceptable) or restructure the entire call chain into a state machine (what Emscripten's asyncify and compiler async/await lowerings do, at a cost in code size and stack discipline). JSPI gives Wasm its own switchable stack: when an import suspends, the engine swaps the Wasm stack out, returns control to the JS event loop, and resumes it later with the resolved value — the Wasm code experiences a straight-line call.

Two wrappers compose the contract. `WebAssembly.Suspending` wraps an import function so calls to it may suspend; the Wasm side sees a normal synchronous call signature:

```js
const originalFetch = async (ptr, len) => {
  const url = readStringFromMemory(ptr, len);
  const res = await fetch(url);
  return writeBytesToMemory(new Uint8Array(await res.arrayBuffer()));
};

const imports = {
  env: {
    fetch_url: new WebAssembly.Suspending(originalFetch),
  },
};
```

`WebAssembly.promising` wraps an exported Wasm function so it can be called from ordinary JS: the wrapper returns a promise that settles when the suspended stack eventually completes:

```js
const { instance } = await WebAssembly.instantiate(moduleBytes, imports);
const runPipeline = new WebAssembly.promising(
  instance.exports.runPipeline
);
const result = await runPipeline(inputPtr);   // Wasm suspends at fetch_url, resumes here
```

The runtime rule that bites: suspension can only occur where the engine can switch stacks. A call that began in a `promising` export is suspendable; a call into Wasm from a normal JS entry point (a direct `instance.exports.foo()`, an event handler, a `getter`) is not, and a `Suspending` import invoked on that stack throws rather than deadlocks — historically surfaced as an exception telling you the import cannot suspend in this context. Every entry point that can reach suspending imports must be wrapped with `promising`.

The wrapped export's promise rejects with the error thrown inside the Wasm execution, which is the natural place for the error boundary. And the suspending import's resolved value crosses back as the Wasm function's return: the JS side should hand back an i32/f64/i64-compatible value or a pointer, not a JS object — objects need the GC proposal or an indirection table, so the common pattern is "JS owns the buffer, Wasm gets an index".

Cancellation and lifetime: each `promising` call allocates a stack; long-lived apps that fire thousands of pipelines should reuse a worker pool of instances or bound concurrency, since suspended stacks pin their linear memory (which is fine — it is the same instance) plus JS closures until resolution. A pipeline that suspends forever pins everything it touched; timeouts belong in the JS import (`AbortSignal` on the fetch inside the wrapper), not in Wasm.

Interop with the older `JS Promise Integration` experimental flag history: engines moved through `Suspender`-based APIs and stack-switching flag eras; the stable shape is `Suspending`/`promising` (plus `promising` on `WebAssembly.Function` for typed-function exports). Code written against the earlier `WebAssembly.Suspender` surface does not run on current engines — check which era a snippet predates before adopting it.

## Controls

- Every export reachable from suspendable paths goes through `WebAssembly.promising`; direct `instance.exports` calls to code that may suspend are treated as a build error, not a runtime surprise.
- All async I/O crosses the boundary as a `Suspending`-wrapped import with a plain-value return (pointer/index or primitive).
- Timeouts/cancellation implemented inside the JS wrapper (AbortController, race with a timer) because Wasm cannot cancel its own suspension.
- Bounded concurrency on `promising` calls (queue or pool) in long-lived pages to cap live suspended stacks.
- A single memory-ownership convention (JS allocates, Wasm indexes) documented for every suspending import, since suspension stretches buffer lifetimes across await points.

## Validation evidence

- Round-trip test: a pipeline calling two sequential suspending imports (fetch A, then fetch B dependent on A's bytes) resolves with correct assembled output — proves resume ordering and memory stability across suspensions.
- Non-suspendable-context test: call a suspend-reaching export directly (unwrapped) and assert the thrown error identifies the context; this pins the failure signature for on-call debugging.
- Cancellation test: abort the fetch inside the wrapper mid-suspension and assert the `promising` promise rejects and the instance remains usable for a subsequent call (no poisoned state).
- Concurrency soak: fire N > target concurrent `promising` calls through the bounded queue; assert memory ceiling and that all N settle, catching stack-pinning leaks via `performance.memory` sampling or heap snapshots.
- Baseline comparison: measure code size and throughput of the JSPI build against the asyncify/JS-async lowering it replaces on the real workload, since the win is workload-dependent.

## Failure modes and correction

- `TypeError`/engine error stating the import cannot suspend: the call stack entered Wasm without `promising`. Wrap the entry point, or restructure so suspending imports are only reachable from wrapped exports.
- Old code referencing `WebAssembly.Suspender` or `WebAssembly.Global` stack-switch tricks fails to exist: the API surface changed; migrate to `Suspending`/`promising`.
- Suspended pipeline never resumes and memory creeps: the awaited promise never settles (dropped rejection path). Add a rejection/timeout path in the wrapper and log hung suspensions by import name.
- Wasm reads a buffer that changed across the await: linear memory is shared with JS, and the JS side reused the region while the stack was suspended. Adopt the ownership convention (JS-side staging buffers keyed by request id).
- Deadlock-shaped hang with two wrappers: code tried to acquire a JS-side lock/signal while suspended; suspension cannot be used to park waiting on other in-page Wasm — restructure to plain async sequencing in JS.
- Exceptions from Wasm vanish: the error crossed as a rejected promise from the `promising` wrapper, but nothing awaited it. Attach `.catch` at the call site or route through the app error boundary.

## Limitations

- JSPI standardization and shipping status varies by engine; feature-detect `WebAssembly.Suspending` and keep the compiler's async lowering as the fallback target.
- Suspension is only at the Wasm/JS import boundary: a long-running pure-Wasm loop cannot be preempted by this mechanism.
- Passing structured JS values across suspending imports still requires pointer/index conventions unless the GC proposal types are in play.
- Stack allocation per suspended call has a cost; the mechanism targets I/O-shaped suspension, not per-frame granularity.
- Toolchain support (which imports to declare suspendable, export lowering) is per-compiler; the embedding contract above must be reconciled with each compiler's flags.

## Canonical sources

- WebAssembly CG, JS Promise Integration proposal: https://webassembly.github.io/js-promise-integration/
- TC39/Wasm CG, JSPI explainer repository: https://github.com/WebAssembly/js-promise-integration
- MDN, `WebAssembly.Suspending`: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/WebAssembly/Suspending
- MDN, `WebAssembly.promising`: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/WebAssembly/promising
