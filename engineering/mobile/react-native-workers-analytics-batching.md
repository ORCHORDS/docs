# React Native Analytics Batching to Workers Analytics Engine

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
Sending one HTTP request per analytics event from a mobile app wastes bandwidth, drains battery, and triggers Cloudflare rate-limiting at scale. Batching events client-side and flushing to a Workers Analytics Engine endpoint reduces network calls by 10–100x while preserving per-event resolution.

## Context
Cloudflare's Analytics Engine is a write-optimized time-series store exposed via the Workers binding `env.ANALYTICS.writeDataPoint()`. Workers can receive a batch of events from mobile, fan them out to Analytics Engine in a loop, and return in under 5 ms. The mobile client collects events in memory (or MMKV for persistence across backgrounding), flushes on a timer or when the queue reaches a size threshold, and falls back gracefully when offline.

## Client-side Event Queue

```typescript
// analytics/queue.ts
import { MMKV } from 'react-native-mmkv';
import NetInfo from '@react-native-community/netinfo';

const storage = new MMKV({ id: 'analytics-queue' });
const QUEUE_KEY = 'event_queue';
const FLUSH_INTERVAL_MS = 30_000;  // 30 s
const FLUSH_SIZE_THRESHOLD = 20;   // flush early if 20 events pile up

export interface AnalyticsEvent {
  name: string;
  ts: number;                          // epoch ms
  doubles?: number[];                  // up to 20 numeric measurements
  blobs?: string[];                    // up to 20 string labels (truncated to 1024 chars by AE)
}

export class AnalyticsQueue {
  private flushTimer: ReturnType<typeof setInterval> | null = null;
  private flushUrl: string;
  private appToken: string;

  constructor(flushUrl: string, appToken: string) {
    this.flushUrl = flushUrl;
    this.appToken = appToken;
  }

  track(event: Omit<AnalyticsEvent, 'ts'>): void {
    const queue = this.readQueue();
    queue.push({ ...event, ts: Date.now() });
    storage.set(QUEUE_KEY, JSON.stringify(queue));

    if (queue.length >= FLUSH_SIZE_THRESHOLD) {
      this.flush().catch(console.error);
    }
  }

  start(): void {
    if (this.flushTimer) return;
    this.flushTimer = setInterval(() => {
      this.flush().catch(console.error);
    }, FLUSH_INTERVAL_MS);
  }

  stop(): void {
    if (this.flushTimer) {
      clearInterval(this.flushTimer);
      this.flushTimer = null;
    }
  }

  async flush(): Promise<void> {
    const queue = this.readQueue();
    if (queue.length === 0) return;

    const net = await NetInfo.fetch();
    if (!net.isConnected) return; // leave in queue; retry on next interval

    // Snapshot and clear optimistically
    storage.delete(QUEUE_KEY);

    try {
      const res = await fetch(this.flushUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-App-Token': this.appToken,
        },
        body: JSON.stringify({ events: queue }),
      });

      if (!res.ok) {
        // Restore events so they are not lost
        this.prependToQueue(queue);
      }
    } catch {
      this.prependToQueue(queue);
    }
  }

  private readQueue(): AnalyticsEvent[] {
    try {
      return JSON.parse(storage.getString(QUEUE_KEY) ?? '[]') as AnalyticsEvent[];
    } catch {
      return [];
    }
  }

  private prependToQueue(events: AnalyticsEvent[]): void {
    const current = this.readQueue();
    // Avoid unbounded growth: keep newest 500 events on repeated failure
    const merged = [...events, ...current].slice(0, 500);
    storage.set(QUEUE_KEY, JSON.stringify(merged));
  }
}

// Singleton export
export const analytics = new AnalyticsQueue(
  'https://api.example.com/analytics',
  process.env.EXPO_PUBLIC_APP_TOKEN ?? ''
);
```

## Workers Ingestion Endpoint

```typescript
// worker/src/analytics.ts
import { Env } from './types';

interface EventPayload {
  name: string;
  ts: number;
  doubles?: number[];
  blobs?: string[];
}

interface BatchPayload {
  events: EventPayload[];
}

export async function handleAnalytics(request: Request, env: Env): Promise<Response> {
  const appToken = request.headers.get('X-App-Token');
  if (appToken !== env.APP_TOKEN) {
    return new Response('Unauthorized', { status: 401 });
  }

  let body: BatchPayload;
  try {
    body = await request.json<BatchPayload>();
  } catch {
    return new Response('Bad Request', { status: 400 });
  }

  const { events } = body;
  if (!Array.isArray(events) || events.length === 0) {
    return new Response('No events', { status: 422 });
  }

  // Analytics Engine: max 25 data points per writeDataPoint call
  // but each call is cheap; fan out in a loop
  for (const event of events.slice(0, 1_000)) {
    env.ANALYTICS.writeDataPoint({
      // blobs[0] is the event name; blobs[1..] are custom labels
      blobs: [
        event.name,
        ...(event.blobs ?? []).slice(0, 19).map((b) => b.substring(0, 1024)),
      ],
      doubles: (event.doubles ?? []).slice(0, 20),
      // AE timestamps are in seconds
      timestamp: new Date(event.ts),
      // indexes are used for efficient filtering (max 1)
      indexes: [event.name],
    });
  }

  return new Response(null, { status: 204 });
}
```

```typescript
// worker/src/index.ts
import { Env } from './types';
import { handleAnalytics } from './analytics';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { pathname } = new URL(request.url);

    if (pathname === '/analytics' && request.method === 'POST') {
      return handleAnalytics(request, env);
    }

    return new Response('Not found', { status: 404 });
  },
};
```

```toml
# wrangler.toml
name = "mobile-analytics"
main = "src/index.ts"
compatibility_date = "2025-08-01"

[[analytics_engine_datasets]]
binding = "ANALYTICS"
dataset = "mobile_events"

[vars]
APP_TOKEN = "replace-with-secret-via-wrangler-secret"
```

## App Lifecycle Integration

```typescript
// App.tsx
import { useEffect } from 'react';
import { AppState, AppStateStatus } from 'react-native';
import { analytics } from './analytics/queue';

export default function App() {
  useEffect(() => {
    analytics.start();

    const sub = AppState.addEventListener('change', (state: AppStateStatus) => {
      if (state === 'background' || state === 'inactive') {
        // Flush before going to background — no guarantee of background time
        analytics.flush().catch(console.error);
      }
    });

    return () => {
      analytics.stop();
      sub.remove();
    };
  }, []);

  // Track screen views
  useEffect(() => {
    analytics.track({ name: 'app_open', blobs: ['home'], doubles: [] });
  }, []);

  return <RootNavigator />;
}
```

## Anti-patterns
- Sending a single HTTP request per event — O(n) network calls; devastates low-signal connections
- Storing the queue in AsyncStorage with JSON.parse/stringify on every write — use MMKV for synchronous, fast I/O
- Flushing every second — wastes battery; 15–30 second intervals are sufficient for analytics
- Dropping events silently on flush failure — restore them to the queue for the next interval
- Writing unbounded doubles/blobs arrays to Analytics Engine — AE limits are 20 doubles and 20 blobs per data point

## Gotchas
- `Analytics Engine` is append-only; you cannot delete or update individual data points
- Workers AE binding `writeDataPoint` is asynchronous but does not return a Promise — failures are fire-and-forget
- On Android, the flush on `AppState 'background'` event is not guaranteed to complete before the process is paused; use a short Headless JS task for guaranteed delivery
- AE dataset names must be <= 64 chars and match `[a-zA-Z0-9_]`; colons and hyphens are rejected
- The SQL API for querying AE (`analytics_engine_sql_api`) has a 100-row result cap without pagination — use LIMIT/OFFSET

## Verification

```bash
# Query Analytics Engine via REST API
curl "https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  --data "SELECT blob1 AS event_name, count() AS cnt \
          FROM mobile_events \
          WHERE timestamp > NOW() - INTERVAL '1' HOUR \
          GROUP BY event_name \
          ORDER BY cnt DESC \
          LIMIT 20"

# Check batch ingestion rate (events per minute)
curl "..." --data "SELECT toStartOfMinute(timestamp) AS minute, count() AS events \
                   FROM mobile_events \
                   WHERE timestamp > NOW() - INTERVAL '10' MINUTE \
                   GROUP BY minute ORDER BY minute"
```

```typescript
// Inspect queue size at runtime (debug builds only)
import { MMKV } from 'react-native-mmkv';
const storage = new MMKV({ id: 'analytics-queue' });
const queue = JSON.parse(storage.getString('event_queue') ?? '[]');
console.log('Pending events:', queue.length);
```

## Related
- `mobile-analytics-patterns.md` — cross-platform analytics strategy
- `flutter-workers-error-reporting-analytics-engine.md` — Flutter equivalent using AE
- `react-native-workers-crash-analytics-d1-tail.md` — crash reporting with D1 tail workers
- `mobile-battery-optimization.md` — timer interval trade-offs for battery life
- `react-native-mmkv-storage.md` — MMKV for high-performance local storage

## Sources
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/analytics/analytics-engine/worker-binding/
- https://reactnative.dev/docs/appstate
- https://mrousavy.github.io/react-native-mmkv/
- https://github.com/react-native-netinfo/react-native-netinfo
