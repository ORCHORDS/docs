# Durable Objects Authentication and Authorization Patterns

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

Cloudflare Durable Objects (DOs) are the stateful layer in a Workers architecture. A DO can represent a chat room, a document, a rate limiter, a queue, or any resource that needs consistent in-memory state and a single-threaded execution model. Because DOs accept messages via `fetch()` stubs from other Workers, they are reachable through an internal RPC surface that is separate from the public HTTP surface.

Two critical mistakes appear repeatedly:

1. **Assuming DOs are private**: A Worker can create a DO stub for any ID if it has the binding. If multiple Workers share the same DO binding (via the same Cloudflare account), any of them can call any DO without the DO verifying who called it.
2. **Forwarding unauthenticated user requests directly to a DO**: Some implementations pass the raw user request to a DO stub, expecting the DO to handle auth. The DO then has no context about who the user is.

This article covers how to authenticate callers to a Durable Object and how to enforce per-resource authorization inside the DO.

## Context

Durable Objects have no built-in authentication layer. Every call to a DO arrives as a standard `Request` object inside the DO's `fetch()` handler. The DO cannot distinguish a call from a trusted internal Worker versus a call from a Worker under an attacker's control on the same account unless the caller proves its identity explicitly.

Two patterns address this:

- **Shared secret header**: The calling Worker attaches a pre-shared secret in a header; the DO verifies it before processing any request. Suitable for simple single-tenant architectures.
- **Service token header with HMAC**: The calling Worker signs a per-request message with a secret bound to its own identity. The DO verifies the signature. Suitable for multi-tenant or multi-service architectures.

Additionally, the DO must enforce user-level authorization: even after verifying that the caller is a trusted Worker, it must ensure the user whose request is being forwarded is authorized to act on this specific DO instance.

## Pattern 1: Shared Internal Secret (Simple Architectures)

All Workers that legitimately call a DO share an `INTERNAL_DO_SECRET` secret:

<redacted-secret>
// src/lib/do-client.ts — called by the Worker before forwarding to DO

const INTERNAL_DO_HEADER = 'X-Internal-Secret';

export function makeDORequest(
  stub: DurableObjectStub,
  path: string,
  options: RequestInit & { internalSecret: string },
): Promise<Response> {
  const { internalSecret, ...fetchOptions } = options;
  const req = new Request(`https://do-internal${path}`, {
    ...fetchOptions,
    headers: {
      ...(fetchOptions.headers as Record<string, string> ?? {}),

    },
  });
  return stub.fetch(req);
}
```

```typescript
// src/durable-objects/room.ts — Durable Object implementation

interface Env {
  INTERNAL_DO_SECRET: string;
}

export class RoomDurableObject implements DurableObject {
  constructor(
    private readonly state: DurableObjectState,
    private readonly env: Env,
  ) {}

  async fetch(req: Request): Promise<Response> {
    // 1. Verify internal caller identity
    const provided = req.headers.get('X-Internal-Secret') ?? '';
    if (!timingSafeEqual(provided, this.env.INTERNAL_DO_SECRET)) {
      return new Response('Unauthorized', { status: 401 });
    }

    // 2. Extract forwarded user identity (set by the calling Worker after it authed the user)
    const userId = req.headers.get('X-User-Id');
    const roomId = this.state.id.toString();
    const url = new URL(req.url);

    // 3. Authorize the user for this specific room
    if (url.pathname === '/send') {
      if (!userId) return new Response('Missing user context', { status: 400 });
      const isMember = await this.isMember(userId);
      if (!isMember) return new Response('Forbidden', { status: 403 });
      return this.handleSend(req, userId);
    }

    return new Response('Not Found', { status: 404 });
  }

  private async isMember(userId: string): Promise<boolean> {
    const members = await this.state.storage.get<string[]>('members') ?? [];
    return members.includes(userId);
  }

  private async handleSend(req: Request, userId: string): Promise<Response> {
    const { message } = await req.json<{ message: string }>();
    // ... persist message, broadcast via WebSocket, etc.
    return new Response(JSON.stringify({ ok: true }), { status: 200 });
  }
}

// Timing-safe string comparison to resist timing attacks
function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  const encoder = new TextEncoder();
  const aBytes = encoder.encode(a);
  const bBytes = encoder.encode(b);
  let diff = 0;
  for (let i = 0; i < aBytes.length; i++) {
    diff |= aBytes[i] ^ bBytes[i];
  }
  return diff === 0;
}
```

The calling Worker authenticates the user, then passes the verified identity to the DO:

```typescript
// src/handlers/room-send.ts — in the public-facing Worker
import { makeDORequest } from '../lib/do-client';
import { getUserFromSession } from '../lib/auth';

export async function handleRoomSend(req: Request, env: Env): Promise<Response> {
  // Auth the user at the edge — never pass an unauthenticated request to a DO
  const user = await getUserFromSession(
    req.headers.get('Authorization')?.replace('Bearer ', '') ?? '',
    env.SESSIONS,
  );
  if (!user) return new Response(JSON.stringify({ error: 'Unauthenticated' }), { status: 401 });

  const roomId = new URL(req.url).pathname.split('/')[3]; // /api/rooms/{id}/send
  const doId = env.ROOM.idFromName(roomId);
  const stub = env.ROOM.get(doId);

  // Pass the verified user ID in a trusted internal header
  return makeDORequest(stub, '/send', {
    method: req.method,
    body: req.body,
    headers: {
      'Content-Type': 'application/json',
      'X-User-Id': user.id,       // Set by the Worker after successful auth
    },
    internalSecret: env.INTERNAL_DO_SECRET,
  });
}
```

## Pattern 2: HMAC-Signed DO Requests (Multi-service Architectures)

When multiple distinct Workers (e.g., a public API Worker and an admin Worker) call the same DO, a single shared secret cannot distinguish callers. Use per-request HMAC signatures:

```typescript
// src/lib/do-hmac.ts

const ALGO = { name: 'HMAC', hash: 'SHA-256' };

async function importKey(secret: string): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    ALGO,
    false,
    ['sign', 'verify'],
  );
}

export async function signDORequest(
  method: string,
  path: string,
  body: string,
  timestamp: number,
  secret: string,
): Promise<string> {
  const key = await importKey(secret);
  const message = `${method}\n${path}\n${timestamp}\n${body}`;
  const sig = await crypto.subtle.sign(ALGO, key, new TextEncoder().encode(message));
  return btoa(String.fromCharCode(...new Uint8Array(sig)));
}

export async function verifyDORequest(
  method: string,
  path: string,
  body: string,
  timestamp: number,
  signature: string,
  secret: string,
  toleranceSeconds = 30,
): Promise<boolean> {
  const now = Math.floor(Date.now() / 1000);
  if (Math.abs(now - timestamp) > toleranceSeconds) return false;  // Replay prevention

  const key = await importKey(secret);
  const message = `${method}\n${path}\n${timestamp}\n${body}`;
  const expectedSig = await crypto.subtle.sign(ALGO, key, new TextEncoder().encode(message));
  const expectedB64 = btoa(String.fromCharCode(...new Uint8Array(expectedSig)));
  return timingSafeStringEqual(signature, expectedB64);
}

function timingSafeStringEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  const enc = new TextEncoder();
  const aBytes = enc.encode(a);
  const bBytes = enc.encode(b);
  let diff = 0;
  for (let i = 0; i < aBytes.length; i++) diff |= aBytes[i] ^ bBytes[i];
  return diff === 0;
}
```

```typescript
// Inside the Durable Object — verifies the HMAC signature
async fetch(req: Request): Promise<Response> {
  const timestamp = parseInt(req.headers.get('X-Timestamp') ?? '0', 10);
  const signature = req.headers.get('X-Signature') ?? '';
  const url = new URL(req.url);
  const bodyText = await req.text();

  const valid = await verifyDORequest(
    req.method,
    url.pathname,
    bodyText,
    timestamp,
    signature,
    this.env.DO_HMAC_SECRET,
  );

  if (!valid) {
    return new Response('Invalid signature', { status: 401 });
  }

  // Re-parse body since we consumed it above
  const body = bodyText ? JSON.parse(bodyText) : null;
  // ... route and handle
}
```

## Authorizing Resource Access Inside the DO

After verifying the caller, the DO enforces per-resource authorization:

```typescript
// Ownership model: the DO ID encodes the owner's user ID
// DO name = "document:{ownerId}:{docId}"
// Only the owner can write; collaborators can read

async function handleWrite(userId: string, body: unknown): Promise<Response> {
  const doName = this.state.id.name ?? '';  // e.g. "document:user-123:doc-abc"
  const ownerId = doName.split(':')[1];

  if (userId !== ownerId) {
    return new Response('Write access denied', { status: 403 });
  }

  await this.state.storage.put('content', body);
  return new Response(JSON.stringify({ ok: true }), { status: 200 });
}

async function handleRead(userId: string): Promise<Response> {
  const doName = this.state.id.name ?? '';
  const ownerId = doName.split(':')[1];
  const collaborators = await this.state.storage.get<string[]>('collaborators') ?? [];

  if (userId !== ownerId && !collaborators.includes(userId)) {
    return new Response('Read access denied', { status: 403 });
  }

  const content = await this.state.storage.get('content');
  return new Response(JSON.stringify({ content }), { status: 200 });
}
```

## Wrangler Configuration

```toml
# wrangler.toml
[[durable_objects.bindings]]
name = "ROOM"
class_name = "RoomDurableObject"

[[migrations]]
tag = "v1"
new_classes = ["RoomDurableObject"]
```

```bash
# Store the internal secret as a Workers secret — it applies to both
# the calling Worker and the DO since they share the same wrangler.toml
wrangler secret put INTERNAL_DO_SECRET --env production
wrangler secret put DO_HMAC_SECRET --env production
```

## Anti-patterns

- **No authentication in the DO**: Assuming DOs are unreachable from outside is wrong. Any Worker with the binding can call any DO. Always verify caller identity inside the DO.
- **Forwarding the raw user request to a DO without extracting identity first**: The DO cannot call KV or D1 reliably to validate a session token on every request (latency, DO invocation limits). Authenticate the user in the gateway Worker and pass the verified user ID in a trusted header.
- **Using `idFromString()` with user-supplied IDs**: `idFromString()` generates a DO ID deterministically from the input. If an attacker supplies a crafted string, they can target a specific DO. Use `idFromName()` with a server-controlled namespace prefix.
- **Storing authorization state only in DO memory**: Memory is lost when the DO hibernates. Persist access control lists (ACLs) to `this.state.storage` so they survive hibernation.
- **Not validating the timestamp in HMAC requests**: Without a timestamp replay window check, a captured HMAC signature can be replayed indefinitely.

## Gotchas

- **DO hibernation resets in-memory state**: If you cache a permission lookup in a Map inside the DO class, it will be gone after the DO hibernates (no traffic for ~10 seconds). Persist ACLs in `this.state.storage`.
- **WebSocket upgrades and auth**: When a client connects via WebSocket to a DO, the upgrade request is the only chance to verify identity. Reject the upgrade with 401/403 if the initial request is not authenticated. After the WebSocket is open, per-message auth is expensive; rely on the initial verification.
- **DO alarms do not carry caller identity**: Code running inside a DO alarm is initiated by the DO itself, not by a Worker. Do not check for caller auth headers in alarm handlers.
- **Multiple Workers sharing a binding**: If you add a second Worker (e.g., an admin Worker) that uses the same DO binding, audit whether it should have the same access level. Use separate bindings with separate secrets if access levels differ.
- **`idFromName()` is deterministic across your account**: Two Workers calling `env.ROOM.idFromName('global')` get the same DO. Ensure namespace prefixes are specific enough to avoid collisions between different logical resources.

## Verification

```bash
# 1. Attempt to call a DO route without the internal secret header — expect 401
curl -s -X POST "https://worker.workers.dev/api/rooms/abc/send" \
  -H "Authorization: Bearer valid_user_token" \
  -H "Content-Type: application/json" \
  -d '{"message":"hello"}' | jq .

# 2. Attempt to send a message to a room the user is not a member of — expect 403
curl -s -X POST "https://worker.workers.dev/api/rooms/restricted-room/send" \
  -H "Authorization: Bearer valid_user_token" \
  -H "Content-Type: application/json" \
  -d '{"message":"intruder"}' | jq .

# 3. Replay a captured HMAC signature after the tolerance window — expect 401
# (manually test by setting the timestamp to now - 60)
```

## Related

- `rate-limiting-per-user-d1-durable-objects.md`
- `jwt-sliding-window-refresh-workers-kv.md`
- `multi-tenancy-isolation-workers-kv-d1.md`
- `timing-safe-compare.md`
- `websocket-security-authorization.md`

## Sources

- Cloudflare Durable Objects documentation: https://developers.cloudflare.com/durable-objects/
- DO storage API: https://developers.cloudflare.com/durable-objects/api/storage-api/
- DO WebSocket hibernation: https://developers.cloudflare.com/durable-objects/examples/websocket-hibernation-server/
- Workers secrets: https://developers.cloudflare.com/workers/configuration/secrets/
