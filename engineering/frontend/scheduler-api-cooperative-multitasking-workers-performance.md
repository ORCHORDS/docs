# Scheduler API — Cooperative Multitasking for Cloudflare Workers and Browser UIs

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Long JavaScript tasks block the browser's main thread, causing high INP (Interaction to
Next Paint) scores and janky animations. You need to break large chunks of work — data
processing, rendering large lists, applying diff patches — into prioritized microtasks
that yield to user input and paint between each chunk.

## Context

The **Scheduler API** (`scheduler.postTask()`) is a browser API (Chrome 94+, Firefox
101+) that lets you schedule tasks with a named priority (`user-blocking`, `user-visible`,
`background`) and abort them via `AbortSignal`. It is the successor to hacks like
`setTimeout(fn, 0)` and `MessageChannel` yielding.

In Cloudflare Workers the same shape appears in the **`scheduler.wait()` API** (Workers
runtime ≥ 2023-03-01) — a sleep primitive for cooperative async scheduling in edge code.
The two contexts share terminology but differ in semantics; this article covers both.

## Browser: scheduler.postTask() Priorities

```typescript
// lib/scheduler.ts — browser

type TaskPriority = 'user-blocking' | 'user-visible' | 'background';

/**
 * Yield to the browser between chunks of work.
 * Falls back to a MessageChannel-based yield when scheduler API is unavailable.
 */
export function yieldToMain(): Promise<void> {
  if ('scheduler' in globalThis && 'yield' in (scheduler as any)) {
    return (scheduler as any).yield(); // Chrome 115+ scheduler.yield()
  }
  return new Promise<void>((resolve) => {
    const mc = new MessageChannel();
    mc.port1.onmessage = () => resolve();
    mc.port2.postMessage(null);
  });
}

/**
 * Run an array of items through a callback in chunks, yielding between each.
 * Uses scheduler.postTask for prioritized execution.
 */
export async function processInChunks<T, R>(
  items: T[],
  processor: (item: T, index: number) => R,
  options: {
    chunkSize?: number;
    priority?: TaskPriority;
    signal?: AbortSignal;
  } = {},
): Promise<R[]> {
  const { chunkSize = 10, priority = 'user-visible', signal } = options;
  const results: R[] = [];

  for (let i = 0; i < items.length; i += chunkSize) {
    if (signal?.aborted) throw new DOMException('Aborted', 'AbortError');

    const chunk = items.slice(i, i + chunkSize);

    const chunkResults = await new Promise<R[]>((resolve, reject) => {
      const task = () => {
        try {
          resolve(chunk.map((item, j) => processor(item, i + j)));
        } catch (err) {
          reject(err);
        }
      };

      if ('scheduler' in globalThis && 'postTask' in (scheduler as any)) {
        (scheduler as any).postTask(task, { priority, signal });
      } else {
        setTimeout(task, 0);
      }
    });

    results.push(...chunkResults);
    await yieldToMain(); // yield between chunks regardless
  }

  return results;
}
```

## Browser: Prioritized Data Pipeline for Large Tables

```typescript
// components/DataTable.tsx  (React 19)
import { useTransition, useDeferredValue, useState } from 'react';
import { processInChunks } from '../lib/scheduler';

interface Row { id: string; value: number; label: string }

export function DataTable({ rawData }: { rawData: Row[] }) {
  const [query, setQuery] = useState('');
  const [isPending, startTransition] = useTransition();
  const [processed, setProcessed] = useState<Row[]>([]);
  const deferredQuery = useDeferredValue(query);

  async function handleSearch(q: string) {
    setQuery(q);
    startTransition(async () => {
      const controller = new AbortController();
      const results = await processInChunks(
        rawData,
        (row) => ({ ...row, label: row.label.toUpperCase() }),
        { chunkSize: 50, priority: 'user-visible', signal: controller.signal },
      );
      setProcessed(results.filter((r) => r.label.includes(q.toUpperCase())));
    });
  }

  return (
    <div>
      <input value={query} onChange={(e) => handleSearch(e.target.value)} />
      {isPending && <span aria-live="polite">Filtering…</span>}
      <table>
        <tbody>
          {processed.map((row) => (
            <tr key={row.id}><td>{row.label}</td><td>{row.value}</td></tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

`useTransition` + chunked `scheduler.postTask` keeps INP under 200 ms even for 50 000
rows by letting input events interrupt filter work.

## Cloudflare Workers: scheduler.wait() for Cooperative Edge Tasks

In Cloudflare Workers `scheduler.wait(ms)` suspends execution, yielding CPU to other
isolate tasks. Use it to avoid hitting the CPU time limit on long-running Workers or to
add jitter in retry loops.

```typescript
// workers/bulk-processor.ts
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const { ids } = await req.json<{ ids: string[] }>();
    const results: Record<string, unknown> = {};

    for (const id of ids) {
      results[id] = await processOne(id, env);
      // Yield every iteration so other fetch events are not starved
      await scheduler.wait(0);
    }

    return Response.json(results);
  },
};

async function processOne(id: string, env: Env) {
  const data = await env.KV.get(id, 'json');
  return data ?? null;
}
```

`scheduler.wait(0)` is the Workers equivalent of `await Promise.resolve()` but
officially supported and stable.

## Measuring Impact with PerformanceObserver

```typescript
// lib/monitor-long-tasks.ts — browser only
export function monitorLongTasks(threshold = 50): () => void {
  if (!('PerformanceObserver' in globalThis)) return () => {};

  const observer = new PerformanceObserver((list) => {
    for (const entry of list.getEntries()) {
      if (entry.duration >= threshold) {
        console.warn(`Long task: ${entry.duration.toFixed(1)}ms`, entry);
      }
    }
  });

  observer.observe({ type: 'longtask', buffered: true });
  return () => observer.disconnect();
}
```

Pair with `web-vitals` INP measurement to confirm scheduler changes reduce p75 INP
before and after deployment on Cloudflare Pages.

## Anti-patterns

- **`setTimeout(fn, 0)` for priority.** `setTimeout` cannot express priority; all
  callbacks land in the task queue at the same level. Use `scheduler.postTask` with
  `user-blocking` for critical work.
- **Blocking loops in Workers.** CPU-bound loops in a Worker isolate prevent other
  requests from being served. Insert `scheduler.wait(0)` every N iterations.
- **Ignoring AbortSignal.** If the user navigates away mid-chunk, the signal fires but
  work continues until the loop finishes. Check `signal.aborted` in the loop guard.
- **Scheduling too many microtasks.** A `chunkSize` of 1 causes overhead from excessive
  yielding. Profile to find the chunk size that keeps individual tasks under 16 ms.

## Gotchas

- `scheduler.yield()` (a shorthand for postTask at the current priority) is Chrome 115+.
  The `processInChunks` fallback covers older Chrome and Firefox.
- TypeScript: `scheduler` is not yet in `lib.dom.d.ts`. Add a declaration:

```typescript
// types/scheduler.d.ts
declare var scheduler: {
  postTask<T>(
    callback: () => T | Promise<T>,
    options?: { priority?: 'user-blocking' | 'user-visible' | 'background'; signal?: AbortSignal; delay?: number }
  ): Promise<T>;
  yield(): Promise<void>;
};
```

- In Cloudflare Workers `scheduler.wait` is not the browser Scheduler API — it is a
  Promise-based sleep. Do not reference `scheduler.postTask` in Workers code.
- Background tasks (`priority: 'background'`) may be deferred indefinitely while the
  user is actively interacting. Do not use `background` for anything that must complete.

## Verification

1. Chrome DevTools → Performance → record while scrolling the DataTable. Confirm tasks
   stay under 50 ms (no red "Long Tasks" markers).
2. `web-vitals` `onINP` callback: compare p75 before/after enabling scheduler chunking.
3. Workers: add `console.time` around the loop; `scheduler.wait(0)` adds ~0 ms overhead
   while preventing CPU-time-limit errors on lists > 1 000 items.
4. Abort test: navigate away mid-filter; console should not log further chunk results
   after the route change triggers `controller.abort()`.

## Related

- `html-web-vitals-inp.md`
- `browser-web-workers.md`
- `react-suspense-boundaries.md`
- `data-table-virtualization-sorting-filtering.md`
- `browser-performance-api.md`

## Sources

- https://developer.chrome.com/docs/web-platform/scheduler-yield
- https://www.w3.org/TR/scheduling-apis/
- https://developer.mozilla.org/en-US/docs/Web/API/Scheduler/postTask
- https://developers.cloudflare.com/workers/runtime-apis/scheduler/
- https://web.dev/articles/optimize-inp
