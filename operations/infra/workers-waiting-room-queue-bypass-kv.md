# Cloudflare Waiting Room: API Provisioning, Bypass Cookies, KV VIP List, and Queue Monitoring

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to protect a high-traffic URL (product launch, ticket sale) from overwhelming your origin, allow known VIP users to skip the queue, and monitor queue depth in real time. Cloudflare Waiting Room handles queueing at the edge; a Worker manages bypass cookie issuance and a KV namespace stores the VIP allowlist.

## Context

- Cloudflare Waiting Room (requires Pro plan or above, zone-level feature)
- Waiting Room is provisioned via the Cloudflare REST API (can also use Terraform)
- Bypass cookie is generated server-side by a Worker using a shared secret
- KV stores the VIP user IDs; Worker checks KV on each authenticated request
- Stack: TypeScript Workers, Workers KV, Cloudflare REST API, Wrangler v3

---

## Section 1: Provision a Waiting Room via API

```bash
# Create a Waiting Room on your zone
export ZONE_ID="<your-zone-id>"
export CF_API_TOKEN="<your-api-token>"

curl -s -X POST \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/waiting_rooms" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "product-launch-queue",
    "host": "shop.example.com",
    "path": "/launch",
    "total_active_users": 500,
    "new_users_per_minute": 200,
    "session_duration": 5,
    "queue_all": false,
    "disable_session_renewal": false,
    "description": "Queue for product launch page",
    "enabled": true
  }' | jq .

# List existing waiting rooms
curl -s \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/waiting_rooms" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result[] | {id, name, path, enabled}'

# Get queue status (live monitoring)
curl -s \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/waiting_rooms/${WAITING_ROOM_ID}/status" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq .
```

---

## Section 2: Bypass Cookie Generation in a Worker

When a VIP user is identified (JWT auth, OAuth callback, admin issuance), your Worker sets a `__cf_waitingroom_bypass` cookie so Cloudflare's Waiting Room lets them through.

```typescript
// src/bypass.ts
// Waiting Room bypass cookie must be HMAC-SHA256 signed with your Waiting Room secret.

export interface Env {
  WAITING_ROOM_BYPASS_SECRET: string; // Wrangler secret — from CF Waiting Room settings
  VIP_KV: KVNamespace; // KV namespace for VIP user list
}

async function generateBypassCookie(
  waitingRoomId: string,
  secret: string
): Promise<string> {
  const now = Math.floor(Date.now() / 1000);
  // Cookie value format: timestamp.HMAC(waitingRoomId + "." + timestamp)
  const message = `${waitingRoomId}.${now}`;
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const sig = await crypto.subtle.sign(
    "HMAC", key, new TextEncoder().encode(message)
  );
  const sigHex = Array.from(new Uint8Array(sig))
    .map((b) => b.toString(16).padStart(2, "0")).join("");

  return `${now}.${sigHex}`;
}

export async function handleVIPRequest(
  request: Request,
  env: Env
): Promise<Response> {
  // This Worker runs on a separate route, e.g. /auth/vip-entry
  // After user is authenticated, check VIP list and issue bypass cookie.

  const userId = request.headers.get("X-User-Id");
  if (!userId) {
    return new Response("Unauthenticated", { status: 401 });
  }

  // Check KV VIP list
  const isVIP = await env.VIP_KV.get(`vip:${userId}`);
  if (!isVIP) {
    // Not a VIP — redirect to the protected URL and let Waiting Room queue them
    return Response.redirect("https://shop.example.com/launch", 302);
  }

  const WAITING_ROOM_ID = "<your-waiting-room-id>";
  const cookieValue = await generateBypassCookie(
    WAITING_ROOM_ID,
    env.WAITING_ROOM_BYPASS_SECRET
  );

  // Set bypass cookie and redirect to the protected page
  const response = Response.redirect("https://shop.example.com/launch", 302);
  const headers = new Headers(response.headers);
  headers.set(
    "Set-Cookie",
    [
      `__cf_waitingroom_bypass=${cookieValue}`,
      "Path=/launch",
      "HttpOnly",
      "Secure",
      "SameSite=Lax",
      "Max-Age=300", // 5-minute window to enter
    ].join("; ")
  );

  return new Response(null, {
    status: 302,
    headers,
  });
}
```

---

## Section 3: KV-backed VIP List Management

```typescript
// src/vip-admin.ts
// Admin API for managing the VIP list in KV.
// Protect this route with an admin API key.

export interface AdminEnv {
  VIP_KV: KVNamespace;
  ADMIN_API_KEY: string;
}

interface VIPEntry {
  userId: string;
  addedAt: string;
  addedBy: string;
  note?: string;
}

export async function handleAdminVIPRequest(
  request: Request,
  env: AdminEnv
): Promise<Response> {
  // Auth check
  if (request.headers.get("X-Admin-Key") !== env.ADMIN_API_KEY) {
    return new Response("Forbidden", { status: 403 });
  }

  const url = new URL(request.url);
  const userId = url.searchParams.get("userId");

  if (request.method === "PUT" && userId) {
    // Add VIP
    const body = await request.json() as { addedBy: string; note?: string };
    const entry: VIPEntry = {
      userId,
      addedAt: new Date().toISOString(),
      addedBy: body.addedBy,
      note: body.note,
    };
    await env.VIP_KV.put(`vip:${userId}`, JSON.stringify(entry), {
      expirationTtl: 86400 * 7, // VIP status expires after 7 days
    });
    return Response.json({ status: "added", userId });
  }

  if (request.method === "DELETE" && userId) {
    // Remove VIP
    await env.VIP_KV.delete(`vip:${userId}`);
    return Response.json({ status: "removed", userId });
  }

  if (request.method === "GET") {
    // List all VIPs (paginate with cursor)
    const cursor = url.searchParams.get("cursor") ?? undefined;
    const list = await env.VIP_KV.list({ prefix: "vip:", limit: 100, cursor });
    const vips = await Promise.all(
      list.keys.map(async (k) => {
        const val = await env.VIP_KV.get(k.name);
        return val ? JSON.parse(val) as VIPEntry : null;
      })
    );
    return Response.json({
      vips: vips.filter(Boolean),
      cursor: list.cursor,
      complete: list.list_complete,
    });
  }

  return new Response("Method not allowed", { status: 405 });
}
```

---

## Section 4: Monitoring Queue Depth

```bash
# Poll queue status during a live event
export ZONE_ID="<zone-id>"
export WAITING_ROOM_ID="<waiting-room-id>"
export CF_API_TOKEN="<token>"

watch -n 10 'curl -s \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/waiting_rooms/${WAITING_ROOM_ID}/status" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq \
  "{status: .result.status, queuedUsers: .result.estimated_queued_users, activeUsers: .result.estimated_total_active_users}"'

# Automate with a Workers Cron Trigger to write queue depth to Analytics Engine
# (see cloudflare-ddos-managed-ruleset-workers-api.md for Analytics Engine patterns)
```

---

## Anti-patterns

- Do not hardcode the bypass secret in Worker source — always use Wrangler secrets (`wrangler secret put`).
- Do not set `queue_all: true` permanently — it queues everyone including already-admitted users on navigation.
- Do not store VIP state in Workers Cache API — KV is the correct durable store; Cache is ephemeral and per-PoP.
- Do not skip cookie `HttpOnly` and `Secure` flags on the bypass cookie — it contains a signed token.

## Gotchas

- Bypass cookies are scoped to the path configured on the Waiting Room; a cookie for `/launch` does not bypass `/checkout`.
- The `__cf_waitingroom_bypass` cookie format is internal to Cloudflare and may change; always generate it using the algorithm documented in the dashboard or derive it from the official JS example.
- Waiting Room requires an orange-clouded (proxied) DNS record — it does not work with grey-cloud (DNS-only).
- `estimated_queued_users` in the status API is an estimate; plan for ±20% accuracy.
- Session duration and new_users_per_minute interact: a short session with high throughput will have rapid turnover but may admit more than `total_active_users` briefly.

## Verification

```bash
# Test bypass cookie issuance (replace with real cookie secret)
curl -v -H "X-User-Id: vip-user-001" https://platform.example.com/auth/vip-entry
# Expect: 302 with Set-Cookie: __cf_waitingroom_bypass=...

# Confirm queue is active
curl -s \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/waiting_rooms/${WAITING_ROOM_ID}/status" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq .result.status
# Expect: "queueAll" | "waitingRoomOnly" | "eventPrequeueing" | "not_queueing"

# Add a VIP via admin API
curl -s -X PUT \
  "https://platform.example.com/admin/vip?userId=user-123" \
  -H "X-Admin-Key: ${ADMIN_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"addedBy": "ops-team", "note": "Beta tester"}'
```

## Related

- `documentation/categories/infra/cloudflare-ddos-managed-ruleset-workers-api.md`
- `documentation/categories/infra/workers-for-platforms-dispatch-namespace.md`

## Sources

- https://developers.cloudflare.com/waiting-room/
- https://developers.cloudflare.com/waiting-room/how-to/create-waiting-room/
- https://developers.cloudflare.com/waiting-room/additional-options/waiting-room-cookie/
- https://developers.cloudflare.com/kv/
