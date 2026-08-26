# Beacon API — Non-Blocking Analytics to Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

example project needs to record engagement events (post views, anonymous vote casts, scroll depth)
without slowing the page or losing data when the user navigates away. `fetch()` requests
started in `beforeunload` are cancelled by the browser. `XMLHttpRequest` with `async:false`
blocks the main thread. The Beacon API solves both problems: it enqueues a fire-and-forget
HTTP POST that the browser guarantees to complete even after the page is discarded.

## Context

`navigator.sendBeacon(url, data)` sends a POST that the UA completes out-of-band. The browser
returns `true` if the payload was queued (not delivered). Payloads must be `Blob`, `ArrayBuffer`,
`FormData`, or `URLSearchParams`; JSON requires wrapping in a `Blob` with the correct MIME type.
Cloudflare Workers receive these as ordinary POST requests. Pair with Workers Logpush or D1 for
persistent storage. The `visibilitychange` event (hidden state) is more reliable than
`beforeunload` on mobile where the page is killed without firing `beforeunload`.

## Cloudflare Worker: Beacon Ingest Endpoint

```typescript
// src/analytics-worker.ts
interface BeaconPayload {
  event: string;
  postId?: string;
  sessionToken: string; // anonymous ephemeral token
  ts: number;
  meta?: Record<string, string | number>;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    if (request.method !== "POST") {
      return new Response(null, { status: 405 });
    }

    // Beacon sends Content-Type: text/plain for JSON blobs
    const raw = await request.text();
    let payload: BeaconPayload;
    try {
      payload = JSON.parse(raw);
    } catch {
      return new Response(null, { status: 400 });
    }

    // Validate anonymous session token (HMAC-signed, no PII)
    if (!isValidSessionToken(payload.sessionToken, env.BEACON_SECRET)) {
      return new Response(null, { status: 403 });
    }

    // Persist asynchronously — don't block the 204 response
    ctx.waitUntil(persistEvent(payload, env));

    // Beacon requires a 2xx; 204 is conventional
    return new Response(null, { status: 204, headers: { "Access-Control-Allow-Origin": "https://example.com" } });
  },
};

async function persistEvent(payload: BeaconPayload, env: Env): Promise<void> {
  await env.DB.prepare(
    "INSERT INTO events (event, post_id, session_token, ts, meta) VALUES (?, ?, ?, ?, ?)"
  )
    .bind(
      payload.event,
      payload.postId ?? null,
      payload.sessionToken,
      payload.ts,
      payload.meta ? JSON.stringify(payload.meta) : null
    )
    .run();
}

function isValidSessionToken(token: string, secret: string): boolean {
  // Real implementation: verify HMAC-SHA256 of the anonymous session ID
  return typeof token === "string" && token.length === 64;
}

interface Env {
  DB: D1Database;
  BEACON_SECRET: string;
}
```

## Client: Beacon Sender Utility

```typescript
// src/lib/beacon.ts
const BEACON_URL = "https://analytics.example.com/beacon";

interface BeaconEvent {
  event: string;
  postId?: string;
  meta?: Record<string, string | number>;
}

function getSessionToken(): string {
  let token = sessionStorage.getItem("wam_beacon_token");
  if (!token) {
    token = Array.from(crypto.getRandomValues(new Uint8Array(32)))
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");
    sessionStorage.setItem("wam_beacon_token", token);
  }
  return token;
}

export function sendBeacon(event: BeaconEvent): boolean {
  const payload = JSON.stringify({
    ...event,
    sessionToken: getSessionToken(),
    ts: Date.now(),
  });
  // Wrap as Blob so Content-Type is set correctly
  const blob = new Blob([payload], { type: "application/json" });
  return navigator.sendBeacon(BEACON_URL, blob);
}
```

## Page-Lifecycle Integration

```typescript
// src/lib/pageAnalytics.ts
import { sendBeacon } from "./beacon";

// visibilitychange fires reliably on mobile (page discard) and desktop (tab switch)
export function initPageAnalytics(postId: string): () => void {
  let startTime = Date.now();
  let maxScrollDepth = 0;

  const trackScroll = () => {
    const depth = Math.round(
      ((window.scrollY + window.innerHeight) / document.documentElement.scrollHeight) * 100
    );
    if (depth > maxScrollDepth) maxScrollDepth = depth;
  };

  const handleVisibilityChange = () => {
    if (document.visibilityState === "hidden") {
      sendBeacon({
        event: "page_hidden",
        postId,
        meta: {
          dwell_ms: Date.now() - startTime,
          scroll_depth: maxScrollDepth,
        },
      });
    } else {
      // Page became visible again — reset dwell timer
      startTime = Date.now();
    }
  };

  window.addEventListener("scroll", trackScroll, { passive: true });
  document.addEventListener("visibilitychange", handleVisibilityChange);

  return () => {
    window.removeEventListener("scroll", trackScroll);
    document.removeEventListener("visibilitychange", handleVisibilityChange);
  };
}
```

## React Hook

```tsx
// src/hooks/useBeaconAnalytics.ts
import { useEffect } from "react";
import { initPageAnalytics } from "../lib/pageAnalytics";
import { sendBeacon } from "../lib/beacon";

export function useBeaconAnalytics(postId: string | undefined) {
  useEffect(() => {
    if (!postId) return;

    // Fire page_view immediately using fetch (non-critical, page is visible)
    sendBeacon({ event: "page_view", postId });

    // Hook into page lifecycle for dwell/scroll
    const cleanup = initPageAnalytics(postId);
    return cleanup;
  }, [postId]);
}

// Usage in a post component:
// useBeaconAnalytics(post.id);
```

## Batching: Queue and Flush

```typescript
// src/lib/beaconBatch.ts — coalesce many micro-events into one beacon
import { sendBeacon } from "./beacon";

const queue: object[] = [];
let flushTimer: ReturnType<typeof setTimeout> | null = null;

export function queueEvent(event: object): void {
  queue.push(event);
  if (!flushTimer) {
    flushTimer = setTimeout(flush, 500); // flush after 500 ms of inactivity
  }
}

export function flush(): void {
  if (queue.length === 0) return;
  const batch = queue.splice(0);
  const blob = new Blob([JSON.stringify({ batch })], { type: "application/json" });
  navigator.sendBeacon("https://analytics.example.com/beacon/batch", blob);
  if (flushTimer) { clearTimeout(flushTimer); flushTimer = null; }
}

// Flush on page hide regardless of timer
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden") flush();
});
```

## Anti-patterns

- **Using `fetch` in `beforeunload`** — The browser cancels inflight fetch requests when
  navigating. Use `sendBeacon` or `fetch` with `keepalive: true`.
- **Sending PII in beacons** — Beacon payloads may appear in server logs; example project is
  anonymous, so use only ephemeral session tokens.
- **Trusting `sendBeacon` return value as delivery confirmation** — `true` means queued, not
  delivered; the network may drop the request.
- **Sending beacons on every scroll event** — Debounce or batch; browsers may throttle
  origins that fire excessive beacons.

## Gotchas

- Beacon payloads are capped at 64 KiB by the spec; batch accordingly.
- `navigator.sendBeacon` is blocked by some ad-blockers; degrade gracefully.
- Cloudflare Workers must respond within 30 s but beacon processing should be offloaded via
  `ctx.waitUntil` so the 204 returns immediately.
- CORS preflight does NOT apply to `sendBeacon` with `text/plain` MIME type, but using
  `application/json` via `Blob` may trigger a preflight for cross-origin endpoints.
  Use `text/plain` content type and parse JSON server-side to avoid the preflight.

## Verification

```bash
# In Chrome DevTools → Network, filter by "beacon"
# Trigger a navigation: events should show status 204 even after page unloads

# Worker tail log
npx wrangler tail analytics-worker --format=pretty
```

## Related

- `web-vitals-cloudflare-rum-integration.md`
- `browser-performance-api.md`
- `cloudflare-pages-middleware-auth-gating.md`
- `indexeddb-offline-sync-cloudflare-d1-workers.md`

## Sources

- https://developer.mozilla.org/en-US/docs/Web/API/Navigator/sendBeacon
- https://developer.mozilla.org/en-US/docs/Web/API/Page_Visibility_API
- https://developers.cloudflare.com/workers/runtime-apis/context/#waituntil
- https://w3c.github.io/beacon/
