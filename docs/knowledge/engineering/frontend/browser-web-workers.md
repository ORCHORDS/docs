# browser-web-workers

**Issue:** Heavy computations on the main thread cause janky UI and poor INP scores
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Parsing a large CSV or running a pathfinding algorithm locks the browser for 2 seconds.

## Pattern / Solution
```ts
// worker.ts
self.addEventListener('message', (e) => {
  const { data, id } = e.data;
  const result = heavyCompute(data);
  self.postMessage({ result, id });
});

// main.ts
const worker = new Worker(new URL('./worker.ts', import.meta.url), { type: 'module' });

function compute(data: unknown): Promise<unknown> {
  return new Promise((resolve) => {
    const id = crypto.randomUUID();
    const handler = (e: MessageEvent) => {
      if (e.data.id === id) {
        worker.removeEventListener('message', handler);
        resolve(e.data.result);
      }
    };
    worker.addEventListener('message', handler);
    worker.postMessage({ data, id });
  });
}
```

## Gotchas
- Workers cannot access the DOM or most browser APIs
- Transferable objects (ArrayBuffer) avoid the copy overhead of postMessage
- Comlink library provides an RPC abstraction over postMessage

## Related
- `html-web-vitals-inp.md`
- `browser-performance-api.md`
