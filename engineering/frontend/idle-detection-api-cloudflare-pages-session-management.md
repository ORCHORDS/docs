# Idle Detection API — Cloudflare Pages Session Management

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your SPA needs to auto-lock the UI after a period of user inactivity — for security
(financial dashboards, admin panels) or to extend sessions only while active. The native
`IdleDetector` API detects both user idle state and screen lock, and a Cloudflare Worker
can extend or invalidate KV-backed sessions based on activity signals from the client.

---

## Context

`IdleDetector` fires events when the user has been idle for a configured threshold (minimum
60 seconds) and when the screen locks. It requires the `idle-detection` permission, which
must be requested via the Permissions API. On Cloudflare Pages, the SPA handles the
UI-level lockout; a Worker extends the session TTL in KV on `active` transitions and
expires it early on `locked` transitions if security policy requires it. The fallback for
unsupported browsers is a `visibilitychange` + `pointermove`/`keydown` debounce.

---

## Feature Detection + Permission

```typescript
// src/lib/idleDetection.ts
export function isIdleDetectionSupported(): boolean {
  return typeof window !== 'undefined' && 'IdleDetector' in window;
}

export async function requestIdlePermission(): Promise<PermissionState> {
  if (!isIdleDetectionSupported()) return 'denied';
  try {
    const perm = await navigator.permissions.query({
      name: 'idle-detection' as PermissionName,
    });
    if (perm.state === 'granted') return 'granted';
    if (perm.state === 'denied') return 'denied';
    // 'prompt' — must be requested from a user gesture
    return 'prompt';
  } catch {
    return 'denied';
  }
}
```

---

## IdleDetector Wrapper

```typescript
// src/lib/IdleWatcher.ts
import { isIdleDetectionSupported } from './idleDetection';

export type IdleState = 'active' | 'idle';
export type ScreenState = 'unlocked' | 'locked';

export interface IdleEvent {
  user: IdleState;
  screen: ScreenState;
}

export class IdleWatcher {
  private detector: IdleDetector | null = null;
  private abortCtrl: AbortController | null = null;

  async start(
    thresholdMs: number,
    onChange: (event: IdleEvent) => void
  ): Promise<boolean> {
    if (!isIdleDetectionSupported()) return false;

    try {
      // Requesting start() is the permission trigger — must be in a user gesture
      this.abortCtrl = new AbortController();
      this.detector = new IdleDetector();

      this.detector.addEventListener('change', () => {
        onChange({
          user: this.detector!.userState as IdleState,
          screen: this.detector!.screenState as ScreenState,
        });
      });

      await this.detector.start({
        threshold: thresholdMs,
        signal: this.abortCtrl.signal,
      });

      return true;
    } catch (err) {
      if ((err as DOMException).name === 'NotAllowedError') {
        return false; // permission denied
      }
      throw err;
    }
  }

  get currentState(): IdleEvent | null {
    if (!this.detector) return null;
    return {
      user: this.detector.userState as IdleState,
      screen: this.detector.screenState as ScreenState,
    };
  }

  stop(): void {
    this.abortCtrl?.abort();
    this.detector = null;
  }
}
```

---

## Fallback for Unsupported Browsers

```typescript
// src/lib/idleFallback.ts
type Callback = (isIdle: boolean) => void;

export function watchIdleFallback(
  thresholdMs: number,
  onChange: Callback
): () => void {
  let idle = false;
  let timer: ReturnType<typeof setTimeout>;

  const reset = () => {
    if (idle) { idle = false; onChange(false); }
    clearTimeout(timer);
    timer = setTimeout(() => { idle = true; onChange(true); }, thresholdMs);
  };

  const events: (keyof DocumentEventMap)[] = [
    'mousemove', 'keydown', 'pointerdown', 'touchstart', 'wheel', 'scroll',
  ];
  events.forEach((e) => document.addEventListener(e, reset, { passive: true }));

  const visChange = () => {
    if (document.hidden) { idle = true; onChange(true); }
    else reset();
  };
  document.addEventListener('visibilitychange', visChange);

  reset(); // start timer

  return () => {
    clearTimeout(timer);
    events.forEach((e) => document.removeEventListener(e, reset));
    document.removeEventListener('visibilitychange', visChange);
  };
}
```

---

## React Hook

```typescript
// src/hooks/useIdleDetection.ts
import { useEffect, useRef, useState, useCallback } from 'react';
import { IdleWatcher, IdleEvent } from '../lib/IdleWatcher';
import { watchIdleFallback } from '../lib/idleFallback';
import { isIdleDetectionSupported } from '../lib/idleDetection';

const IDLE_THRESHOLD_MS = 5 * 60 * 1000; // 5 minutes

export function useIdleDetection() {
  const [idleState, setIdleState] = useState<'active' | 'idle'>('active');
  const watcherRef = useRef(new IdleWatcher());

  const startWatching = useCallback(async () => {
    const watcher = watcherRef.current;

    const handleChange = (event: IdleEvent) => {
      setIdleState(event.user === 'idle' || event.screen === 'locked' ? 'idle' : 'active');
      // Notify Worker to extend or trim session
      fetch('/api/session/activity', {
        method: 'POST',
        keepalive: true,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ userState: event.user, screenState: event.screen }),
      }).catch(() => {/* non-critical */});
    };

    const supported = await watcher.start(IDLE_THRESHOLD_MS, handleChange);

    if (!supported) {
      // Fallback path
      const cleanup = watchIdleFallback(IDLE_THRESHOLD_MS, (isIdle) => {
        setIdleState(isIdle ? 'idle' : 'active');
      });
      return cleanup;
    }
    return () => watcher.stop();
  }, []);

  useEffect(() => {
    let cleanup: (() => void) | undefined;
    startWatching().then((fn) => { cleanup = fn; });
    return () => cleanup?.();
  }, [startWatching]);

  return idleState;
}
```

---

## Cloudflare Worker — Session Activity Endpoint

```typescript
// workers/session/activity.ts  (POST /api/session/activity)
import { Hono } from 'hono';

type Env = { KV: KVNamespace };
const app = new Hono<{ Bindings: Env }>();

const ACTIVE_TTL = 60 * 60 * 8;       // 8 hours while active
const IDLE_EXPIRE_DELTA_MS = 60_000;   // expire 60s after idle signal

app.post('/api/session/activity', async (c) => {
  const cookie = c.req.header('cookie') ?? '';
  const sid = cookie.match(/(?:^|;\s*)sid=([^;]+)/)?.[1];
  if (!sid) return c.json({ ok: false }, 401);

  const key = `session:${sid}`;
  const raw = await c.env.KV.get(key);
  if (!raw) return c.json({ ok: false }, 401);

  const { userState, screenState } = await c.req.json<{
    userState: 'active' | 'idle';
    screenState: 'unlocked' | 'locked';
  }>();

  if (userState === 'active' && screenState === 'unlocked') {
    // Refresh TTL while user is active
    await c.env.KV.put(key, raw, { expirationTtl: ACTIVE_TTL });
    return c.json({ ok: true, action: 'refreshed' });
  }

  if (screenState === 'locked') {
    // Screen lock — expire session quickly for security-sensitive apps
    await c.env.KV.put(key, raw, { expirationTtl: 60 });
    return c.json({ ok: true, action: 'locked' });
  }

  // userState === 'idle': let natural TTL expire, do nothing
  return c.json({ ok: true, action: 'idle_passthrough' });
});

export default app;
```

---

## UI Lock Screen Component

```tsx
// src/components/IdleLock.tsx
import { useIdleDetection } from '../hooks/useIdleDetection';
import { useState } from 'react';

export function IdleLock({ children }: { children: React.ReactNode }) {
  const idleState = useIdleDetection();
  const [unlocked, setUnlocked] = useState(false);

  if (idleState === 'idle' && !unlocked) {
    return (
      <div role="dialog" aria-modal aria-label="Session locked">
        <p>Your session has been locked due to inactivity.</p>
        <button onClick={() => setUnlocked(true)}>Unlock</button>
      </div>
    );
  }

  return <>{children}</>;
}
```

---

## Anti-patterns

- **Calling `IdleDetector.start()` outside a user gesture** — Chrome requires a user activation; wrap in a button `onClick`.
- **Polling `visibilitychange` as the only idle signal** — tab switching is not inactivity; use the debounced fallback with pointer/keyboard events.
- **Setting threshold below 60 000 ms** — the spec requires a minimum of 60 seconds; lower values throw `RangeError`.
- **Expiring sessions aggressively on every idle signal** — use a grace period (60 s) before truly deleting the session, or users are logged out during short pauses.
- **Not calling `AbortController.abort()` on cleanup** — `IdleDetector` keeps running after component unmount and fires change events into stale closures.

---

## Gotchas

- `IdleDetector` is available in Chrome 94+ and Edge 94+; it is NOT available in Firefox or Safari (as of 2026). Always ship the fallback.
- The `idle-detection` permission is not surfaced in the Permissions UI by default — the user will see a generic prompt; explain why in your UI before calling `.start()`.
- `screenState === 'locked'` only fires if the OS-level screen lock is activated, not if the user simply switches apps on mobile.
- `keepalive: true` on the activity `fetch` ensures the signal reaches the Worker even when the user closes the tab immediately after going idle.
- On Cloudflare Pages with `wrangler pages dev`, the KV binding must be configured in `wrangler.toml` as a `[[kv_namespaces]]` entry with a local simulation namespace ID.

---

## Verification

```bash
# Check activity endpoint with mock session
SESSION_ID=$(curl -s http://localhost:8788/api/auth/test-session | jq -r '.sid')

# Simulate active heartbeat
curl -X POST http://localhost:8788/api/session/activity \
  -H "Cookie: sid=${SESSION_ID}" \
  -H 'Content-Type: application/json' \
  -d '{"userState":"active","screenState":"unlocked"}'
# expect: {"ok":true,"action":"refreshed"}

# Simulate screen lock
curl -X POST http://localhost:8788/api/session/activity \
  -H "Cookie: sid=${SESSION_ID}" \
  -H 'Content-Type: application/json' \
  -d '{"userState":"idle","screenState":"locked"}'
# expect: {"ok":true,"action":"locked"}

# Confirm KV TTL was shortened
wrangler kv key get --binding=KV "session:${SESSION_ID}" --local
```

---

## Related

- `cloudflare-pages-functions-session-validation-middleware.md`
- `credential-management-api-cloudflare-workers.md`
- `browser-permissions-api.md`
- `screen-wake-lock-visibility-lifecycle.md`
- `user-activation-transient-sticky-gating.md`

---

## Sources

- https://developer.mozilla.org/en-US/docs/Web/API/IdleDetector
- https://wicg.github.io/idle-detection/
- https://developer.chrome.com/docs/capabilities/idle-detection
- https://developers.cloudflare.com/kv/
- https://developers.cloudflare.com/pages/
