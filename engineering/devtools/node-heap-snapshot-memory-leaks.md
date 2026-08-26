# node-heap-snapshot-memory-leaks

**Issue:** A Node.js process's RSS climbs steadily over hours or days until it gets OOM-killed or slowed by GC pressure, but the code "looks fine" and no single commit is obviously guilty. This article covers the current heap-snapshot workflow — capturing snapshots safely, diffing them in Chrome DevTools with the three-snapshot technique, reading the retainers panel, and the leak patterns that cause most Node memory growth in practice.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Capturing heap snapshots

1. **DevTools Memory tab via `chrome://inspect`.** Run node with `--inspect`, attach from Chrome, open the Memory tab, and take a heap snapshot of the running isolate. Best for local reproduction where you control the process and can interact with it between snapshots.
2. **`--heapsnapshot-signal=SIGUSR2` for production.** Start the process with this flag and `kill -USR2 <pid>` writes a `.heapsnapshot` file to the working directory on demand — no debugger attached, no code changes. This is the production-friendly trigger recommended by the official Node.js diagnostics guide.
3. **`v8.writeHeapSnapshot()` programmatically.** Import `v8` and call `writeHeapSnapshot('/tmp/heap-1.heapsnapshot')` from an admin endpoint, signal handler, or scheduled job. Wrap it in try/catch — it throws if the file cannot be written (disk full, permissions).
4. **Force GC before baseline snapshots with `--expose-gc`.** Start node with `--expose-gc` and call `globalThis.gc()` (or click the trash icon in DevTools) before capturing, so garbage that merely has not been collected yet does not pollute the baseline. Never enable this flag casually in production — it changes GC behavior.
5. **Heap allocation timeline as a lower-overhead first pass.** In DevTools, "Allocation instrumentation on timeline" records each allocation with stack traces; a growing blue bar sequence points at the allocating code before you ever take a full snapshot, which matters because full snapshots pause the process.

## The three-snapshot diffing technique

1. **Take a baseline snapshot after warmup.** Exercise the app first so lazy module loading, caches, and JIT warm state exist; snapshotting a cold process makes everything look like growth.
2. **Exercise the suspected leak, then snapshot again.** Run the suspect operation repeatedly (N requests, N sessions, N file watches) — a leak that grows one object per operation shows up far more clearly at N=500 than N=2.
3. **Force GC and take the third snapshot.** The post-GC capture separates live, retained memory from pending garbage. An object count that keeps rising across post-GC snapshots is retained by definition — something holds a reference.
4. **Use Comparison view, not Summary view, for diffing.** Load the snapshots in order, select the later one, switch the view dropdown to "Comparison", and sort by "Size Delta" or "Objects Allocated" — Chrome then shows only what changed between the two captures, which is the entire point of the technique.
5. **Walk the Retainers panel to find the holder.** Select a growing object and read the retainer chain at the bottom of the Memory tab: it names the exact array, map, closure, or listener that keeps the object alive. The fix is always about that last retaining edge, not the leaked object itself.

## Common leak sources in Node

1. **Unbounded in-process caches.** A plain `Map` used as a cache with no eviction grows forever; replace with an LRU (e.g. `lru-cache`) with a max size, or `WeakMap`/`WeakRef` when keys' lifetimes can govern entry lifetimes.
2. **Event listener accumulation.** Adding listeners per request or per connection without `removeListener`/`off` (often on shared emitters, sockets, or Redis clients) retains both the closure and everything it captures; the MaxListenersExceededWarning is the classic early symptom.
3. **Closures and captures over large scopes.** A small exported callback that references a big request-scoped object (buffers, parsed bodies, `this`) keeps the whole scope alive; hoist what the callback truly needs, or restructure so short-lived data is not captured by long-lived handlers.
4. **Uncleared timers and intervals.** Every `setInterval` holds its callback and its captures until cleared; verify `clearInterval` on shutdown paths, and remember that a repeating timer also keeps the surrounding module state alive forever.
5. **Buffering streams and promise chains.** Piping into an accumulating array or string, or fire-and-forget promise chains that collect resolved values (e.g. unbounded `Promise.all` batches), pins large buffers in memory; prefer backpressure-aware `pipeline()` and bounded concurrency queues.

## Production safety rules

1. **Know that snapshotting is stop-the-world.** Writing a heap snapshot pauses the process for a period proportional to heap size; on a 2 GB heap that can be seconds. It is a diagnostic action, not something to schedule every minute.
2. **Drain traffic before capturing.** Take the instance out of the load balancer (or stop the timer feed) before triggering SIGUSR2 so the pause hits an idle worker, then put it back — a single-instance pause under full load can cascade into timeouts.
3. **Plan for file size and disk.** The `.heapsnapshot` file is roughly the size of the heap and often bigger as JSON; check disk space before triggering, write to a scratch volume, and stream the file off the box (they compress well with gzip).
4. **Treat snapshots as sensitive data.** A heap snapshot contains strings from the live heap — tokens, API keys, user PII. Handle, store, and share them like a database dump; open them locally or in a client-side-only viewer rather than pasting them into random web tools.
5. **Correlate with metrics before and after.** Capture `process.memoryUsage()` (especially `heapUsed` after GC), RSS from `ps`, and the operation count at each snapshot; "heap grew 40 MB over 10k requests, retained objects are X" is a reproducible report, while "memory is high" is not.
