# Mobile Push vs Email Preference Management D1 Schema

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

Users receive duplicate notifications via both push and email for the same event because the notification layer lacks a unified preference store. Teams rebuild preference logic per channel in ad-hoc tables, causing drift when new notification types are added. A consolidated D1 schema that models email and mobile push preferences together eliminates this duplication and makes per-channel, per-topic opt-in/out trivially queryable from any Worker.

## Context

Cloudflare D1 is a serverless SQLite-compatible database accessible from Workers at the edge. Because it supports relational schemas with foreign keys, it is well-suited for modelling the many-to-many relationship between a user, a notification topic (e.g. `order_shipped`), and a delivery channel (email, iOS push, Android FCM). The preference resolution logic runs in a Worker on every notification event, fetching the user's opted-in channels before routing the payload to the correct sink (SendGrid for email, FCM/APNs for push). GDPR and CASL require the schema to record explicit consent evidence — timestamp, source IP, and consent version — alongside each preference row.

## Schema Design

### Core Tables

```sql
-- migrations/0001_notification_preferences.sql

CREATE TABLE IF NOT EXISTS users (
  id          TEXT PRIMARY KEY,          -- UUID v7
  email       TEXT NOT NULL UNIQUE,
  created_at  INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE IF NOT EXISTS notification_topics (
  id           TEXT PRIMARY KEY,         -- e.g. 'order_shipped'
  label        TEXT NOT NULL,
  category     TEXT NOT NULL,            -- 'transactional' | 'marketing' | 'account'
  default_email  INTEGER NOT NULL DEFAULT 1,  -- 1 = opted-in by default
  default_push   INTEGER NOT NULL DEFAULT 1,
  created_at   INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE IF NOT EXISTS notification_channels (
  id    TEXT PRIMARY KEY   -- 'email' | 'ios_push' | 'android_fcm' | 'web_push'
);

INSERT OR IGNORE INTO notification_channels (id) VALUES
  ('email'), ('ios_push'), ('android_fcm'), ('web_push');

-- One row per (user, topic, channel) — absent row = use topic default
CREATE TABLE IF NOT EXISTS user_preferences (
  user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  topic_id     TEXT NOT NULL REFERENCES notification_topics(id) ON DELETE CASCADE,
  channel_id   TEXT NOT NULL REFERENCES notification_channels(id),
  opted_in     INTEGER NOT NULL,         -- 0 or 1
  consent_src  TEXT,                     -- 'preference_center' | 'checkout' | 'import'
  consent_ip   TEXT,
  consent_ver  TEXT,                     -- consent policy version slug
  updated_at   INTEGER NOT NULL DEFAULT (unixepoch()),
  PRIMARY KEY (user_id, topic_id, channel_id)
);

CREATE INDEX idx_pref_user ON user_preferences (user_id);
CREATE INDEX idx_pref_topic ON user_preferences (topic_id, channel_id);

-- Push device tokens (one user may have many devices)
CREATE TABLE IF NOT EXISTS push_tokens (
  id          TEXT PRIMARY KEY,
  user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  channel_id  TEXT NOT NULL,             -- 'ios_push' | 'android_fcm' | 'web_push'
  token       TEXT NOT NULL,
  device_name TEXT,
  active      INTEGER NOT NULL DEFAULT 1,
  registered_at INTEGER NOT NULL DEFAULT (unixepoch()),
  UNIQUE (channel_id, token)
);

CREATE INDEX idx_token_user ON push_tokens (user_id, channel_id, active);
```

### Seeding Default Topics

```sql
INSERT OR IGNORE INTO notification_topics (id, label, category, default_email, default_push) VALUES
  ('order_placed',      'Order confirmation',      'transactional', 1, 1),
  ('order_shipped',     'Shipping update',          'transactional', 1, 1),
  ('order_delivered',   'Delivery confirmation',    'transactional', 1, 0),
  ('password_reset',    'Password reset',           'account',       1, 0),
  ('promo_weekly',      'Weekly deals',             'marketing',     0, 0),
  ('promo_flash',       'Flash sale alert',         'marketing',     0, 1),
  ('digest_daily',      'Daily digest',             'marketing',     0, 0);
```

## Worker — Preference Resolution

```typescript
// src/preferences.ts
export interface Env {
  DB: D1Database;
}

export interface ChannelDecision {
  email:       boolean;
  ios_push:    boolean;
  android_fcm: boolean;
  web_push:    boolean;
}

/**
 * Resolve which channels a user wants for a given topic.
 * Falls back to topic defaults when no explicit preference row exists.
 */
export async function resolveChannels(
  db: D1Database,
  userId: string,
  topicId: string
): Promise<ChannelDecision> {
  const topicRow = await db
    .prepare('SELECT default_email, default_push FROM notification_topics WHERE id = ?')
    .bind(topicId)
    .first<{ default_email: number; default_push: number }>();

  if (!topicRow) throw new Error(`Unknown topic: ${topicId}`);

  // Fetch all explicit prefs for this user+topic in one query
  const prefs = await db
    .prepare(
      'SELECT channel_id, opted_in FROM user_preferences WHERE user_id = ? AND topic_id = ?'
    )
    .bind(userId, topicId)
    .all<{ channel_id: string; opted_in: number }>();

  const map: Record<string, boolean> = {};
  for (const row of prefs.results) {
    map[row.channel_id] = row.opted_in === 1;
  }

  const emailDefault = topicRow.default_email === 1;
  const pushDefault  = topicRow.default_push  === 1;

  return {
    email:       map['email']       ?? emailDefault,
    ios_push:    map['ios_push']    ?? pushDefault,
    android_fcm: map['android_fcm'] ?? pushDefault,
    web_push:    map['web_push']    ?? pushDefault,
  };
}

/**
 * Upsert an explicit preference with consent evidence.
 */
export async function setPreference(
  db: D1Database,
  userId: string,
  topicId: string,
  channelId: string,
  optedIn: boolean,
  meta: { src: string; ip: string; ver: string }
): Promise<void> {
  await db
    .prepare(`
      INSERT INTO user_preferences
        (user_id, topic_id, channel_id, opted_in, consent_src, consent_ip, consent_ver, updated_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, unixepoch())
      ON CONFLICT (user_id, topic_id, channel_id) DO UPDATE SET
        opted_in    = excluded.opted_in,
        consent_src = excluded.consent_src,
        consent_ip  = excluded.consent_ip,
        consent_ver = excluded.consent_ver,
        updated_at  = excluded.updated_at
    `)
    .bind(userId, topicId, channelId, optedIn ? 1 : 0, meta.src, meta.ip, meta.ver)
    .run();
}
```

## Worker — Notification Dispatch

```typescript
// src/dispatch.ts
import { resolveChannels } from './preferences';

interface NotificationPayload {
  userId:  string;
  topic:   string;
  title:   string;
  body:    string;
  data?:   Record<string, string>;
}

export async function dispatch(
  env: Env,
  payload: NotificationPayload
): Promise<void> {
  const channels = await resolveChannels(env.DB, payload.userId, payload.topic);

  // Fetch user email and active push tokens in parallel
  const [userRow, pushTokens] = await Promise.all([
    channels.email
      ? env.DB.prepare('SELECT email FROM users WHERE id = ?').bind(payload.userId)
          .first<{ email: string }>()
      : Promise.resolve(null),
    (channels.ios_push || channels.android_fcm || channels.web_push)
      ? env.DB.prepare(
          `SELECT channel_id, token FROM push_tokens
           WHERE user_id = ? AND active = 1`
        ).bind(payload.userId).all<{ channel_id: string; token: string }>()
      : Promise.resolve({ results: [] }),
  ]);

  const tasks: Promise<void>[] = [];

  if (channels.email && userRow) {
    tasks.push(sendEmail(env, userRow.email, payload));
  }

  for (const pt of pushTokens.results) {
    if (!channels[pt.channel_id as keyof typeof channels]) continue;
    tasks.push(sendPush(env, pt.channel_id, pt.token, payload));
  }

  await Promise.allSettled(tasks);
}

async function sendEmail(env: Env, to: string, p: NotificationPayload): Promise<void> {
  // Mobile-first email: short subject, preheader matches body
  const res = await fetch('https://api.sendgrid.com/v3/mail/send', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.SENDGRID_API_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      personalizations: [{ to: [{ email: to }] }],
      from: { email: env.FROM_EMAIL },
      subject: p.title,          // ≤ 50 chars for mobile preview
      content: [
        { type: 'text/plain', value: p.body },
        { type: 'text/html',  value: mobileSafeHtml(p.title, p.body) },
      ],
    }),
  });
  if (!res.ok) throw new Error(`SendGrid ${res.status}`);
}

async function sendPush(
  _env: Env,
  channel: string,
  token: string,
  p: NotificationPayload
): Promise<void> {
  // Stub — replace with FCM v1 API or APNs HTTP/2 call
  console.log(`[${channel}] push → ${token.slice(0, 8)}… "${p.title}"`);
}

function mobileSafeHtml(title: string, body: string): string {
  // Single-column, 600px max, 16px font for mobile readability
  return `<!DOCTYPE html>
<html><head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{margin:0;padding:0;background:#f5f5f5;font-family:Arial,sans-serif}
.wrap{max-width:600px;margin:0 auto;background:#ffffff;padding:24px 16px}
h1{font-size:20px;color:#111;margin:0 0 12px}
p{font-size:16px;line-height:1.5;color:#333;margin:0}
</style></head>
<body><div class="wrap">
<h1>${title}</h1><p>${body}</p>
</div></body></html>`;
}
```

## Mobile vs Desktop Email Rendering Considerations

- **Subject line length**: iOS Mail clips at ~35 characters in notification shade; Android Gmail clips at ~30. Keep subjects under 30 chars for push-adjacent contexts.
- **Single-column layout**: Mobile clients (Gmail app, Apple Mail iOS) render 600 px fluid columns as full-width. Avoid multi-column designs that break on small screens.
- **Tap target size**: CTA buttons must be at least 44 × 44 px (Apple HIG); use `padding: 14px 24px` on anchor tags rather than `<button>` elements (Outlook ignores button styles).
- **System fonts stack**: `font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif` renders system fonts on iOS and Android, avoiding webfont loading failures in email clients.
- **Dark mode**: add `@media (prefers-color-scheme: dark)` within `<style>` and `[data-ogsc]` selectors for Outlook mobile's dark mode compatibility.

## Preference Center API Design

```typescript
// GET /api/preferences — return full matrix for authenticated user
// PATCH /api/preferences — update one (topic, channel) tuple

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    const userId = req.headers.get('X-User-Id') ?? '';   // set by auth middleware

    if (req.method === 'GET' && url.pathname === '/api/preferences') {
      const rows = await env.DB.prepare(`
        SELECT nt.id as topic_id, nt.label, nt.category,
               nt.default_email, nt.default_push,
               up.channel_id, up.opted_in
        FROM notification_topics nt
        LEFT JOIN user_preferences up
          ON up.topic_id = nt.id AND up.user_id = ?
        ORDER BY nt.category, nt.id
      `).bind(userId).all();
      return Response.json(rows.results);
    }

    if (req.method === 'PATCH' && url.pathname === '/api/preferences') {
      const { topicId, channelId, optedIn } = await req.json<{
        topicId: string; channelId: string; optedIn: boolean;
      }>();
      const ip  = req.headers.get('CF-Connecting-IP') ?? '';
      await setPreference(env.DB, userId, topicId, channelId, optedIn,
        { src: 'preference_center', ip, ver: 'v2026-08' });
      return new Response(null, { status: 204 });
    }

    return new Response('Not found', { status: 404 });
  },
};
```

## Anti-patterns

- **Single boolean per user per topic**: loses channel granularity; a user may want push but not email for the same event.
- **Storing preferences in KV only**: KV has no relational constraints and cannot enforce referential integrity between topics and channels.
- **Defaulting all marketing to opted-in**: violates GDPR legitimate-interest rules for marketing communications; always default marketing to opted-out.
- **Mixing transactional and marketing in a single opt-out flag**: GDPR requires granular consent; transactional opt-outs may also block password-reset emails.
- **Not recording consent metadata**: without `consent_src`, `consent_ip`, and `consent_ver` you cannot demonstrate lawful basis under GDPR Art. 7(1) during a supervisory authority audit.

## Gotchas

- D1 SQLite does not enforce `FOREIGN KEY` constraints without `PRAGMA foreign_keys = ON`. Cloudflare enables this automatically in D1 but confirm with a test insert of a non-existent `user_id`.
- `unixepoch()` in SQLite returns UTC epoch seconds as INTEGER; compare with `Date.now() / 1000` in Worker code — do not mix milliseconds and seconds.
- Absent preference rows mean "use topic default". If you delete a topic and re-create it with a different default, existing users who never explicitly set a preference silently inherit the new default. Bump `consent_ver` and show the preference center on next login.
- FCM tokens expire when a user reinstalls the app; mark them `active = 0` on FCM `UNREGISTERED` or `INVALID_REGISTRATION` error responses rather than deleting (for audit trail).

## Verification

```bash
# Check D1 schema is applied
npx wrangler d1 execute DB --command \
  "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"

# Confirm default resolution (no explicit pref row)
npx wrangler d1 execute DB --command \
  "SELECT * FROM user_preferences WHERE user_id='test-user-1';"

# Simulate preference upsert
curl -X PATCH https://your-worker.workers.dev/api/preferences \
  -H 'X-User-Id: test-user-1' \
  -H 'Content-Type: application/json' \
  -d '{"topicId":"promo_flash","channelId":"email","optedIn":false}'
```

## Related

- `email-preference-center.md`
- `gdpr-email-consent.md`
- `one-click-unsubscribe-rfc8058-gdpr.md`
- `transactional-email-rate-limiting-workers.md`
- `cloudflare-email-routing-workers.md`

## Sources

- Cloudflare D1 documentation — https://developers.cloudflare.com/d1/
- GDPR Article 7 — Conditions for consent
- Apple Human Interface Guidelines — Touch target size (44 × 44 pt)
- FCM registration token management — https://firebase.google.com/docs/cloud-messaging/manage-tokens
