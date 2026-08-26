# Workers CPU Flame Graph Profiling

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A Cloudflare Workers endpoint is hitting the CPU time limit (50 ms on the free plan,
30 s on paid) or showing unexpectedly high p99 latency. You need to identify which
function calls consume the most CPU — not wall-clock time — and visualise the call
stack as a flame graph rather than reading raw sampling data.

## Context

Workers runs on V8 isolates. CPU profiling uses the V8 inspector protocol, which
Wrangler exposes through `wrangler dev --inspector-port 9229`. You attach Chrome
DevTools (or `0x` / `speedscope`) to capture a CPU profile, then convert it to a
flame graph. For CI-reproducible profiling, `miniflare` can emit V8 coverage and
sampling data programmatically via its `--inspector-port` flag.

Tools: Wrangler ≥ 3.60, Chrome 125+, `0x` CLI (optional), `speedscope` (optional).

---

## 1. Start Wrangler dev with inspector port

```bash
# Terminal 1 — run the worker with the V8 inspector enabled
wrangler dev --inspector-port 9229 --local
```

The inspector listens at `ws://127.0.0.1:9229`. Open Chrome and navigate to:
`chrome://inspect/#devices` → click **"inspect"** next to the Workers target.

## 2. Capture a CPU profile via Chrome DevTools

```
1. In the DevTools Performance panel click "Record" (or Ctrl+E).
2. Send requests to http://localhost:8787 to exercise the hot path.
3. Click "Stop" — DevTools shows a flame chart and a bottom-up table.
4. Export the profile: ⋮ menu → "Save profile…" → profile.cpuprofile
```

## 3. Programmatic profile capture via fetch + inspector

```typescript
// scripts/capture-profile.ts
// Requires: bun or Node 22+, wrangler dev running on port 8787 + inspector 9229

const INSPECTOR_URL = "ws://127.0.0.1:9229";
const WORKER_URL = "http://localhost:8787";
const DURATION_MS = 3000;

// Open WebSocket to the V8 inspector
const ws = new WebSocket(INSPECTOR_URL);
let cmdId = 1;

function send(method: string, params: Record<string, unknown> = {}) {
  ws.send(JSON.stringify({ id: cmdId++, method, params }));
}

ws.onopen = async () => {
  // Enable profiler
  send("Profiler.enable");
  send("Profiler.setSamplingInterval", { interval: 100 }); // microseconds
  send("Profiler.start");

  // Warm-up + measurement requests
  await Promise.all(
    Array.from({ length: 50 }, () => fetch(WORKER_URL + "/your-hot-endpoint"))
  );

  // Wait for the measurement window
  await new Promise<void>((r) => setTimeout(r, DURATION_MS));

  send("Profiler.stop");
};

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data as string) as {
    id?: number;
    result?: { profile?: unknown };
  };
  if (msg.result?.profile) {
    const Bun = (globalThis as { Bun?: { write(p: string, d: unknown): void } }).Bun;
    if (Bun) {
      Bun.write("profile.cpuprofile", JSON.stringify(msg.result.profile));
    } else {
      // Node fallback
      import("node:fs").then(({ writeFileSync }) =>
        writeFileSync("profile.cpuprofile", JSON.stringify(msg.result!.profile))
      );
    }
    console.log("Profile saved to profile.cpuprofile");
    ws.close();
  }
};
```

## 4. Convert to flame graph with `0x`

```bash
# Install 0x globally
npm i -g 0x

# 0x can consume a .cpuprofile directly
0x --input profile.cpuprofile

# Opens a flame graph in the browser at http://localhost:8080
```

## 5. Analyse the profile programmatically

```typescript
// scripts/analyse-profile.ts
import { readFileSync } from "node:fs";

interface CpuNode {
  id: number;
  callFrame: {
    functionName: string;
    url: string;
    lineNumber: number;
  };
  hitCount: number;
  children?: number[];
}

interface CpuProfile {
  nodes: CpuNode[];
  startTime: number;
  endTime: number;
  samples: number[];
  timeDeltas: number[];
}

const profile: CpuProfile = JSON.parse(readFileSync("profile.cpuprofile", "utf8"));

// Build a hit-count map per function
const hitMap = new Map<string, number>();
for (const node of profile.nodes) {
  const fn = node.callFrame.functionName || "(anonymous)";
  const file = node.callFrame.url.split("/").at(-1) ?? "?";
  const key = `${fn} @ ${file}:${node.callFrame.lineNumber}`;
  hitMap.set(key, (hitMap.get(key) ?? 0) + node.hitCount);
}

// Print top 10 hottest functions
const sorted = [...hitMap.entries()].sort((a, b) => b[1] - a[1]).slice(0, 10);
const totalSamples = profile.samples.length;

console.log("Top 10 CPU hotspots:");
for (const [fn, hits] of sorted) {
  const pct = ((hits / totalSamples) * 100).toFixed(1);
  console.log(`  ${pct.padStart(5)}%  ${fn}`);
}
```

## 6. Speedscope integration (shareable flame graphs)

```bash
# Install speedscope
npm i -g speedscope

# Open local profile
speedscope profile.cpuprofile

# Or upload to https://speedscope.app (no server-side storage — client-side only)
```

## Anti-patterns

- Profiling in production — always profile against `wrangler dev --local`. Production
  V8 isolates do not expose the inspector protocol.
- Using wall-clock timers (`Date.now()`, `performance.now()`) to identify CPU hotspots
  — these measure total elapsed time including I/O waits, not CPU usage.
- Collecting profiles during cold start only — most Workers run in warm isolates. Send
  ≥ 20 warm-up requests before starting the profiler.

## Gotchas

- `--inspector-port` only works with `wrangler dev --local`. Remote dev mode
  (`--remote`) proxies to Cloudflare infrastructure where the inspector is unavailable.
- The V8 sampling profiler introduces ~2–5% overhead; results are statistical, not
  exact. Short profiles (< 1 s) have high variance — prefer 3–10 s capture windows.
- `profile.cpuprofile` files can exceed 50 MB for long captures. The `0x` CLI may OOM
  on large profiles; use `speedscope` which streams the data browser-side.
- Workers that use `wasm` bindings will show WASM frames in the profile with opaque
  function names unless the WASM module was compiled with DWARF debug info.

## Verification

```bash
# Confirm inspector is reachable
curl http://127.0.0.1:9229/json/list

# Capture a quick 2-second profile
bun scripts/capture-profile.ts
ls -lh profile.cpuprofile

# View top hotspots
bun scripts/analyse-profile.ts
```

## Related

- `node-cpu-flame-graph-profiling.md`
- `wrangler-dev-local-d1-r2-kv.md`
- `opentelemetry-workers-tracing-setup.md`

## Sources

- https://developers.cloudflare.com/workers/observability/dev-tools/inspector/
- https://chromedevtools.github.io/devtools-protocol/tot/Profiler/
- https://github.com/nicolo-ribaudo/0x
- https://speedscope.app
