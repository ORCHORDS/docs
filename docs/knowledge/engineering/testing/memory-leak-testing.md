# memory-leak-testing

**Issue:** Tests pass, the app ships, and then RSS/heap climbs steadily in production until the container is OOM-killed — because no test ever asserted that memory stays bounded over time
**Date:** 2026-08-12
**Status:** documented

## Symptom / Context

A feature works perfectly for one request. The test suite runs each case once, memory looks fine,
and the PR merges. In production, memory grows monotonically over hours/days until the process hits
its memory limit and is killed (Node), the tab crashes (browser), or Android displays the
"App keeps stopping" dialog (mobile).

Classic leak sources that single-shot tests never catch:
- event listeners added but never removed (`emitter.on(...)` inside a handler called per request)
- closures capturing large objects referenced by long-lived timers/intervals
- caches/Maps that grow without eviction and never get asserted against
- detached DOM nodes held by JS references after navigation
- WritableStream/ReadableStream handles not closed on abort
- WebSocket/EventSource connections not closed on unmount
- Android: static references, BroadcastReceiver not unregistered, Cursor not closed, Bitmap not
  recycled, Coroutine leak across configuration change

## Pattern / Solution

### 1. Loop the operation and assert heap plateaus
The signature of a leak is monotonic growth. Run the operation many times and assert memory
stabilises rather than grows without bound:
```ts
test("processing requests does not leak heap", async () => {
  // Warm up so JIT/GC internals stabilise.
  for (let i = 0; i < 50; i++) await processRequest(makePayload());

  globalThis.gc!();                       // requires --expose-gc
  const baseline = process.memoryUsage().heapUsed;

  for (let i = 0; i < 1000; i++) await processRequest(makePayload());
  globalThis.gc!();
  const after = process.memoryUsage().heapUsed;

  const growthPerOp = (after - baseline) / 1000;
  expect(growthPerOp).toBeLessThan(1024);  // <1KB/op retained
});
```
Run Node with `node --expose-gc`. The warmup phase is mandatory — the first iterations allocate
closures, inline caches, and module state that are not leaks.

### 2. Use Chrome DevTools Protocol (CDP) for browser leaks
For web apps, drive the page with Playwright and take heap snapshots between batches of interactions,
then diff the retained objects:
```ts
test("navigating to/from list 50x does not leak DOM nodes", async ({ page }) => {
  const client = await page.context().newCDPSession(page);
  await client.send("HeapProfiler.enable");
  await client.send("HeapProfiler.startSampling");
  for (let i = 0; i < 50; i++) {
    await page.goto("/list"); await page.goto("/");
  }
  const { profile } = await client.send("HeapProfiler.stopSampling");
  const detached = JSON.stringify(profile).match(/Detached/g) ?? [];
  expect(detached.length).toBeLessThan(5);
});
```
Assert specifically on `Detached` DOM nodes — these are nodes removed from the tree but still
referenced by JS, the canonical browser leak.

### 3. Mobile: assert via `dumpsys meminfo`
On Android, run a workload then capture per-process memory and assert it stays within a budget:
```bash
ADB="C:/path/to/project
for i in $(seq 1 50); do
  "$ADB" shell am start -n studio.mooneddev.example project/.MainActivity
  "$ADB" shell am force-stop studio.mooneddev.example project
done
"$ADB" shell dumpsys meminfo studio.mooneddev.example project | grep "TOTAL RSS"
# Parse and compare against a budget, e.g. < 300MB.
```
Also grep logcat for `LeakCanary` (if installed) which reports retained fragments/activities on
configuration change.

### 4. Snapshot-based leak detectors in unit tests
- Node: use `weakref`/`FinalizationRegistry` to assert a known-retained object is collected after
  release. If the finalizer never fires, something is holding it.
- Browser: `@testing-library/react` unmount + assert `getByText` throws is a cheap structural check,
  but combine with a heap snapshot for real leak detection.
- React Native / Capacitor: drive `unmount`/navigation and assert no listeners remain on shared
  emitters (keep a `Set` of registered listeners in dev mode and assert it's empty after teardown).

## Gotchas

- **GC is non-deterministic.** Without `--expose-gc` and an explicit `gc()` call, heap readings are
  meaningless — uncollected garbage looks identical to a real leak. Always expose and force GC
  before measuring.
- **Warmup matters.** The first N iterations allocate module-level singletons, JIT caches, and pool
  slots that are legitimately retained. Skip them or your test reports false leaks.
- **Threshold-based assertions are noisy on CI.** Use a per-operation growth bound (KB/op), not an
  absolute ceiling — absolute heap size varies with runner load. Also run leak tests in their own
  shard so unrelated suite allocations don't pollute the reading.
- **`process.memoryUsage().rss` includes native buffers and shared libs** — it is a blunt signal.
  Prefer `heapUsed` for V8/Node leaks, and `external` for native/Blob leaks. RSS alone leads to
  false positives.
- **Detached DOM node count of 0 is unrealistic** — browsers always retain a few internally. Pick a
  small non-zero budget (e.g. <5) rather than strict equality to 0.
- **FinalizationRegistry may never fire** even for truly-unreferenced objects — V8 runs finalizers
  on a best-effort basis. Treat absence-of-finalization as a hint, not proof.
- **Leaks often appear only across lifecycle events** (mount/unmount, navigation, config change).
  Single-shot unit tests almost never catch them; you must loop the lifecycle.
- **Android leaks frequently hide behind static fields and Bus receivers** that survive the
  activity. LeakCanary in debug builds is the cheapest way to find these — add it early.
- Long-running streams/connections are the #1 leak source in modern apps. For every test that opens
  a WebSocket/EventSource/ReadableStream, assert it is closed in the teardown (or use
  `ensureCleanedUp` style guards).

## Related
- streaming-sse-testing
- event-driven-testing
- react-testing-patterns
- mobile-browser-testing
- flaky-test-detection
- test-fixtures-patterns
- playwright-network-interception
