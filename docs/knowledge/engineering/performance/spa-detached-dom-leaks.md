# spa-detached-dom-leaks

**Issue:** Long-lived SPA sessions (dashboards, email clients, feed apps that stay open for hours) slowly grow from 80MB to 600MB until the tab stutters and the user rage-refreshes. The dominant cause is not closures over big arrays — it is detached DOM nodes: subtrees removed from the document but still referenced by listeners, framework caches, observer callbacks, or stray module-level variables. Detached nodes are invisible in normal profiling because DevTools heap snapshots only flag them when you know to look.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Root Causes

1. **Event listeners outliving their targets.** `document.addEventListener('scroll', handler)` where the closure captures a component's root node keeps the entire removed subtree alive. The listener must be removed in cleanup (`useEffect` return, `disconnectedCallback`, `onDestroy`) — the framework unmounting the DOM does not detach listeners registered on ancestors of it.
2. **Module-level and global caches.** A `Map` keyed by DOM node (view caches, virtual-list item pools without eviction, WeakMap-free memoization) pins every node ever inserted. Use `WeakMap`/`WeakSet` for node-keyed metadata so entry lifetime follows node lifetime.
3. **Timers and intervals holding scope.** `setInterval` callbacks that touch component state after unmount keep the closure — and everything it references, including DOM handles — permanently live. Clear timers in cleanup; a stale interval is both a memory leak and a runtime error source.
4. **Observer callbacks and refs.** `ResizeObserver`, `IntersectionObserver`, and MutationObserver hold strong references to observed elements until `disconnect()`/`unobserve()`. Storing a `ref.current` in an external store or global event bus has the same effect.
5. **Framework internals doing it for you.** Retained component instances (a modal kept "hidden" instead of unmounted), router view caches, and state managers holding serialized DOM-adjacent data (Selection ranges, Range objects) each pin subtrees without any obvious culprit line in your code.

## Detection Workflow

1. **Performance Monitor first.** In Chrome/Edge DevTools, watch the "DOM Nodes" counter while repeating the suspect flow (navigate to list, open item, go back, 20 times). A healthy app plateaus; a leak climbs linearly. This is the cheapest confirmation that the leak is DOM, not JS heap.
2. **Three-snapshot technique.** Memory tab → Heap Snapshot → run the flow N times → snapshot → run again → snapshot. Compare and filter the summary for "Detached"; growth in `Detached <div>` / `Detached HTMLElement` counts between snapshots is the smoking gun. Retainers view then shows exactly what pins the subtree.
3. **Edge Detached Elements tool.** Microsoft Edge DevTools ships a dedicated "Detached Elements" profiling type that enumerates detached DOM objects and their sizes directly, which is faster than eyeballing snapshot diffs on large heaps. Chrome users fall back to snapshot filtering.
4. **Memory recording with allocation stacks.** Allocation instrumentation on timeline records where detached nodes were created; with the track-allocation-stack option you get the constructor site, collapsing the search from "what holds it" to "what made it".
5. **Automate with MemLab.** Meta's Memlab runs scripted Puppeteer scenarios (visit → interact → back) and diffs heap snapshots in CI, failing the build on detached-node growth. It detects leak classes (detached DOM, closure growth) without a human reading flamegraphs.

## Framework-Specific Causes

1. **React: cleanup-free effects.** Every `window.addEventListener` in a `useEffect` without a matching removal in the returned cleanup leaks on unmount; with React 18 StrictMode double-mounting in dev, the leak manifests as duplicated handlers even in development.
2. **React: stale refs in external code.** `ref.current` stored into a module singleton or passed to a long-lived subscription keeps the node after unmount because nothing nulls the ref except a subsequent mount on the same component instance.
3. **Vue: watchers on removed components.** Watchers created outside the component's scope (`watchEffect` in a store) that reference component DOM or reactive state keep the component tree from being collected.
4. **Routing-level retention.** Keep-alive style caching, persisted scroll containers, and "shell stays, content swaps" architectures leak when the swap path forgets an observer or listener attached to the outgoing content.

## Fixes and Prevention

1. **Cleanup symmetry rule.** Any API with an `add`/`observe`/`subscribe` gets its inverse (`remove`/`disconnect`/`unsubscribe`) in the same function that created it — effect cleanup, destroy hook, or `AbortController` signal passed to `addEventListener` so one `abort()` removes a whole batch.
2. **Weak references for node-keyed data.** Replace `Map<HTMLElement, T>` caches with `WeakMap`; prefer `WeakRef` for caches that must not extend lifetime.
3. **Null out handles in teardown.** Explicitly set `this.root = null`, `ref.current = null` in component teardown when handles escape into external structures; do not rely on GC "noticing".
4. **Leak tests in CI.** A nightly Playwright/Puppeteer test that loops the top 5 navigation flows 25 times and asserts DOM-node count growth stays under a threshold catches regressions before support tickets do.
5. **Production signals.** Ship a lightweight RUM counter (heap `usedJSHeapSize`, or a periodic `document.getElementsByTagName('*').length` sample for the live side) tagged by route so leaks surface as per-route memory trends in field data.

## Gotchas

1. **Detached nodes reported by DevTools are not all leaks.** Frameworks legitimately pool a few detached nodes (React root containers, virtual lists); judge by growth trend across repeated cycles, not absolute presence.
2. **Snapshot "Detached" filter hides size.** Sort by retained size, not count — one detached tree of 40,000 nodes outweighs thousands of small detached spans.
3. **Fixing the closure but not the listener.** Removing the captured data while leaving the listener registered on `document` still pins the closure scope; the removal API call is the fix, not shrinking the closure.
4. **Mobile devices crash first.** iOS Safari kills tabs at lower memory ceilings than desktop; verify fixes on a mid-range phone with a 30-minute soak, not just in desktop DevTools.

## Related

closure-memory-leaks, chrome-devtools-memory, memory-management-js, garbage-collection-optimization, dom-manipulation-performance
