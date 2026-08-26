# iOS Live Activities with Cloudflare Workers Real-Time Updates

**Date:** 2026-08-23
**Author:** example.com
**Status:** production

---

## Symptom / Use-Case

You ship a Live Activity (Lock Screen / Dynamic Island widget) for real-time events — a delivery tracker, a sports scoreboard, a ride-share ETA — but the update latency is unacceptably high because you are pushing ActivityKit updates via APNs only when your backend triggers them manually. You need a Cloudflare Workers pipeline that listens to upstream event sources (webhooks, queues, third-party APIs) and pushes ActivityKit-compatible APNs payloads to connected devices within seconds, without standing up a persistent Node.js server.

---

## Context

iOS Live Activities are updated through two mechanisms:
1. **ActivityKit push notifications** — the app registers a Live Activity and returns a push token (distinct from the regular notification token). APNs delivers a `liveactivity` push type that replaces the widget's `ContentState`.
2. **`Activity.update(_:alertConfiguration:)`** — on-device update triggered from the host app. Only useful when the app is in the foreground.

The Workers pipeline owns the second path over APNs. The client POSTs its Live Activity push token to a Worker on activity start; the Worker stores the token in D1 keyed by activity ID. A separate Worker or Queue Consumer receives upstream events and fans out APNs pushes to all active tokens for that activity type.

APNs requires HTTP/2 with a JWT bearer token or a TLS client certificate. Cloudflare Workers support `fetch` with HTTP/2 but not client certificates in the standard runtime. Use APNs JWT authentication (ES256, `p8` private key).

```toml
# wrangler.toml
name = "live-activity-api"
main = "src/index.ts"
compatibility_date = "2026-08-01"

[[d1_databases]]
binding = "DB"
database_name = "live_activities"
database_id = "YOUR_D1_DATABASE_ID"

[[queues.consumers]]
queue = "activity-events"
max_batch_size = 25
max_batch_timeout = 2

[[queues.producers]]
queue = "activity-events"
binding = "EVENTS_QUEUE"

[vars]
APNS_KEY_ID = "YOUR_KEY_ID"
APNS_TEAM_ID = "YOUR_TEAM_ID"
APNS_BUNDLE_ID = "com.example.app"
```

---

## 1. D1 Schema

```sql
-- migrations/0001_live_activities.sql
CREATE TABLE IF NOT EXISTS live_activity_tokens (
  activity_id   TEXT PRIMARY KEY,
  push_token    TEXT NOT NULL,
  bundle_id     TEXT NOT NULL,
  user_id       TEXT NOT NULL,
  activity_type TEXT NOT NULL,
  registered_at INTEGER NOT NULL,
  ended_at      INTEGER
);

CREATE INDEX IF NOT EXISTS idx_lat_type ON live_activity_tokens (activity_type, ended_at);
```

---

## 2. Worker: Token Registration Endpoint

```typescript
// src/register.ts
export interface Env {
  DB: D1Database;
}

export interface RegisterTokenBody {
  activityId: string;
  pushToken: string;       // hex push token from ActivityKit
  activityType: string;    // e.g. "delivery", "sports_match"
  userId: string;
}

export async function handleRegister(request: Request, env: Env): Promise<Response> {
  if (request.method !== "POST") return new Response("Method not allowed", { status: 405 });

  const body = await request.json<RegisterTokenBody>();
  const { activityId, pushToken, activityType, userId } = body;

  if (!activityId || !pushToken || !activityType || !userId) {
    return new Response(JSON.stringify({ error: "Missing fields" }), { status: 400 });
  }

  await env.DB.prepare(
    `INSERT OR REPLACE INTO live_activity_tokens
     (activity_id, push_token, bundle_id, user_id, activity_type, registered_at)
     VALUES (?, ?, ?, ?, ?, ?)`,
  )
    .bind(activityId, pushToken, "com.example.app", userId, activityType, Date.now())
    .run();

  return new Response(JSON.stringify({ ok: true }), {
    headers: { "content-type": "application/json" },
  });
}

export async function handleEnd(request: Request, env: Env): Promise<Response> {
  if (request.method !== "POST") return new Response("Method not allowed", { status: 405 });
  const { activityId } = await request.json<{ activityId: string }>();
  await env.DB.prepare("UPDATE live_activity_tokens SET ended_at = ? WHERE activity_id = ?")
    .bind(Date.now(), activityId)
    .run();
  return new Response(JSON.stringify({ ok: true }), {
    headers: { "content-type": "application/json" },
  });
}
```

---

## 3. APNs JWT Builder

```typescript
// src/apns-jwt.ts
// ES256 JWT for APNs — private key stored as PKCS#8 PEM in a Worker Secret.

function base64url(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let b = "";
  for (const byte of bytes) b += String.fromCharCode(byte);
  return btoa(b).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export async function buildApnsJwt(
  privateKeyPem: string,
  keyId: string,
  teamId: string,
): Promise<string> {
  const header = base64url(new TextEncoder().encode(JSON.stringify({ alg: "ES256", kid: keyId })));
  const now = Math.floor(Date.now() / 1000);
  const payload = base64url(new TextEncoder().encode(JSON.stringify({ iss: teamId, iat: now })));
  const signingInput = `${header}.${payload}`;

  // Import the PEM-encoded private key
  const pemContents = privateKeyPem
    .replace(/<redacted-private-key>/, "")
    .replace(/\s/g, "");
  const der = Uint8Array.from(atob(pemContents), (c) => c.charCodeAt(0));

  const cryptoKey = await crypto.subtle.importKey(
    "pkcs8",
    der.buffer,
    { name: "ECDSA", namedCurve: "P-256" },
    false,
    ["sign"],
  );

  const signature = await crypto.subtle.sign(
    { name: "ECDSA", hash: "SHA-256" },
    cryptoKey,
    new TextEncoder().encode(signingInput),
  );

  return `${signingInput}.${base64url(signature)}`;
}
```

---

## 4. Queue Consumer: Push Live Activity Updates

```typescript
// src/index.ts
import { handleRegister, handleEnd } from "./register";
import { buildApnsJwt } from "./apns-jwt";

export interface Env {
  DB: D1Database;
  EVENTS_QUEUE: Queue;
  APNS_PRIVATE_KEY: string;     // Worker Secret: PEM-encoded ES256 private key
  APNS_KEY_ID: string;
  APNS_TEAM_ID: string;
  APNS_BUNDLE_ID: string;
}

interface ActivityEvent {
  activityType: string;
  contentState: Record<string, unknown>; // must match Swift ContentState Codable struct
  relevanceScore?: number;
  staleDate?: number; // Unix timestamp
  dismissalDate?: number;
}

async function pushLiveActivity(
  token: string,
  event: ActivityEvent,
  jwt: string,
  bundleId: string,
  isDismissal: boolean,
): Promise<void> {
  const apnsUrl = `https://api.push.apple.com/3/device/${token}`;

  const body: Record<string, unknown> = {
    aps: {
      timestamp: Math.floor(Date.now() / 1000),
      event: isDismissal ? "end" : "update",
      "content-state": event.contentState,
      ...(event.relevanceScore !== undefined && { "relevance-score": event.relevanceScore }),
      ...(event.staleDate !== undefined && { "stale-date": event.staleDate }),
      ...(event.dismissalDate !== undefined && { "dismissal-date": event.dismissalDate }),
    },
  };

  const response = await fetch(apnsUrl, {
    method: "POST",
    headers: {
      authorization: `bearer ${jwt}`,
      "apns-push-type": "liveactivity",
      "apns-topic": `${bundleId}.push-type.liveactivity`,
      "apns-priority": "10",
      "content-type": "application/json",
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const errorBody = await response.text();
    throw new Error(`APNs error ${response.status}: ${errorBody}`);
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === "/activity/register") return handleRegister(request, env);
    if (url.pathname === "/activity/end") return handleEnd(request, env);

    // Webhook entry point — push an event to the queue
    if (request.method === "POST" && url.pathname === "/activity/event") {
      const event = await request.json<ActivityEvent>();
      await env.EVENTS_QUEUE.send(event);
      return new Response(JSON.stringify({ queued: true }), {
        headers: { "content-type": "application/json" },
      });
    }

    return new Response("Not found", { status: 404 });
  },

  async queue(batch: MessageBatch<ActivityEvent>, env: Env): Promise<void> {
    const jwt = await buildApnsJwt(
      env.APNS_PRIVATE_KEY,
      env.APNS_KEY_ID,
      env.APNS_TEAM_ID,
    );

    for (const message of batch.messages) {
      const event = message.body;

      const rows = await env.DB.prepare(
        `SELECT activity_id, push_token FROM live_activity_tokens
         WHERE activity_type = ? AND ended_at IS NULL`,
      )
        .bind(event.activityType)
        .all<{ activity_id: string; push_token: string }>();

      const pushes = rows.results.map((row) =>
        pushLiveActivity(
          row.push_token,
          event,
          jwt,
          env.APNS_BUNDLE_ID,
          event.dismissalDate !== undefined,
        ).catch((err: unknown) =>
          console.error(`Push failed for activity ${row.activity_id}:`, err),
        ),
      );

      await Promise.allSettled(pushes);
      message.ack();
    }
  },
};
```

---

## 5. Swift: Registering the Push Token

```swift
// LiveActivityManager.swift (Swift 5.9+)
import ActivityKit

struct DeliveryAttributes: ActivityAttributes {
    struct ContentState: Codable, Hashable {
        var status: String
        var etaMinutes: Int
    }
    var orderId: String
}

class LiveActivityManager {
    private var activity: Activity<DeliveryAttributes>?

    func start(orderId: String) async throws {
        let attributes = DeliveryAttributes(orderId: orderId)
        let contentState = DeliveryAttributes.ContentState(status: "Preparing", etaMinutes: 30)
        let content = ActivityContent(state: contentState, staleDate: nil)

        activity = try Activity<DeliveryAttributes>.request(
            attributes: attributes,
            content: content,
            pushType: .token
        )

        // Observe push token changes and register with Workers
        for await data in activity!.pushTokenUpdates {
            let token = data.map { String(format: "%02x", $0) }.joined()
            try await registerToken(activityId: activity!.id, token: token, orderId: orderId)
        }
    }

    private func registerToken(activityId: String, token: String, orderId: String) async throws {
        var request = URLRequest(url: URL(string: "https://live-activity-api.example.workers.dev/activity/register")!)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "content-type")
        request.httpBody = try JSONEncoder().encode([
            "activityId": activityId,
            "pushToken": token,
            "activityType": "delivery",
            "userId": orderId,
        ])
        let (_, _) = try await URLSession.shared.data(for: request)
    }
}
```

---

## Anti-Patterns

- **Caching APNs JWTs for longer than 55 minutes** — APNs rejects tokens older than 60 minutes. Regenerate per Queue batch or cache with a 50-minute max-age.
- **Using the regular APNs notification token** — Live Activity push tokens are distinct from `UNUserNotificationCenter` tokens. Never mix them.
- **Sending updates after `dismissalDate` has passed** — APNs accepts the push but the system discards it silently and may revoke the token. Mark rows as `ended_at` and stop pushing.
- **Firing APNs pushes directly from a stateless Worker on every webhook** — fan-out to a Queue to avoid overwhelming APNs rate limits under high event volume.

---

## Gotchas

- The `apns-topic` header must end in `.push-type.liveactivity`, not just the bundle ID.
- Live Activity push tokens rotate. The Swift `pushTokenUpdates` async sequence delivers new tokens; each rotation must POST to your Worker to update D1.
- Cloudflare Workers support HTTP/2 in `fetch`, which is required by APNs. Confirm `compatibility_date` is ≥ 2023-03-01 where HTTP/2 `fetch` is stable.
- ContentState serialization must exactly match the Swift `Codable` struct field names — use `CodingKeys` if your TypeScript uses camelCase and Swift expects snake_case.

---

## Verification

1. Start a Live Activity on a physical device; confirm the token POST appears in `wrangler tail`.
2. Send a test event: `curl -X POST https://…/activity/event -d '{"activityType":"delivery","contentState":{"status":"Out for delivery","etaMinutes":8}}'`
3. Observe the Lock Screen widget update within ~2 seconds.
4. Check the Queue consumer processed the message: `wrangler queues messages list`.

---

## Related

- `ios-live-activities-dynamic-island.md`
- `ios-widgetkit-workers-background-refresh.md`
- `ios-push-notifications-apns-workers.md`
- `mobile-push-notifications-cloudflare-queues.md`
- `mobile-push-delivery-reliability.md`

---

## Sources

- ActivityKit documentation: https://developer.apple.com/documentation/activitykit
- APNs Live Activity push type: https://developer.apple.com/documentation/usernotifications/sending-notification-requests-to-apns
- Cloudflare Queues: https://developers.cloudflare.com/queues/
- Cloudflare Workers HTTP/2 fetch: https://developers.cloudflare.com/workers/runtime-apis/fetch/
