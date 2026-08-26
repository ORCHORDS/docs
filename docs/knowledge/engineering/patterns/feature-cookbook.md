# feature-cookbook

**Issue:** Common feature recipes — search, notifications, file upload
**Date:** 2026-08-09
**Status:** documented

## Search

For a simple text search (10k-100k records), use SQLite's
FTS5:
```sql
-- Create FTS5 virtual table
CREATE VIRTUAL TABLE users_fts USING fts5(
  display_name,
  email,
  content='users',
  content_rowid='rowid'
);

-- Trigger to keep FTS in sync
CREATE TRIGGER users_fts_insert AFTER INSERT ON users BEGIN
  INSERT INTO users_fts(rowid, display_name, email) VALUES (new.rowid, new.display_name, new.email);
END;
CREATE TRIGGER users_fts_delete AFTER DELETE ON users BEGIN
  INSERT INTO users_fts(users_fts, rowid, display_name, email) VALUES('delete', old.rowid, old.display_name, old.email);
END;

-- Search
SELECT u.* FROM users u
JOIN users_fts f ON u.rowid = f.rowid
WHERE users_fts MATCH 'alice' AND u.tenant_id = ?;
```

For larger search (1M+ records), use Algolia or Meilisearch.

## Notifications

For in-app notifications, a simple D1 table:
```sql
CREATE TABLE notifications (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  type TEXT NOT NULL,  -- 'comment', 'like', 'follow', etc.
  resource_id TEXT,
  read_at TEXT,  -- ISO 8601
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_notif_user_unread ON notifications(user_id, read_at);
```

```ts
async function createNotification(input: NotificationInput, env: Env): Promise<Notification> {
  const id = crypto.randomUUID();
  await env.DB!.prepare(
    `INSERT INTO notifications (id, user_id, type, resource_id) VALUES (?, ?, ?, ?)`
  ).bind(id, input.userId, input.type, input.resourceId).run();
  return { id, ...input };
}

async function getUnreadCount(userId: string, env: Env): Promise<number> {
  const result = await env.DB!.prepare(
    `SELECT COUNT(*) AS count FROM notifications WHERE user_id = ? AND read_at IS NULL`
  ).bind(userId).first<{ count: number }>();
  return result?.count ?? 0;
}

async function markAsRead(id: string, userId: string, env: Env): Promise<void> {
  await env.DB!.prepare(
    `UPDATE notifications SET read_at = ? WHERE id = ? AND user_id = ? AND read_at IS NULL`
  ).bind(new Date().toISOString(), id, userId).run();
}
```

For push notifications, integrate with Apple Push Notification
service (APNS) and Firebase Cloud Messaging (FCM).

## File upload

For direct-to-R2 upload, use a presigned URL:
```ts
// 1. Server generates a presigned URL
async function getUploadUrl(filename: string, env: Env): Promise<{ url: string; key: string }> {
  const key = `uploads/${crypto.randomUUID()}/${filename}`;
  const url = await env.R2!.createPresignedUrl({
    method: 'PUT',
    key,
    expiration: 600,  // 10 min
  });
  return { url, key };
}

// 2. Client uploads directly to R2
const { url, key } = await fetch('/api/uploads/presign', { method: 'POST' }).then(r => r.json());
await fetch(url, { method: 'PUT', body: file });

// 3. Server records the upload
await fetch('/api/uploads', { method: 'POST', body: JSON.stringify({ key }) });
```

For images, integrate with Cloudflare Images for resizing +
WebP conversion.

## Email

For transactional email, use a vendor (SendGrid, Postmark,
Resend, AWS SES):
```ts
async function sendEmail(input: EmailInput, env: Env): Promise<void> {
  const response = await fetch('https://api.resend.com/emails', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${env.RESEND_API_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      from: 'noreply@example.com',
      to: input.to,
      subject: input.subject,
      html: input.html,
    }),
  });

  if (!response.ok) {
    throw new Error(`Email send failed: ${response.status}`);
  }
}
```

For internationalization, use a templating engine that
supports i18n (Handlebars, MJML).

## Internationalization

For 20 locales, use i18next:
```ts
import i18next from 'i18next';

await i18next.init({
  resources: {
    en: { translation: enMessages },
    es: { translation: esMessages },
    // ...
  },
  lng: ctx.user.preferredLanguage ?? 'en',
  fallbackLng: 'en',
});

const greeting = i18next.t('greeting', { name: 'Alice' });
```

For full ICU MessageFormat, use `@formatjs/intl`.

## Background jobs

For long-running work, use CF Queues:
```ts
// 1. Producer
async function enqueueJob(env: Env, job: JobInput): Promise<void> {
  await env.QUEUE.send(job);
}

// 2. Consumer
export async function handleQueue(batch: MessageBatch<JobInput>, env: Env, ctx: ExecutionContext): Promise<void> {
  for (const message of batch.messages) {
    try {
      await processJob(message.body, env);
      message.ack();
    } catch (err) {
      message.retry({ delaySeconds: 60 });  // Retry in 1 min
    }
  }
}
```

## Real-time

For real-time updates, use Server-Sent Events (SSE):
```ts
// Server
export async function handleSSE(request: Request, env: Env): Promise<Response> {
  const stream = new ReadableStream({
    start(controller) {
      const interval = setInterval(() => {
        controller.enqueue(`data: ${Date.now()}\n\n`);
      }, 1000);

      request.signal.addEventListener('abort', () => {
        clearInterval(interval);
        controller.close();
      });
    },
  });

  return new Response(stream, {
    headers: {
      'content-type': 'text/event-stream',
      'cache-control': 'no-cache',
      'connection': 'keep-alive',
    },
  });
}
```

For two-way real-time, use WebSockets.

## Rate limiting

For per-IP rate limiting, use CF's rate limiting rules + a
DO for per-user:
```ts
async function checkRateLimit(userId: string, env: Env): Promise<{ allowed: boolean; remaining: number }> {
  const id = env.RATE_LIMIT.idFromName(userId);
  const stub = env.RATE_LIMIT.get(id);
  const response = await stub.fetch('https://rate/check');
  return response.json();
}
```

The DO counts requests; the handler checks the count.

## Geolocation

CF Workers has built-in geolocation:
```ts
export default {
  async fetch(request: Request, env: Env, ctx: McContext) {
    const country = request.cf?.country;
    const city = request.cf?.city;
    const ip = request.headers.get('cf-connecting-ip');
    // ... use these
  },
};
```

For user-set location, store in D1.

## Password reset

```ts
// 1. Request
async function requestPasswordReset(email: string, env: Env): Promise<void> {
  const user = await env.DB!.prepare(`SELECT id FROM users WHERE email = ?`).bind(email).first<User>();
  if (!user) return;  // Don't reveal whether the user exists

  const token = crypto.randomUUID();
  const expiresAt = new Date(Date.now() + 60 * 60 * 1000);  // 1 hour

  await env.DB!.prepare(
    `INSERT INTO password_resets (token, user_id, expires_at) VALUES (?, ?, ?)`
  ).bind(token, user.id, expiresAt.toISOString()).run();

  await sendEmail(email, `Click to reset: https://example.com/auth/reset?token=${token}`);
}

// 2. Reset
async function resetPassword(token: string, newPassword: string, env: Env): Promise<void> {
  const row = await env.DB!.prepare(
    `SELECT user_id, expires_at FROM password_resets WHERE token = ? AND used_at IS NULL`
  ).bind(token).first<{ user_id: string; expires_at: string }>();

  if (!row || new Date(row.expires_at) < new Date()) {
    throw new Error('Invalid or expired token');
  }

  const hashed = await hashPassword(newPassword);
  await env.DB!.prepare(`UPDATE users SET password_hash = ? WHERE id = ?`).bind(hashed, row.user_id).run();
  await env.DB!.prepare(`UPDATE password_resets SET used_at = ? WHERE token = ?`).bind(new Date().toISOString(), token).run();
}
```

## Two-factor authentication

For TOTP (RFC 6238), use a library like `otplib`:
```ts
import { authenticator } from 'otplib';

const secret = <redacted-secret>
const uri = authenticator.keyuri(user.email, 'MyApp', secret);

// User scans the QR code, enters the code
const isValid = authenticator.verify({ token: code, secret });
```

Store the secret encrypted in the user record. Provide
backup codes (8 random 6-digit codes, hashed).

## Verification
- **Test:** Each feature has unit + integration tests
- **Live:** Feature usage is monitored
- **Audit:** Quarterly feature review

## Gotchas
- **Each feature is a chance for a security bug.** Search
  (injection), email (SPF/DKIM), upload (size limits), 2FA
  (rate limiting on attempts).
- **Each feature has a UX.** Push notifications need
  permission. File upload needs progress. Email needs
  unsubscribe.
- **Each feature has a cost.** Email costs per send. SMS is
  per message. Search is per query. Storage is per GB.
- **Each feature is a chance for a failure mode.** Plan for
  the vendor being down.

## Related
- `search-architecture.md`
- `observability-three-pillars.md`
- `rate-limiting-strategies.md`
- `webauthn-passkey-flow.md`
- `authentication-flows-comparison.md`
- `i18n/icu-messageformat-advanced.md`
