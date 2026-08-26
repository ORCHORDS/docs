# Incident Communication and Status Pages on Cloudflare Workers

**Date:** 2026-08-22
**Author:** example.com
**Status:** published

## Symptom

An incident resolves in 22 minutes but users do not know anything happened
until they file support tickets. The engineering team has no status page, or
has one hosted on the same infrastructure that goes down during incidents,
making it unreachable when users need it most. Mobile users discover the
outage through app crashes or blank screens with no in-app explanation.
Subscriber emails go out hours after resolution. The status page is a static
HTML file that requires a manual edit and a deployment to update — no engineer
does this during an active incident.

## Context

Incident communication is a first-class engineering product, not an afterthought.
Cloudflare's architecture is uniquely suited to a reliable, low-latency status
page: Cloudflare Pages serves static assets from the edge globally; D1 stores
incident state; Durable Objects provide real-time state synchronization for live
status feeds; Workers handle subscriber management and push notifications.
Because the status page infrastructure is independent of the application Workers
that may be impaired, it remains reachable when the application is down —
solving the "status page hosted on the thing that's broken" anti-pattern.

## Architecture overview

```
┌─────────────────────────────────────────────────────────────────┐
│  Cloudflare Pages                                               │
│  status.example.com — static HTML/JS, served from edge          │
│  Polls: /api/status every 30 s via Workers fetch               │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTP
┌──────────────────────────▼──────────────────────────────────────┐
│  Status API Worker (Cloudflare Worker)                          │
│  GET /api/status         → reads D1 for current incident state  │
│  POST /api/incidents     → creates/updates incident (auth)      │
│  POST /api/subscribe     → adds subscriber email/push token     │
│  GET  /api/feed          → SSE or Durable Object WebSocket      │
└────────┬──────────────────────────────────────┬─────────────────┘
         │ D1 queries                            │ DO stub
┌────────▼───────────┐              ┌────────────▼──────────────┐
│  D1 database       │              │  Durable Object           │
│  incidents table   │              │  StatusBroadcastDO        │
│  components table  │              │  holds WebSocket clients  │
│  subscribers table │              │  broadcasts on update     │
│  audit_log table   │              └───────────────────────────┘
└────────────────────┘
```

## D1 schema for incident state

```sql
-- Incident status: investigating | identified | monitoring | resolved
CREATE TABLE incidents (
  id           TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
  title        TEXT NOT NULL,
  status       TEXT NOT NULL CHECK(status IN
               ('investigating','identified','monitoring','resolved')),
  impact       TEXT NOT NULL CHECK(impact IN ('none','minor','major','critical')),
  created_at   INTEGER NOT NULL DEFAULT (unixepoch('now')),
  updated_at   INTEGER NOT NULL DEFAULT (unixepoch('now')),
  resolved_at  INTEGER
);

CREATE TABLE incident_updates (
  id           TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
  incident_id  TEXT NOT NULL REFERENCES incidents(id),
  body         TEXT NOT NULL,
  status       TEXT NOT NULL,
  created_at   INTEGER NOT NULL DEFAULT (unixepoch('now'))
);

CREATE TABLE components (
  id           TEXT PRIMARY KEY,
  name         TEXT NOT NULL,        -- e.g. "API", "Mobile App", "Auth"
  status       TEXT NOT NULL DEFAULT 'operational'
               CHECK(status IN ('operational','degraded','outage','maintenance'))
);

CREATE TABLE subscribers (
  id           TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
  email        TEXT,
  push_token   TEXT,                 -- FCM or APNs token
  platform     TEXT,                 -- 'ios' | 'android' | 'web'
  active       INTEGER NOT NULL DEFAULT 1,
  created_at   INTEGER NOT NULL DEFAULT (unixepoch('now')),
  UNIQUE(email),
  UNIQUE(push_token)
);

-- Audit log for incident mutations (blameless postmortem support)
CREATE TABLE incident_audit (
  id           TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
  incident_id  TEXT,
  actor        TEXT,                 -- service account or operator email
  action       TEXT,                 -- 'create' | 'update' | 'resolve'
  payload      TEXT,                 -- JSON of the change
  created_at   INTEGER NOT NULL DEFAULT (unixepoch('now'))
);
```

## Status API Worker

```typescript
// src/status-worker.ts
export interface Env {
  DB: D1Database;
  STATUS_DO: DurableObjectNamespace;
  AUTH_SECRET: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/api/status' && request.method === 'GET') {
      return handleGetStatus(env);
    }
    if (url.pathname === '/api/incidents' && request.method === 'POST') {
      return handleCreateIncident(request, env);
    }
    if (url.pathname.startsWith('/api/incidents/') &&
        request.method === 'PATCH') {
      const id = url.pathname.split('/')[3];
      return handleUpdateIncident(request, env, id);
    }
    if (url.pathname === '/api/subscribe' && request.method === 'POST') {
      return handleSubscribe(request, env);
    }
    if (url.pathname === '/api/feed') {
      return handleFeed(request, env);      // Durable Object WebSocket
    }
    return new Response('Not found', { status: 404 });
  }
};

async function handleGetStatus(env: Env): Promise<Response> {
  const [components, incidents] = await Promise.all([
    env.DB.prepare('SELECT * FROM components ORDER BY name ASC').all(),
    env.DB.prepare(`
      SELECT i.*, json_group_array(json_object(
        'body', u.body, 'status', u.status,
        'created_at', u.created_at
      ) ORDER BY u.created_at DESC) AS updates
      FROM incidents i
      LEFT JOIN incident_updates u ON u.incident_id = i.id
      WHERE i.status != 'resolved'
         OR i.resolved_at > unixepoch('now') - 86400
      GROUP BY i.id
      ORDER BY i.created_at DESC
      LIMIT 10
    `).all()
  ]);
  return Response.json(
    { components: components.results, incidents: incidents.results },
    { headers: { 'Cache-Control': 'public, max-age=30' } }
  );
}

function requireAuth(request: Request, env: Env): boolean {
  const auth = request.headers.get('Authorization') ?? '';
  return auth === `Bearer ${env.AUTH_SECRET}`;
}

async function handleCreateIncident(
  request: Request, env: Env
): Promise<Response> {
  if (!requireAuth(request, env)) return new Response('Unauthorized', { status: 401 });
  const body = await request.json<{
    title: string; status: string; impact: string; update?: string;
  }>();
  const id = crypto.randomUUID().slice(0, 16);
  await env.DB.batch([
    env.DB.prepare(
      'INSERT INTO incidents (id,title,status,impact) VALUES (?,?,?,?)'
    ).bind(id, body.title, body.status, body.impact),
    ...(body.update ? [env.DB.prepare(
      'INSERT INTO incident_updates (incident_id,body,status) VALUES (?,?,?)'
    ).bind(id, body.update, body.status)] : []),
    env.DB.prepare(
      'INSERT INTO incident_audit (incident_id,actor,action,payload) VALUES (?,?,?,?)'
    ).bind(id, 'system', 'create', JSON.stringify(body))
  ]);
  await broadcastUpdate(env, id);
  await notifySubscribers(env, body.title, body.status);
  return Response.json({ id }, { status: 201 });
}

async function broadcastUpdate(env: Env, incidentId: string): Promise<void> {
  const doId = env.STATUS_DO.idFromName('global');
  const stub = env.STATUS_DO.get(doId);
  await stub.fetch('https://internal/broadcast', {
    method: 'POST',
    body: JSON.stringify({ incidentId }),
    headers: { 'Content-Type': 'application/json' }
  });
}
```

## Durable Object for real-time updates

```typescript
// src/status-do.ts
export class StatusBroadcastDO {
  private sessions: Set<WebSocket> = new Set();
  private state: DurableObjectState;

  constructor(state: DurableObjectState) {
    this.state = state;
    this.state.getWebSockets().forEach(ws => this.sessions.add(ws));
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/feed') {
      const [client, server] = Object.values(new WebSocketPair());
      this.state.acceptWebSocket(server);
      this.sessions.add(server);
      return new Response(null, { status: 101, webSocket: client });
    }

    if (url.pathname === '/broadcast' && request.method === 'POST') {
      const data = await request.json();
      const msg = JSON.stringify({ type: 'incident_update', ...data });
      for (const ws of this.sessions) {
        try { ws.send(msg); } catch { this.sessions.delete(ws); }
      }
      return new Response('ok');
    }
    return new Response('Not found', { status: 404 });
  }

  webSocketClose(ws: WebSocket): void {
    this.sessions.delete(ws);
  }
}
```

## Mobile push notifications on incident

When an incident is created or updated, send push notifications to
mobile subscribers via FCM (Android) and APNs (iOS):

```typescript
// src/notify.ts
async function notifySubscribers(
  env: Env,
  title: string,
  status: string
): Promise<void> {
  const subscribers = await env.DB.prepare(
    'SELECT push_token, platform FROM subscribers WHERE active = 1 AND push_token IS NOT NULL'
  ).all();

  const message = `[${status.toUpperCase()}] ${title}`;

  await Promise.allSettled(
    subscribers.results.map(async (sub) => {
      if (sub.platform === 'android') {
        await sendFCM(sub.push_token as string, message, env);
      } else if (sub.platform === 'ios') {
        await sendAPNs(sub.push_token as string, message, env);
      }
    })
  );
}

async function sendFCM(
  token: string, message: string, env: Env
): Promise<void> {
  await fetch('https://fcm.googleapis.com/v1/projects/example project/messages:send', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${env.FCM_ACCESS_TOKEN}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      message: {
        token,
        notification: { title: 'example project Status', body: message }
      }
    })
  });
}
```

**APNs note:** APNs requires an HTTP/2 connection and a device-specific
JWT. Use a Workers-compatible APNs library or proxy through a Firebase
Admin SDK endpoint to avoid HTTP/2 limitations in Workers.

## Subscriber management

Subscribers opt in via a form on the status page or through the mobile
app settings. Unsubscribe via a one-click link in notification emails:

```typescript
async function handleSubscribe(
  request: Request, env: Env
): Promise<Response> {
  const body = await request.json<{
    email?: string; push_token?: string; platform?: string;
  }>();
  if (!body.email && !body.push_token) {
    return Response.json(
      { error: 'email or push_token required' }, { status: 400 }
    );
  }
  await env.DB.prepare(
    `INSERT INTO subscribers (email, push_token, platform)
     VALUES (?, ?, ?)
     ON CONFLICT(email) DO UPDATE SET active = 1
     ON CONFLICT(push_token) DO UPDATE SET active = 1`
  ).bind(body.email ?? null, body.push_token ?? null, body.platform ?? 'web')
   .run();
  return Response.json({ ok: true }, { status: 201 });
}
```

For unsubscribe, issue a signed token (HMAC of subscriber ID) in the
notification email link. Validate on click and set `active = 0`.

## Mobile client: in-app status banner

The mobile app should poll the status API on app foreground and display
a banner when an active incident exists:

```typescript
// React Native example
async function checkStatus(): Promise<void> {
  try {
    const res = await fetch('https://status.example.com/api/status');
    const data = await res.json();
    const activeIncidents = data.incidents.filter(
      (i: Incident) => i.status !== 'resolved'
    );
    if (activeIncidents.length > 0) {
      showStatusBanner(activeIncidents[0]);
    }
  } catch {
    // Do not show banner on network error — the app handles that separately
  }
}

// Poll on foreground events (AppState change)
AppState.addEventListener('change', (state) => {
  if (state === 'active') checkStatus();
});
```

Banner UX rules for mobile:
- Show a non-blocking banner at the top (not a modal).
- Banner color: yellow for minor/degraded, red for major/critical.
- Tap navigates to `status.example.com` in an in-app browser.
- Dismiss is persistent per incident ID (store dismissed incident IDs
  in AsyncStorage).
- Do not show a resolved banner — only suppress the banner when resolved.

## Anti-patterns

- **Status page hosted on the same domain/infrastructure as the app** —
  if `api.example.com` is down, `status.example.com` must still work.
  Keep them on separate Cloudflare Workers scripts and separate DNS
  records. Ideally, the status page is a Cloudflare Pages site that
  serves static HTML without any Worker dependency for the base page.
- **Manual status page updates during an incident** — an engineer
  updating the status page during an active incident is an engineer not
  working on the incident. Provide a simple authenticated API that can
  be called from a runbook command or a Slack `/status` slash command.
- **Notification email with no unsubscribe link** — CAN-SPAM and GDPR
  require unsubscribe. Every status notification email must include a
  one-click unsubscribe link.
- **Push tokens stored without platform** — FCM and APNs use different
  API endpoints, payloads, and auth methods. Always store `platform`
  alongside the token.
- **Polling interval too short** — a 5-second poll from thousands of
  mobile clients can DDoS your status Worker during an incident when
  traffic is already elevated. Use 30 seconds with `Cache-Control` on
  the status endpoint.

## Gotchas

- **Durable Objects location** — a global-singleton DO (`idFromName('global')`)
  is created in one Cloudflare datacenter. Writes from other datacenters
  have ~50–150ms additional latency. For a status page write (operator
  action), this is acceptable. For read-heavy polling, cache the DO
  response in the Worker for 30 seconds via `ctx.waitUntil` or a KV cache.
- **APNs HTTP/2 in Workers** — Cloudflare Workers support HTTP/1.1 and
  HTTP/2 fetch, but APNs requires HTTP/2 and a client certificate for
  certificate-based auth. Use token-based APNs auth (JWT) to avoid
  certificate complexity. Or proxy via Firebase Cloud Messaging which
  handles APNs internally.
- **FCM token rotation** — FCM tokens expire and rotate. Handle 404
  responses from FCM by deactivating the subscriber row rather than
  retrying.
- **D1 write latency during incident** — D1 writes go to the primary
  region. If an incident originates in that region, D1 writes may be
  slow or fail. Keep the status Worker write path minimal and add a
  fallback to KV for the "is the system currently impaired" boolean.

## Verification

- Status page is hosted on Cloudflare Pages, independent of application
  Workers; it remains reachable when application Workers are down.
- Status API Worker updates D1 and broadcasts to DO WebSocket clients
  within 2 seconds of an operator incident creation.
- Mobile subscribers receive push notifications within 60 seconds of
  incident creation.
- In-app status banner appears on app foreground within one polling cycle
  (≤ 30 seconds) of an active incident.
- Email notifications include a working one-click unsubscribe link.
- FCM 404 responses deactivate subscriber rows rather than retrying.
- Status page cache TTL is 30 seconds; no mobile client polls faster
  than that.

## Related

- `documentation/docs/policies/lessons/public-status-needs-an-independent-failure-domain.md`
- `documentation/docs/policies/lessons/incident-communication-stakeholder-updates.md`
- `documentation/docs/policies/lessons/postmortem-culture-blameless-cloudflare.md`
- `documentation/docs/policies/lessons/audit-logs-are-append-only.md`
- `documentation/docs/policies/lessons/mobile-first-means-api-first.md`
- `documentation/docs/policies/lessons/webhook-delivery-is-not-guaranteed.md`

## Source URLs (verified 2026-08-22)

- Cloudflare Durable Objects — https://developers.cloudflare.com/durable-objects/
- Cloudflare D1 HTTP API — https://developers.cloudflare.com/d1/platform/client-api/
- Cloudflare Pages documentation — https://developers.cloudflare.com/pages/
- Firebase Cloud Messaging HTTP v1 API — https://firebase.google.com/docs/cloud-messaging/send-message
- Atlassian status page best practices — https://www.atlassian.com/incident-management/kpis/status-page
