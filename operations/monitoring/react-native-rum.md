# Real User Monitoring for React Native Apps

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

React Native apps surface performance problems that are invisible on the web:
JS thread blocking causing frozen animations, bridge-related latency in the
old architecture, Hermes JIT warmup delays on cold start, and network
variability across mobile carriers. Standard web RUM (Core Web Vitals, LCP,
CLS) does not apply. Teams need mobile-specific signals: Time to Interactive,
app cold/warm start duration, JS thread frame rate, and navigation transition
times — all broken out by device class, OS version, and network type.

## Context

React Native spans two architectures:

- **Old architecture (Bridge)** — async JS-to-native communication over a
  serialized bridge. Performance bottlenecks show as dropped frames and slow
  event processing.
- **New architecture (JSI / Fabric / TurboModules)** — synchronous JSI calls
  from JS to native. Eliminates many bridge bottlenecks but introduces
  different failure modes (JSI call latency, Fabric layout thrashing).

RUM for React Native must instrument both architectures and normalize the
signals into a unified metric set. The primary instrumentation surfaces are:

1. **React Native Performance API** (`performance.now()`, `PerformanceObserver`
   where available).
2. **Native modules** (Android `SystemClock.elapsedRealtimeNanos()`, iOS
   `CACurrentMediaTime()`).
3. **React Native's `InteractionManager`** — defers non-critical work until
   after animations complete; its callback timing is a proxy for UI thread
   availability.
4. **Flipper / Hermes profiler** — for local development; not for production
   RUM.
5. **Third-party SDKs** — Sentry, Datadog, New Relic, and Firebase
   Performance all ship React Native agents.

This article focuses on a self-hosted, vendor-neutral RUM pipeline that
captures metrics via native modules and ships them to Cloudflare Analytics
Engine or a self-hosted backend.

## Key Metrics to Collect

| Metric | Definition | Target |
|--------|-----------|--------|
| Cold Start TTI | Time from process launch to first interactive frame | < 2 s (p75) |
| Warm Start TTI | Time from app foreground to first interactive frame | < 500 ms (p75) |
| JS Thread FPS | Frames rendered per second on the JS thread | ≥ 55 fps (p75) |
| UI Thread FPS | Frames rendered per second on the native UI thread | ≥ 55 fps (p75) |
| Navigation Transition | Time from route change to rendered destination screen | < 300 ms (p75) |
| Network TTFB | Time to first byte for API calls made from the app | per-endpoint |
| JS Bundle Load | Time to parse and execute the JS bundle at cold start | < 800 ms (p75) |
| Memory Usage | Heap allocated at key checkpoints | < 200 MB (p90) |
| Crash-free Sessions | Percentage of sessions without a crash | ≥ 99.5 % |

## Instrumentation

### App Startup Timing

React Native does not expose a built-in startup duration. Use a native module
that records the process start time and compares it to when the JS root
component mounts.

```typescript
// StartupTimer.ts
import { NativeModules } from "react-native";
const { StartupTimer } = NativeModules;

export async function measureColdStart(): Promise<number> {
  const nativeLaunchTime: number = await StartupTimer.getLaunchTime();
  const jsReadyTime = Date.now();
  return jsReadyTime - nativeLaunchTime;
}
```

Android native module (`StartupTimerModule.kt`):

```kotlin
class StartupTimerModule(reactContext: ReactApplicationContext)
    : ReactContextBaseJavaModule(reactContext) {

  override fun getName() = "StartupTimer"

  @ReactMethod
  fun getLaunchTime(promise: Promise) {
    // Application.onCreate timestamp stored at launch
    promise.resolve(MyApplication.launchTimestampMs.toDouble())
  }
}
```

Record the timestamp in `Application.onCreate()`:

```kotlin
class MyApplication : Application() {
  companion object {
    var launchTimestampMs: Long = 0
  }

  override fun onCreate() {
    launchTimestampMs = System.currentTimeMillis()
    super.onCreate()
  }
}
```

### Frame Rate Monitoring

React Native exposes `PerfMonitor` in development, but for production use the
`PerformanceObserver` API (available on Hermes ≥ 0.72):

```typescript
// FrameRateMonitor.ts
export function startFrameRateMonitoring(
  onSample: (jsFps: number) => void
): () => void {
  let lastTime = performance.now();
  let frameCount = 0;
  let rafId: number;

  function tick() {
    frameCount++;
    const now = performance.now();
    if (now - lastTime >= 1000) {
      onSample(frameCount);
      frameCount = 0;
      lastTime = now;
    }
    rafId = requestAnimationFrame(tick);
  }

  rafId = requestAnimationFrame(tick);
  return () => cancelAnimationFrame(rafId);
}
```

This measures the rate at which `requestAnimationFrame` callbacks fire on the
JS thread — a direct indicator of JS thread health.

### Navigation Timing

React Navigation exposes a listener for screen transitions:

```typescript
// NavigationTiming.ts
import { NavigationContainerRef } from "@react-navigation/native";

export function instrumentNavigation(
  navigationRef: React.RefObject<NavigationContainerRef<any>>,
  onTransition: (from: string, to: string, durationMs: number) => void
): void {
  let transitionStart: number | null = null;
  let fromRoute: string | null = null;

  navigationRef.current?.addListener("state", () => {
    if (transitionStart !== null && fromRoute !== null) {
      const duration = performance.now() - transitionStart;
      const currentRoute =
        navigationRef.current?.getCurrentRoute()?.name ?? "unknown";
      onTransition(fromRoute, currentRoute, duration);
    }
    transitionStart = performance.now();
    fromRoute = navigationRef.current?.getCurrentRoute()?.name ?? null;
  });
}
```

### Network Request Timing

Patch `fetch` and `XMLHttpRequest` at app startup:

```typescript
// NetworkInstrumentation.ts
const originalFetch = global.fetch;

global.fetch = async function patchedFetch(
  input: RequestInfo,
  init?: RequestInit
): Promise<Response> {
  const url = typeof input === "string" ? input : input.url;
  const start = performance.now();

  try {
    const response = await originalFetch(input, init);
    const duration = performance.now() - start;
    recordNetworkTiming(url, response.status, duration);
    return response;
  } catch (err) {
    const duration = performance.now() - start;
    recordNetworkTiming(url, 0, duration);
    throw err;
  }
};
```

## RUM Data Pipeline

Batch metric events locally (IndexedDB via `@react-native-async-storage/async-storage`)
and flush to the backend every 30 seconds or on app background:

```typescript
// RumBatcher.ts
import AsyncStorage from "@react-native-async-storage/async-storage";
import { AppState } from "react-native";

const QUEUE_KEY = "rum_queue";
const FLUSH_INTERVAL_MS = 30_000;

export class RumBatcher {
  private timer: ReturnType<typeof setInterval>;

  constructor(private readonly endpoint: string) {
    this.timer = setInterval(() => this.flush(), FLUSH_INTERVAL_MS);
    AppState.addEventListener("change", (state) => {
      if (state === "background") this.flush();
    });
  }

  async push(event: Record<string, unknown>): Promise<void> {
    const raw = await AsyncStorage.getItem(QUEUE_KEY);
    const queue: unknown[] = raw ? JSON.parse(raw) : [];
    queue.push({ ...event, ts: Date.now() });
    await AsyncStorage.setItem(QUEUE_KEY, JSON.stringify(queue));
  }

  async flush(): Promise<void> {
    const raw = await AsyncStorage.getItem(QUEUE_KEY);
    if (!raw) return;
    const queue = JSON.parse(raw);
    if (queue.length === 0) return;
    await AsyncStorage.removeItem(QUEUE_KEY);

    try {
      await fetch(this.endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ events: queue }),
      });
    } catch {
      // Re-enqueue on failure
      const existing = await AsyncStorage.getItem(QUEUE_KEY);
      const current = existing ? JSON.parse(existing) : [];
      await AsyncStorage.setItem(
        QUEUE_KEY,
        JSON.stringify([...queue, ...current])
      );
    }
  }
}
```

## Segmentation Dimensions

Always capture these dimensions alongside every metric:

```typescript
import { Platform } from "react-native";
import DeviceInfo from "react-native-device-info";

async function getDeviceContext() {
  return {
    platform: Platform.OS,                          // "ios" | "android"
    osVersion: Platform.Version,                    // "17.2" | 34
    deviceModel: await DeviceInfo.getModel(),       // "iPhone 15 Pro"
    deviceBrand: await DeviceInfo.getBrand(),       // "Apple"
    isLowEnd: await DeviceInfo.isLowRamDevice(),   // boolean
    connectionType: await getNetworkType(),         // "wifi" | "4g" | "5g"
    appVersion: DeviceInfo.getVersion(),            // "2.4.1"
    buildNumber: DeviceInfo.getBuildNumber(),       // "241"
    hermes: (global as any).HermesInternal != null, // boolean
  };
}
```

## Anti-patterns

**Measuring only on developer devices.** High-end devices hide startup and
frame-rate problems that appear on mid-range Android hardware. Always segment
by device class and alert on low-end device p75, not overall p50.

**Sampling 100 % of events.** On a large user base, sending every frame-rate
sample generates significant bandwidth and backend cost. Sample at 10–20 %
for high-frequency metrics (FPS) and 100 % for infrequent high-value metrics
(cold start, crash).

**Using wall-clock Date.now() for sub-second measurements.** `Date.now()` has
millisecond resolution and can skew with clock adjustments. Use
`performance.now()` (Hermes) or native `CACurrentMediaTime` / `elapsedRealtimeNanos`
for durations.

**Ignoring the JS/UI thread distinction.** A smooth UI thread with a frozen
JS thread shows as 60 fps in some monitors but causes dropped gesture
responsiveness. Monitor both threads independently.

**Flushing metrics synchronously in `componentWillUnmount`.** This blocks the
UI thread. Use the AppState background listener and async flush.

## Gotchas

- **Hermes vs JavaScriptCore.** `performance.now()` is available in Hermes ≥
  0.71 but not in older JSC. Feature-detect before using it.
- **Android emulator vs physical device.** Emulator timings are meaningless
  for startup and FPS RUM. Gate metric collection on physical device checks
  using `DeviceInfo.isEmulator()`.
- **Background fetch restrictions.** iOS aggressively throttles background
  network activity. Always attempt to flush before the app enters the
  background state, not after.
- **AsyncStorage size limits.** The local queue can grow large if the network
  is unavailable for extended periods. Cap the queue at 500 events and drop
  oldest on overflow.
- **New Architecture migration.** JSI / Fabric changes native timing
  behavior. Re-baseline all startup and FPS thresholds after migrating.

## Verification

1. Run the app on three device classes: flagship (e.g., iPhone 15), mid-range
   (e.g., Pixel 6a), and low-end (e.g., a 3 GB RAM Android device). Confirm
   metric collection fires on all three.
2. Introduce an artificial 200 ms delay in a navigation handler. Confirm the
   navigation transition metric captures the degradation within one standard
   deviation.
3. Kill the network during a test session, perform several navigation events,
   then restore the network. Confirm all queued events flush on reconnection.
4. Verify that device context dimensions appear correctly segmented in the
   analytics dashboard — no null `deviceModel` or `connectionType` values.
5. Confirm that emulator sessions are excluded from production dashboards.

## Related

- `real-user-monitoring-rum.md`
- `real-user-monitoring-rum-mobile-network.md`
- `rum-mobile-desktop-cwv-disparity.md`
- `mobile-crash-monitoring.md`
- `analytics-engine-mobile-desktop-segmentation.md`

## Sources

- React Native Performance documentation (Meta, 2024)
- Hermes JavaScript Engine documentation
- React Navigation performance guide
- Sentry React Native SDK documentation
- Datadog Mobile RUM documentation
- "Measuring App Startup in React Native" — Callstack Blog, 2024
