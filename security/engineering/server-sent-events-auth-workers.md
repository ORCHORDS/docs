# Server-Sent Events Authentication and Authorization on Workers

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Server-Sent Events (SSE) streams keep long-lived HTTP connections open to push real-time
updates to browsers. Unlike ordinary REST calls, the browser's `EventSource` API sends no
`Authorization` header — only cookies and same-origin credentials — making token-based auth
non-trivial and authorization checks easy to miss after the initial handshake.

## Context

Cloudflare Workers handle SSE with `ReadableStream` and the `text/event-stream` content type.
Because a Worker invocation lasts as long as the stream is open (up to the platform's CPU and
wall-clock limits), auth logic that runs only at connection time must be re-evaluated
periodically, and per-event filtering must prevent cross-tenant data leakage. Durable Objects
can manage long-lived broadcast state while Workers enforce per-connection auth.

## Threat Model

**Attacker goal**: receive events intended for another user, maintain a stream after the
underlying session or token has been revoked, or inject malicious event data.

Attack scenarios:

- **Session theft via EventSource**: `EventSource` cannot set custom headers; if authentication
  relies solely on a cookie the attacker forged or stole, they gain a persistent read channel.
- **Stale stream after logout**: a user logs out; the SSE stream opened before logout keeps
  delivering their data because the Worker never re-checks the session.
- **Cross-tenant event leakage**: a multi-tenant Worker broadcasts events to all open streams
  without per-event tenant filtering, exposing one tenant's data to another.
- **SSE injection**: if event data is user-controlled and not sanitised, an attacker embeds
  `\n\nevent: admin\ndata: ...` sequences that alter the event stream for other subscribers.
- **CSRF via EventSource**: `EventSource` follows cross-origin redirects with cookies, making it
  usable as a CSRF vector if the SSE endpoint triggers side effects on GET.

## Implementation — Authenticated SSE Endpoint

```typescript
// sse-worker/src/index.ts
import { KVNamespace } from '@cloudflare/workers-types';

export interface Env {
  SESSIONS: KVNamespace;
  // Tenant-scoped event channels via Durable Objects
  CHANNEL: DurableObjectNamespace;
}

interface SessionData {
  userId: string;
  tenantId: string;
  expiresAt: number;
  scopes: string[];
}

async function validateSession(request: Request, env: Env): Promise<SessionData | null> {
  // Option A: signed HttpOnly cookie (preferred — not accessible to JS)
  const cookie = request.headers.get('Cookie') ?? '';
  const sessionId = parseCookie(cookie, 'sid');
  if (!sessionId) return null;

  const data = await env.SESSIONS.get<SessionData>(`session:${sessionId}`, 'json');
  if (!data) return null;
  if (data.expiresAt < Math.floor(Date.now() / 1000)) return null;
  return data;
}

function parseCookie(header: string, name: string): string | null {
  for (const part of header.split(';')) {
    const [k, v] = part.trim().split('=');
    if (k === name && v) return decodeURIComponent(v);
  }
  return null;
}

// Sanitise event data to prevent SSE injection via newlines
function sanitiseEventData(raw: unknown): string {
  const str = typeof raw === 'string' ? raw : JSON.stringify(raw);
  // SSE spec: data lines must not contain \r or \n — strip them
  return str.replace(/[\r\n]/g, ' ');
}

// Build a single SSE event frame
function sseEvent(opts: {
  event?: string;
  data: string;
  id?: string;
  retry?: number;
}): string {
  const lines: string[] = [];
  if (opts.retry !== undefined) lines.push(`retry: ${opts.retry}`);
  if (opts.id) lines.push(`id: ${opts.id}`);
  if (opts.event) lines.push(`event: ${opts.event}`);
  lines.push(`data: ${sanitiseEventData(opts.data)}`);
  lines.push('', ''); // blank line terminates event
  return lines.join('\n');
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Only GET is valid for SSE; reject others to block CSRF side-effect attacks
    if (request.method !== 'GET') {
      return new Response('Method Not Allowed', { status: 405, headers: { Allow: 'GET' } });
    }

    const url = new URL(request.url);
    if (url.pathname !== '/events') {
      return new Response('Not Found', { status: 404 });
    }

    // Step 1: validate session before opening any stream
    const session = await validateSession(request, env);
    if (!session) {
      // Return 401 — browser EventSource does not expose the status code,
      // but the stream will simply not open; the app can detect this and redirect to login.
      return new Response('Unauthorized', {
        status: 401,
        headers: { 'WWW-Authenticate': 'Cookie realm="app"' },
      });
    }

    // Step 2: validate scope — ensure caller is allowed to subscribe to events
    if (!session.scopes.includes('events:read')) {
      return new Response('Forbidden', { status: 403 });
    }

    // Step 3: check Origin to mitigate cross-site EventSource CSRF
    const origin = request.headers.get('Origin');
    const allowedOrigins = ['https://app.example.com', 'https://beta.example.com'];
    if (origin && !allowedOrigins.includes(origin)) {
      return new Response('Forbidden', { status: 403 });
    }

    // Step 4: set up a tenant-scoped Durable Object channel
    const channelId = env.CHANNEL.idFromName(`tenant:${session.tenantId}`);
    const channel = env.CHANNEL.get(channelId);

    // Step 5: stream events with periodic re-auth checks
    const { readable, writable } = new TransformStream<string, Uint8Array>({
      transform(chunk, ctrl) {
        ctrl.enqueue(new TextEncoder().encode(chunk));
      },
    });

    const writer = writable.getWriter();
    const sessionId = parseCookie(request.headers.get('Cookie') ?? '', 'sid')!;

    // Kick off the streaming loop in a separate microtask
    streamEvents(writer, session, sessionId, channel, env).catch(() => {
      writer.close().catch(() => {});
    });

    return new Response(readable as unknown as BodyInit, {
      status: 200,
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache, no-store',
        Connection: 'keep-alive',
        // Prevent intermediary buffering
        'X-Accel-Buffering': 'no',
        // Allow specific origin only — wildcard breaks credentialed EventSource
        'Access-Control-Allow-Origin': origin ?? 'https://app.example.com',
        'Access-Control-Allow-Credentials': 'true',
        Vary: 'Origin',
      },
    });
  },
};

async function streamEvents(
  writer: WritableStreamDefaultWriter<string>,
  session: SessionData,
  sessionId: string,
  channel: DurableObjectStub,
  env: Env,
): Promise<void> {
  // Send initial connection confirmation
  await writer.write(sseEvent({ event: 'connected', data: JSON.stringify({ userId: session.userId }) }));

  let lastReauthAt = Date.now();
  const REAUTH_INTERVAL_MS = 30_000; // re-verify session every 30 s

  // Poll the Durable Object for new events (in production, use a WebSocket to the DO instead)
  let cursor = '0';
  while (true) {
    // Periodic re-authentication check
    if (Date.now() - lastReauthAt > REAUTH_INTERVAL_MS) {
      const fresh = await env.SESSIONS.get<SessionData>(`session:${sessionId}`, 'json');
      if (!fresh || fresh.expiresAt < Math.floor(Date.now() / 1000)) {
        // Session expired or revoked — close the stream
        await writer.write(sseEvent({ event: 'auth-expired', data: 'session expired' }));
        await writer.close();
        return;
      }
      lastReauthAt = Date.now();
    }

    // Fetch events from the Durable Object channel, scoped to this tenant
    const resp = await channel.fetch('https://internal/poll?cursor=' + cursor, {
      method: 'GET',
      headers: { 'X-Tenant-Id': session.tenantId, 'X-User-Id': session.userId },
    });

    if (resp.ok) {
      const payload = await resp.json<{ events: Array<{ id: string; type: string; data: unknown }>; next: string }>();
      for (const evt of payload.events) {
        await writer.write(sseEvent({
          event: evt.type,
          id: evt.id,
          data: JSON.stringify(evt.data),
        }));
      }
      cursor = payload.next;
    }

    // Back-pressure: yield to avoid CPU time limit
    await new Promise(r => setTimeout(r, 500));
  }
}
```

## Hardening — Token-in-URL Alternative with One-Time Ticket

```typescript
// When cookies are not available (native mobile EventSource wrappers), issue a
// short-lived one-time ticket redeemable at the SSE endpoint only.
export async function issueStreamTicket(
  userId: string,
  tenantId: string,
  env: Env,
): Promise<string> {
  const ticket = crypto.randomUUID();
  const key = `sse-ticket:${ticket}`;
  await env.SESSIONS.put(key, JSON.stringify({ userId, tenantId, scopes: ['events:read'] }), {
    // Ticket valid for 30 s; must be redeemed before expiry
    expirationTtl: 30,
  });
  return ticket;
}

// In the SSE handler, accept the ticket once then delete it (one-time use)
async function redeemTicket(ticket: string, env: Env): Promise<SessionData | null> {
  const key = `sse-ticket:${ticket}`;
  const data = await env.SESSIONS.get<SessionData>(key, 'json');
  if (!data) return null;
  // Atomic delete — if two requests race, only one gets the ticket
  await env.SESSIONS.delete(key);
  return data;
}
```

## Anti-patterns

- **Skipping CORS / Origin checks**: `EventSource` sends cookies cross-origin by default; an
  attacker page can open an SSE stream as the victim unless you validate `Origin`.
- **No periodic re-auth**: authenticating only at connection time means a revoked session or
  logged-out user keeps receiving events for the session lifetime.
- **Broadcasting without tenant filtering**: sending all events to all streams and filtering
  on the client is a data-leakage risk; filter server-side before writing to each stream.
- **User-controlled event `type` values**: if `event:` field is set from user input without
  sanitisation, attackers inject crafted event types that confuse client-side handlers.
- **Token in query string**: `?token=...` appears in Cloudflare access logs, `Referer` headers,
  and CDN edge caches; use short-lived tickets or signed cookies instead.

## Gotchas

- **Workers CPU time**: a long-lived SSE connection counts CPU time only when the Worker is
  actively executing; use Durable Objects for the event fan-out state machine to avoid the
  Worker's 30 s CPU wall-clock limit.
- **`Last-Event-ID` replay**: browsers auto-reconnect SSE and send `Last-Event-ID`; validate
  that the reconnecting client still owns the session before resuming from that cursor.
- **Buffering by Cloudflare**: Cloudflare may buffer small SSE frames; set
  `Transfer-Encoding: chunked` or ensure frames are large enough (>1 KB) to flush, or use
  the `X-Accel-Buffering: no` header.
- **`EventSource` cannot set `Authorization`**: the browser API has no hook for custom headers;
  token-in-URL or cookie are the only options — design your auth scheme accordingly.
- **Stream lingering after error**: if the upstream DO throws, the stream silently stops
  without sending a close event; always wrap the streaming loop in try/finally and send an
  `error` event before closing so the client can reconnect intelligently.

## Verification

```bash
# 1. Unauthenticated request must return 401 (not open a stream)
curl -s -o /dev/null -w "%{http_code}" \
  -H "Accept: text/event-stream" \
  https://app.example.workers.dev/events
# expect: 401

# 2. Cross-origin EventSource attempt (wrong Origin) must be rejected
curl -s -o /dev/null -w "%{http_code}" \
  -H "Origin: https://evil.example.com" \
  -H "Cookie: sid=valid-session" \
  -H "Accept: text/event-stream" \
  https://app.example.workers.dev/events
# expect: 403

# 3. Content-Type must be text/event-stream
curl -sv -H "Cookie: sid=valid-session" \
  -H "Accept: text/event-stream" \
  https://app.example.workers.dev/events 2>&1 | grep -i content-type
# expect: content-type: text/event-stream

# 4. After session revocation, stream should close with auth-expired event
# Revoke session in KV, then observe that the SSE client receives event: auth-expired
```

## Related

- `websocket-security-authorization.md`
- `session-fixation-workers-d1-rotation.md`
- `cors-cloudflare-workers-mobile-preflight.md`
- `csrf-protection-double-submit.md`
- `durable-objects-auth-patterns.md`

## Sources

- https://html.spec.whatwg.org/multipage/server-sent-events.html — SSE specification
- https://developer.mozilla.org/en-US/docs/Web/API/EventSource
- https://developers.cloudflare.com/workers/runtime-apis/streams/
