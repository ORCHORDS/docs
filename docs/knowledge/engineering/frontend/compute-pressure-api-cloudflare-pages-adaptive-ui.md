# Compute Pressure API — Adaptive UI on Cloudflare Pages

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A real-time dashboard, 3D configurator, or WebGL visualisation hosted on Cloudflare
Pages causes the user's laptop fan to spin up, the browser to drop frames, and the
battery to drain. The app has no signal that it is overwhelming the device. Reducing
frame rate or particle count on a timer is a blind guess; cutting quality on every
low-end device is too conservative. The operating system's thermal and CPU state is
the authoritative signal and the page has historically had no access to it.

## Context

`PressureObserver` exposes CPU pressure as four discrete states: `"nominal"`,
`"fair"`, `"serious"`, `"critical"`. The browser aggregates OS-level thermal and
scheduler load signals and reports them at a capped rate (~1 Hz). Pages react by
throttling animations, reducing WebGL complexity, offloading to Shared Workers, or
suspending non-essential polling.

The API is a pure progressive enhancement — when unavailable, fall back to a
highest-quality default. No server component is required; Cloudflare Workers are
useful only for persisting quality-change telemetry.

Support: Chrome 125+, Edge 125+. Not in Firefox or Safari as of 2025.
Feature-detect on `'PressureObserver' in window`.

---

## 1. TypeScript Declarations

```typescript
type PressureState  = 'nominal' | 'fair' | 'serious' | 'critical';
type PressureSource = 'cpu';

interface PressureRecord {
  readonly state:  PressureState;
  readonly source: PressureSource;
  readonly time:   DOMHighResTimeStamp;
  toJSON(): object;
}

interface PressureObserverOptions {
  sampleInterval?: number; // ms; browser may clamp upward
}

declare global {
  class PressureObserver {
    constructor(
      callback: (records: PressureRecord[], observer: PressureObserver) => void,
      options?: PressureObserverOptions
    );
    observe(source: PressureSource): Promise<void>;
    unobserve(source: PressureSource): void;
    disconnect(): void;
    static readonly supportedSources: ReadonlyArray<PressureSource>;
  }
}

function supportsPressureObserver(): boolean {
  return typeof window !== 'undefined' && 'PressureObserver' in window;
}
```

---

## 2. Core Observer Setup

```typescript
type PressureChangeHandler = (state: PressureState) => void;

function createPressureObserver(
  onStateChange: PressureChangeHandler
): (() => void) | null {
  if (!supportsPressureObserver()) return null;
  if (!PressureObserver.supportedSources.includes('cpu')) return null;

  let lastState: PressureState | null = null;

  const observer = new PressureObserver((records) => {
    // The callback may receive multiple records; always use the latest
    const latest = records.at(-1);
    if (!latest || latest.state === lastState) return;
    lastState = latest.state;
    onStateChange(latest.state);
  }, { sampleInterval: 1000 });

  observer.observe('cpu').catch((err: unknown) => {
    // Fails when blocked by Permissions Policy or unsupported environment
    console.warn('PressureObserver failed to start:', err);
  });

  return () => observer.disconnect();
}
```

The returned cleanup function disconnects the observer. Call it on component unmount
or page teardown to prevent the callback from firing on a stale closure.

---

## 3. Quality Levels and Render Adaptation

```typescript
type RenderQuality = 'high' | 'medium' | 'low' | 'minimal';

const QUALITY_MAP: Record<PressureState, RenderQuality> = {
  nominal:  'high',
  fair:     'medium',
  serious:  'low',
  critical: 'minimal',
};

interface RenderConfig {
  particleCount: number;
  shadowsEnabled: boolean;
  antiAlias: boolean;
  targetFps: number;
}

const RENDER_CONFIGS: Record<RenderQuality, RenderConfig> = {
  high:    { particleCount: 100_000, shadowsEnabled: true,  antiAlias: true,  targetFps: 60 },
  medium:  { particleCount:  30_000, shadowsEnabled: true,  antiAlias: false, targetFps: 60 },
  low:     { particleCount:   5_000, shadowsEnabled: false, antiAlias: false, targetFps: 30 },
  minimal: { particleCount:     500, shadowsEnabled: false, antiAlias: false, targetFps: 15 },
};

function pressureToConfig(state: PressureState): RenderConfig {
  return RENDER_CONFIGS[QUALITY_MAP[state]];
}
```

---

## 4. React Hook with Hysteresis

Thermal pressure can oscillate between states. Debounce upgrades to avoid rapidly
increasing load the moment pressure dips.

```typescript
import { useCallback, useEffect, useRef, useState } from 'react';

function usePressureAdaptation(
  defaultQuality: RenderQuality = 'high',
  upgradeDelayMs = 5000,
  downgradeDelayMs = 500
): RenderQuality {
  const [quality, setQuality] = useState<RenderQuality>(defaultQuality);
  const cleanupRef = useRef<(() => void) | null>(null);
  const pendingRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const applyChange = useCallback(
    (next: RenderQuality, delayMs: number) => {
      if (pendingRef.current) clearTimeout(pendingRef.current);
      pendingRef.current = setTimeout(() => setQuality(next), delayMs);
    },
    []
  );

  useEffect(() => {
    const RANKS: RenderQuality[] = ['high', 'medium', 'low', 'minimal'];
    let current: RenderQuality = defaultQuality;

    cleanupRef.current = createPressureObserver((state) => {
      const next = QUALITY_MAP[state];
      if (next === current) return;
      const isDowngrade = RANKS.indexOf(next) > RANKS.indexOf(current);
      current = next;
      applyChange(next, isDowngrade ? downgradeDelayMs : upgradeDelayMs);
    });

    return () => {
      cleanupRef.current?.();
      if (pendingRef.current) clearTimeout(pendingRef.current);
    };
  }, [defaultQuality, upgradeDelayMs, downgradeDelayMs, applyChange]);

  return quality;
}

// Usage:
function ParticleScene() {
  const quality = usePressureAdaptation();
  const config  = RENDER_CONFIGS[quality];
  // Pass config.particleCount, config.targetFps etc. to the WebGL renderer
}
```

---

## 5. Forwarding Telemetry to Cloudflare Workers

```typescript
// Client side: batch pressure events, flush on beacon
interface PressureEvent {
  state:     PressureState;
  quality:   RenderQuality;
  sessionId: string;
  ts:        number;
}

class PressureTelemetry {
  private queue:   PressureEvent[]               = [];
  private timer:   ReturnType<typeof setInterval>;

  constructor(private sessionId: string, private endpoint: string) {
    this.timer = setInterval(() => this.flush(), 30_000);
    window.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'hidden') this.flush();
    });
  }

  record(state: PressureState, quality: RenderQuality): void {
    this.queue.push({ state, quality, sessionId: this.sessionId, ts: Date.now() });
    if (this.queue.length >= 20) this.flush();
  }

  private flush(): void {
    if (this.queue.length === 0) return;
    navigator.sendBeacon(this.endpoint, JSON.stringify(this.queue.splice(0)));
  }

  destroy(): void {
    clearInterval(this.timer);
    this.flush();
  }
}

// workers/pressure-telemetry.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response(null, { status: 405 });
    const events = await request.json<PressureEvent[]>();
    const batch  = events.slice(0, 50).map(e =>
      env.DB.prepare(
        'INSERT INTO pressure_events (session_id, state, quality, ts) VALUES (?,?,?,?)'
      ).bind(e.sessionId.slice(0, 64), e.state, e.quality, e.ts)
    );
    await env.DB.batch(batch);
    return new Response(null, { status: 204 });
  },
} satisfies ExportedHandler<Env>;
```

---

## Anti-patterns

- Reacting to every record in the callback without deduplicating by state. The
  callback may fire multiple times during rapid transitions; always compare against
  the last applied state before making changes.
- Restoring high quality immediately when the state returns to `"nominal"`. Thermal
  systems recover slowly; wait several seconds before increasing GPU or CPU load.
- Degrading accessibility features. Quality reduction must never remove captions,
  mute audio, or eliminate keyboard interactions without explicit user consent.
- Setting `sampleInterval` below 1000 ms in production. The browser will clamp it
  upward, and lower values increase CPU overhead for the observer itself.
- Treating `"nominal"` as definitive proof the device is not under load. Some
  sandboxed environments (certain VMs, CI machines) always report `"nominal"`.

## Gotchas

- `observe('cpu')` returns a Promise that rejects if the source is unsupported or
  blocked by a Permissions Policy. Always `.catch()` it; an unhandled rejection
  from `observe` may appear as an uncaught error in analytics.
- The Permissions Policy header `compute-pressure` controls whether embedded iframes
  can observe pressure. Set it in the Cloudflare Pages `_headers` file:
  `Permissions-Policy: compute-pressure=(self)`.
- `PressureObserver` is not available in Service Workers, Shared Workers, or
  Worklets — client window context only.
- The API was originally named "Compute Pressure API" and renamed to "Pressure
  Observer API" during standardization. Older Chrome releases used
  `ComputePressureObserver`; verify the constructor name in your target range.

## Verification

```typescript
// Manually verify state transitions under artificial load:
const obs = new PressureObserver(rs => console.log('Pressure:', rs.at(-1)?.state));
await obs.observe('cpu');

// Then in a Worker (separate thread to not block the page):
const w = new Worker(URL.createObjectURL(new Blob([
  'let i=0; while(true){i++;}'   // tight loop
], { type: 'application/javascript' })));
// Expect state to climb toward "serious" or "critical" within seconds
// Open Chrome DevTools → Performance → CPU throttle to accelerate
```

## Related

- `scheduler-api-cooperative-multitasking-workers-performance.md`
- `web-animations-api-workers-performance.md`
- `browser-web-workers.md`
- `browser-performance-api.md`

## Sources

- W3C Compute Pressure Level 1 — https://www.w3.org/TR/compute-pressure/
- MDN PressureObserver — https://developer.mozilla.org/en-US/docs/Web/API/PressureObserver
- Chrome Platform Status — https://chromestatus.com/feature/5597608644968448
- WICG Compute Pressure explainer — https://github.com/WICG/compute-pressure/blob/main/README.md
