# Cloudflare Waiting Room Event Queue Integration with Workers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case
example project / example.com hosts viral content drops and live social events where traffic can spike 50–100x normal load in seconds. Without a queue, the origin D1 database and Durable Objects saturate instantly, causing cascading 500s that erode user trust. A Cloudflare Waiting Room solves the front-door problem, but the platform needs Workers-side event hooks to coordinate downstream capacity and emit analytics when users enter, advance, or abandon the queue.

## Context
Cloudflare Waiting Room is a Zone-level product that holds visitors in a virtual queue before admitting them to a protected path. It ships with an Event system (scheduled traffic boosts) and a JSON API for real-time queue depth metrics. Workers can consume both through fetch-based integrations and Waiting Room Bypass Tokens to let already-authenticated users skip the queue entirely.

## Waiting Room Configuration (wrangler.toml + Dashboard)

Waiting Room is configured at the Zone level, not in `wrangler.toml`. However, Workers that handle bypass tokens and event webhooks do have bindings.

```toml
# wrangler.toml — the companion Worker
name = "example project-queue-coordinator"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[[kv_namespaces]]
binding = "QUEUE_STATE"
id = "xxxxxxxxxxxxxxxxxxxxxxxxxxxx"

[[d1_databases]]
binding = "DB"
database_name = "example project-prod"
database_id = "xxxxxxxxxxxxxxxxxxxxxxxxxxxx"

[vars]
ZONE_ID = "your-zone-id"
WAITING_ROOM_ID = "your-waiting-room-id"

[[secrets]]
# CF_API_TOKEN bound at deploy time via Cloudflare dashboard
```

Create the Waiting Room via the Dashboard or Terraform. Key settings for a social event:
- **Total active users**: set to ~80% of your D1 + DO saturation limit
- **New users per minute**: ramp based on your p95 onboarding latency
- **Session duration**: 15–30 min for an interactive social session
- **JSON response**: enable so SPAs can render a custom waiting page

## Bypass Token Issuance from Workers

Pre-verified users (e.g. premium subscribers, returning sessions) should skip the queue. Bypass tokens are HMAC-signed strings issued by your Worker and validated by the Waiting Room.

```typescript
// src/bypass.ts
import { createHmac } from "node:crypto";

export interface Env {
  WAITING_ROOM_BYPASS_SECRET: string; // from Workers Secrets Store
  DB: D1Database;
}

export async function issueBypassToken(
  userId: string,
  env: Env
): Promise<string> {
  // Token format: base64url(userId + ":" + expiry) + "." + signature
  const expiry = Math.floor(Date.now() / 1000) + 3600; // 1 hour
  const payload = `${userId}:${expiry}`;
  const encoder = new TextEncoder();

  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(env.WAITING_ROOM_BYPASS_SECRET),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );

  const sig = await crypto.subtle.sign(
    "HMAC",
    key,
    encoder.encode(payload)
  );

  const sigB64 = btoa(String.fromCharCode(...new Uint8Array(sig)))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=/g, "");

  const payloadB64 = btoa(payload)
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=/g, "");

  return `${payloadB64}.${sigB64}`;
}
```

Attach the token as a cookie (`__cfwaitingroom_bypass_<ROOM_ID>`) on the user's authenticated response, and Cloudflare's edge will skip the queue for subsequent requests within that session.

## Queue Depth Polling and Capacity Coordination

The Waiting Room API exposes real-time queue depth. A scheduled Worker polls it and scales DO shard counts or toggles feature flags.

```typescript
// src/queue-coordinator.ts
export interface Env {
  ZONE_ID: string;
  WAITING_ROOM_ID: string;
  CF_API_TOKEN: string;
  QUEUE_STATE: KVNamespace;
  DB: D1Database;
}

interface WaitingRoomStatus {
  result: {
    queueing_active: boolean;
    estimated_queued_users: number;
    total_active_users: number;
  };
}

async function fetchQueueStatus(env: Env): Promise<WaitingRoomStatus> {
  const url = `https://api.cloudflare.com/client/v4/zones/${env.ZONE_ID}/waiting_rooms/${env.WAITING_ROOM_ID}/status`;
  const resp = await fetch(url, {
    headers: { Authorization: `Bearer ${env.CF_API_TOKEN}` },
  });
  if (!resp.ok) throw new Error(`WR API ${resp.status}`);
  return resp.json();
}

export async function coordinateCapacity(env: Env): Promise<void> {
  const status = await fetchQueueStatus(env);
  const { estimated_queued_users, total_active_users, queueing_active } =
    status.result;

  await env.QUEUE_STATE.put(
    "latest",
    JSON.stringify({ estimated_queued_users, total_active_users, ts: Date.now() }),
    { expirationTtl: 120 }
  );

  // Emit to Analytics Engine via D1-backed event log
  if (queueing_active) {
    await env.DB.prepare(
      `INSERT INTO queue_events (queued, active, recorded_at)
       VALUES (?, ?, CURRENT_TIMESTAMP)`
    )
      .bind(estimated_queued_users, total_active_users)
      .run();
  }
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    await coordinateCapacity(env);
  },
  async fetch(req: Request, env: Env): Promise<Response> {
    // Expose queue depth to internal dashboards
    const state = await env.QUEUE_STATE.get("latest");
    return Response.json(state ? JSON.parse(state) : { queued: 0, active: 0 });
  },
};
```

## Waiting Room Events (Traffic Boosts) via API

Cloudflare Waiting Room Events let you pre-schedule capacity increases for known traffic spikes (e.g. a scheduled content drop at 8pm).

```typescript
// src/schedule-event.ts — called from an admin Worker or CI pipeline
export async function createWaitingRoomEvent(
  env: Env,
  eventName: string,
  startAt: string, // ISO 8601
  endAt: string,
  newUsersPerMinute: number,
  totalActiveUsers: number
): Promise<void> {
  const url = `https://api.cloudflare.com/client/v4/zones/${env.ZONE_ID}/waiting_rooms/${env.WAITING_ROOM_ID}/events`;
  const body = {
    name: eventName,
    event_start_time: startAt,
    event_end_time: endAt,
    new_users_per_minute: newUsersPerMinute,
    total_active_users: totalActiveUsers,
    disable_session_renewal: false,
  };

  const resp = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.CF_API_TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });

  if (!resp.ok) {
    const err = await resp.text();
    throw new Error(`Create event failed: ${resp.status} ${err}`);
  }
}
```

Pre-create events via a CI step 30 minutes before a scheduled drop. The Waiting Room transitions to event parameters automatically.

## Anti-patterns
- Setting `total_active_users` to `Infinity` equivalent (very large number) defeats the queue and still lets the origin saturate
- Issuing bypass tokens to all users — reserve them for truly verified/premium accounts to prevent queue-bypass abuse
- Polling the Waiting Room API more frequently than every 60 seconds from a scheduled Worker (rate limits apply; use KV to cache and serve the latest value)
- Forgetting to delete or disable Waiting Room Events after the traffic spike — users continue to see the waiting room unnecessarily
- Using Waiting Room on API paths (`/api/*`) — JSON responses work but the estimated wait time UX is designed for browser sessions

## Gotchas
- Bypass tokens are zone-scoped secrets; rotating `WAITING_ROOM_BYPASS_SECRET` invalidates all outstanding bypass sessions simultaneously — roll with a grace period
- `session_duration` clock resets on each active page request; users who idle in the SPA without HTTP requests will time out of the active pool and re-enter the queue
- The Waiting Room API `status` endpoint returns stale data up to ~30 seconds behind reality under very high queue churn
- The `__cfwaitingroom_bypass_*` cookie must be set on the same domain/path as the waiting room; cross-subdomain bypass tokens do not propagate
- Waiting Room does not function behind an orange-clouded subdomain that is not proxied — ensure DNS is proxied

## Verification
1. Deploy the coordinator Worker: `npx wrangler deploy`
2. Use the Waiting Room preview URL (Dashboard → Waiting Room → Preview) to simulate a queued visitor
3. Hit `/` with a valid bypass cookie and confirm the response is `200` (not the queue page)
4. Check KV for `latest` key after the cron fires: `npx wrangler kv key get --binding=QUEUE_STATE latest`
5. Query D1 `queue_events` to confirm event rows are inserted during active queueing

## Related
- `waiting-room-traffic-management-queuing.md`
- `cloudflare-workers-cron-triggers-scheduling.md`
- `d1-best-practices.md`
- `kv-best-practices.md`
- `cloudflare-workers-secrets-store-rotation-automation.md`

## Sources
- https://developers.cloudflare.com/waiting-room/
- https://developers.cloudflare.com/waiting-room/additional-options/waiting-room-analytics/
- https://developers.cloudflare.com/waiting-room/how-to/bypass-waiting-room/
- https://developers.cloudflare.com/waiting-room/reference/waiting-room-api/
- https://developers.cloudflare.com/waiting-room/additional-options/create-events/
