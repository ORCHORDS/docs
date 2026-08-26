# React Native Reanimated Workers Animation Frame Sync

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
React Native apps using Reanimated 3 shared values for smooth animations need to synchronize animation targets (positions, opacities, progress values) with server state from Cloudflare Workers without causing jank on the UI thread or the JS thread.

## Context
Reanimated 3 moves animation worklets to a separate C++ UI thread; shared values (`useSharedValue`) update on that thread and trigger layout without touching the JS event loop. When Workers push new state (via polling or WebSocket), that data arrives on the JS thread and must be copied into shared values with `runOnUI`. The challenge is batching server-driven updates to avoid unnecessary re-renders while keeping animations smooth at 60 fps. A Workers-backed SSE or polling endpoint provides the animation targets; Reanimated `withSpring` or `withTiming` interpolates between frames client-side.

## Workers SSE Endpoint for Animation State

```typescript
// worker/src/animation-state.ts
export interface Env {
  KV: KVNamespace;
}

interface AnimationTarget {
  id: string;
  x: number;
  y: number;
  scale: number;
  opacity: number;
  updatedAt: number;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // SSE stream: GET /stream?channel=<id>
    if (url.pathname === "/stream" && request.method === "GET") {
      const channel = url.searchParams.get("channel") ?? "default";
      const encoder = new TextEncoder();

      const stream = new ReadableStream({
        async start(controller) {
          // Initial state burst
          const raw = await env.KV.get(`anim:${channel}`);
          const targets: AnimationTarget[] = raw ? JSON.parse(raw) : [];
          controller.enqueue(
            encoder.encode(`data: ${JSON.stringify({ type: "init", targets })}\n\n`)
          );

          // Poll for updates every 250 ms (SSE keep-alive)
          let lastUpdatedAt = targets.reduce((m, t) => Math.max(m, t.updatedAt), 0);
          let open = true;

          request.signal.addEventListener("abort", () => { open = false; });

          while (open) {
            await new Promise((r) => setTimeout(r, 250));
            if (!open) break;

            const updated = await env.KV.get(`anim:${channel}`);
            if (!updated) continue;

            const next: AnimationTarget[] = JSON.parse(updated);
            const maxTs = next.reduce((m, t) => Math.max(m, t.updatedAt), 0);
            if (maxTs > lastUpdatedAt) {
              lastUpdatedAt = maxTs;
              controller.enqueue(
                encoder.encode(`data: ${JSON.stringify({ type: "delta", targets: next })}\n\n`)
              );
            }
          }

          controller.close();
        },
      });

      return new Response(stream, {
        headers: {
          "Content-Type": "text/event-stream",
          "Cache-Control": "no-cache",
          "Access-Control-Allow-Origin": "*",
        },
      });
    }

    // PUT /targets — write new animation targets
    if (url.pathname === "/targets" && request.method === "PUT") {
      const channel = url.searchParams.get("channel") ?? "default";
      const body = await request.json<AnimationTarget[]>();
      const stamped = body.map((t) => ({ ...t, updatedAt: Date.now() }));
      await env.KV.put(`anim:${channel}`, JSON.stringify(stamped), {
        expirationTtl: 3600,
      });
      return new Response(JSON.stringify({ ok: true }), {
        headers: { "Content-Type": "application/json" },
      });
    }

    return new Response("Not found", { status: 404 });
  },
};
```

## React Native Reanimated Integration

```typescript
// src/hooks/useAnimatedWorkerSync.ts
import { useEffect, useRef } from "react";
import {
  SharedValue,
  runOnUI,
  withSpring,
  withTiming,
} from "react-native-reanimated";

export interface AnimationTarget {
  id: string;
  x: number;
  y: number;
  scale: number;
  opacity: number;
  updatedAt: number;
}

interface AnimatedRefs {
  x: SharedValue<number>;
  y: SharedValue<number>;
  scale: SharedValue<number>;
  opacity: SharedValue<number>;
}

const WORKERS_URL = process.env.EXPO_PUBLIC_WORKERS_URL ?? "";

/**
 * Subscribes to a Workers SSE channel and drives Reanimated shared values
 * smoothly without jank on the JS thread.
 */
export function useAnimatedWorkerSync(
  targetId: string,
  refs: AnimatedRefs,
  channel = "default"
) {
  const controllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    controllerRef.current = controller;

    async function subscribe() {
      try {
        const response = await fetch(
          `${WORKERS_URL}/stream?channel=${encodeURIComponent(channel)}`,
          { signal: controller.signal }
        );

        if (!response.body) return;
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const parts = buffer.split("\n\n");
          buffer = parts.pop() ?? "";

          for (const part of parts) {
            const line = part.replace(/^data: /, "").trim();
            if (!line) continue;

            let event: { type: string; targets: AnimationTarget[] };
            try {
              event = JSON.parse(line);
            } catch {
              continue;
            }

            const target = event.targets.find((t) => t.id === targetId);
            if (!target) continue;

            // Capture values before crossing to UI thread
            const { x, y, scale, opacity } = target;

            // runOnUI schedules on the Reanimated UI thread—no JS jank
            runOnUI(() => {
              "worklet";
              refs.x.value = withSpring(x, { damping: 15, stiffness: 120 });
              refs.y.value = withSpring(y, { damping: 15, stiffness: 120 });
              refs.scale.value = withSpring(scale, { damping: 12, stiffness: 100 });
              refs.opacity.value = withTiming(opacity, { duration: 200 });
            })();
          }
        }
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
          // Retry after 3 s on unexpected error
          setTimeout(subscribe, 3000);
        }
      }
    }

    subscribe();

    return () => {
      controller.abort();
    };
  }, [targetId, channel, refs.x, refs.y, refs.scale, refs.opacity]);
}
```

## Animated Component Example

```typescript
// src/components/WorkerSyncedCard.tsx
import React from "react";
import { StyleSheet, Text } from "react-native";
import Animated, {
  useSharedValue,
  useAnimatedStyle,
} from "react-native-reanimated";
import { useAnimatedWorkerSync } from "../hooks/useAnimatedWorkerSync";

interface Props {
  id: string;
  label: string;
  channel?: string;
}

export function WorkerSyncedCard({ id, label, channel }: Props) {
  const x = useSharedValue(0);
  const y = useSharedValue(0);
  const scale = useSharedValue(1);
  const opacity = useSharedValue(1);

  useAnimatedWorkerSync(id, { x, y, scale, opacity }, channel);

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [
      { translateX: x.value },
      { translateY: y.value },
      { scale: scale.value },
    ],
    opacity: opacity.value,
  }));

  return (
    <Animated.View style={[styles.card, animatedStyle]}>
      <Text style={styles.label}>{label}</Text>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  card: {
    width: 120,
    height: 80,
    borderRadius: 12,
    backgroundColor: "#4F46E5",
    alignItems: "center",
    justifyContent: "center",
    elevation: 4,
    shadowColor: "#000",
    shadowOpacity: 0.2,
    shadowRadius: 6,
    shadowOffset: { width: 0, height: 3 },
  },
  label: { color: "#fff", fontWeight: "700", fontSize: 14 },
});
```

## Batching Multiple Target Updates

```typescript
// src/hooks/useMultiAnimatedSync.ts
import { useEffect, useRef } from "react";
import { SharedValue, runOnUI, withSpring } from "react-native-reanimated";
import type { AnimationTarget } from "./useAnimatedWorkerSync";

type AnimMap = Map<string, { x: SharedValue<number>; y: SharedValue<number> }>;

const WORKERS_URL = process.env.EXPO_PUBLIC_WORKERS_URL ?? "";

/**
 * Syncs many animated nodes at once, batching all targets from one SSE
 * event into a single runOnUI call to minimize UI thread context switches.
 */
export function useMultiAnimatedSync(channel: string, animMap: AnimMap) {
  const animMapRef = useRef(animMap);
  animMapRef.current = animMap;

  useEffect(() => {
    const controller = new AbortController();

    async function run() {
      try {
        const res = await fetch(
          `${WORKERS_URL}/stream?channel=${encodeURIComponent(channel)}`,
          { signal: controller.signal }
        );
        if (!res.body) return;

        const reader = res.body.getReader();
        const dec = new TextDecoder();
        let buf = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += dec.decode(value, { stream: true });
          const parts = buf.split("\n\n");
          buf = parts.pop() ?? "";

          for (const part of parts) {
            const line = part.replace(/^data: /, "").trim();
            if (!line) continue;
            let ev: { type: string; targets: AnimationTarget[] };
            try { ev = JSON.parse(line); } catch { continue; }

            // Snapshot values from JS thread before passing to worklet
            const updates = ev.targets
              .map((t) => {
                const ref = animMapRef.current.get(t.id);
                return ref ? { x: t.x, y: t.y, xSv: ref.x, ySv: ref.y } : null;
              })
              .filter(Boolean) as Array<{
              x: number;
              y: number;
              xSv: SharedValue<number>;
              ySv: SharedValue<number>;
            }>;

            if (updates.length === 0) continue;

            runOnUI(() => {
              "worklet";
              for (const u of updates) {
                u.xSv.value = withSpring(u.x);
                u.ySv.value = withSpring(u.y);
              }
            })();
          }
        }
      } catch (e) {
        if ((e as Error).name !== "AbortError") setTimeout(run, 3000);
      }
    }

    run();
    return () => controller.abort();
  }, [channel]);
}
```

## Anti-patterns
- Calling `setState` or updating React state on every SSE event to drive animations—bypasses Reanimated's UI thread and causes JS thread jank
- Passing mutable objects (arrays, plain objects with methods) directly into `runOnUI`—only primitives and plain data structures cross the JS/UI thread boundary safely
- Polling the Workers endpoint faster than 100 ms—each SSE poll in a Worker counts against CPU time; use 250 ms or a true push architecture (Durable Objects WebSocket) for sub-100 ms latency
- Using `withRepeat` or frame-level callbacks (e.g., `useFrameCallback`) to fetch data from Workers—network I/O cannot run in a worklet
- Forgetting to abort the `fetch` on component unmount, leading to memory leaks from dangling SSE readers

## Gotchas
- `runOnUI` is asynchronous on the JS side but synchronous on the UI thread; do not `await` it—the returned function returns `void`
- Shared values captured inside `runOnUI` closures must exist at call time; if a component unmounts before the callback fires, the shared value may have been garbage-collected
- On Android Hermes, `TextDecoder` with `{ stream: true }` requires `react-native-fast-text-encoding` or a polyfill—test this explicitly
- SSE connections over cellular networks can be silently dropped by carrier middleboxes; implement a heartbeat check (detect >30 s without an event) and reconnect
- The Reanimated `"worklet"` directive must appear as the very first statement in a function body, including inside arrow functions passed to `runOnUI`

## Verification
1. In `wrangler dev`, PUT a target to `/targets?channel=test` and confirm the `/stream?channel=test` response emits a `delta` event within 300 ms.
2. In the React Native app (Expo dev build), mount `WorkerSyncedCard` and update the KV value via `curl`; verify the card animates smoothly without dropped frames (check with Flipper Performance tab).
3. Run `yarn jest` with a mocked `fetch` that emits two SSE events 100 ms apart; assert `runOnUI` is called once per event with the correct target values.
4. Open React DevTools profiler while SSE events arrive; confirm no React re-renders are triggered by the animation sync hook.
5. Kill the network connection and restore it; confirm the hook reconnects within 5 seconds and resumes animation sync.

## Related
- `react-native-reanimated.md`
- `capacitor-workers-sse-streaming.md`
- `react-native-flipper-workers-api-debugging.md`
- `mobile-network-resilience-cloudflare-workers.md`

## Sources
- https://docs.swmansion.com/react-native-reanimated/docs/
- https://developers.cloudflare.com/workers/runtime-apis/streams/
- https://developers.cloudflare.com/kv/
