# Scheduled Email Digest Generation and Sending with Workers + D1 + MailChannels

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

You need to send periodic digest emails (daily or weekly) to users summarising recent activity — new content, updates, or aggregated metrics — without running a traditional server-side cron job. Users must be able to set their own frequency preference and unsubscribe from digests independently of the main email list.

## Context

Cloudflare Workers Cron Triggers fire a `scheduled` event on a fixed cron schedule. Combined with D1 (SQLite at the edge) for storing digest state and user preferences, and MailChannels for transactional delivery, you can build a fully serverless digest pipeline. The pattern tracks the last digest sent per user so frequency preferences (daily vs. weekly) are honoured even when the cron fires more frequently than some users need.

## Solution

### D1 Schema

```sql
-- migrations/0001_digest.sql
CREATE TABLE IF NOT EXISTS digest_preferences (
  user_id       TEXT PRIMARY KEY,
  email         TEXT NOT NULL,
  frequency     TEXT NOT NULL DEFAULT 'weekly', -- 'daily' | 'weekly' | 'none'
  last_sent_at  INTEGER,                         -- Unix epoch seconds
  unsubscribed  INTEGER NOT NULL DEFAULT 0,      -- boolean
  created_at    INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE IF NOT EXISTS digest_items (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id     TEXT NOT NULL,
  title       TEXT NOT NULL,
  url         TEXT NOT NULL,
  summary     TEXT,
  category    TEXT,
  created_at  INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_items_user_created
  ON digest_items (user_id, created_at DESC);
```

### Worker – Digest Scheduler

```typescript
// src/digest-scheduler.ts
import { Env } from './types';

const DAY_S  = 86_400;
const WEEK_S = 7 * DAY_S;

export default {
  // Cron: "0 8 * * *" — fires every day at 08:00 UTC
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext) {
    ctx.waitUntil(runDigestCycle(env));
  },

  // Manual trigger for testing
  async fetch(req: Request, env: Env): Promise<Response> {
    if (new URL(req.url).pathname === '/trigger-digest') {
      await runDigestCycle(env);
      return new Response('Digest cycle complete', { status: 200 });
    }
    return new Response('Not found', { status: 404 });
  },
};

async function runDigestCycle(env: Env): Promise<void> {
  const now = Math.floor(Date.now() / 1000);

  // Fetch users who are due for a digest
  const { results: users } = await env.DB.prepare(`
    SELECT user_id, email, frequency, last_sent_at
    FROM   digest_preferences
    WHERE  unsubscribed = 0
      AND  frequency   != 'none'
  `).all<DigestPreference>();

  for (const user of users) {
    const intervalS = user.frequency === 'daily' ? DAY_S : WEEK_S;
    const lastSent  = user.last_sent_at ?? 0;

    if (now - lastSent < intervalS) continue; // not yet due

    const since = lastSent || now - intervalS;
    const items = await fetchDigestItems(env, user.user_id, since);

    if (items.length === 0) continue; // nothing to send

    await sendDigestEmail(env, user, items, now);

    await env.DB.prepare(`
      UPDATE digest_preferences
      SET    last_sent_at = ?
      WHERE  user_id      = ?
    `).bind(now, user.user_id).run();
  }
}

async function fetchDigestItems(
  env: Env,
  userId: string,
  since: number
): Promise<DigestItem[]> {
  const { results } = await env.DB.prepare(`
    SELECT title, url, summary, category, created_at
    FROM   digest_items
    WHERE  user_id    = ?
      AND  created_at > ?
    ORDER  BY created_at DESC
    LIMIT  50
  `).bind(userId, since).all<DigestItem>();

  return results;
}

function buildDigestHtml(user: DigestPreference, items: DigestItem[]): string {
  const grouped = groupByCategory(items);
  const sections = Object.entries(grouped)
    .map(([cat, catItems]) => `
      <h2 style="color:#1a1a2e">${escapeHtml(cat)}</h2>
      <ul>
        ${catItems.map(i => `
          <li>
            <a >${escapeHtml(i.title)}</a>
            ${i.summary ? `<p style="color:#555;margin:4px 0">${escapeHtml(i.summary)}</p>` : ''}
          </li>
        `).join('')}
      </ul>
    `).join('');

  const unsubUrl = `https://app.example.com/unsubscribe-digest?uid=${user.user_id}`;

  return `<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Your ${user.frequency} digest</title></head>
<body style="font-family:sans-serif;max-width:600px;margin:auto;padding:24px">
  <h1>Your ${user.frequency} digest</h1>
  ${sections}
  <hr style="margin-top:40px">
  <p style="font-size:12px;color:#999">
    You are receiving this because you opted in to ${user.frequency} digests.
    <a >Unsubscribe from digests</a>
  </p>
</body></html>`;
}

async function sendDigestEmail(
  env: Env,
  user: DigestPreference,
  items: DigestItem[],
  now: number
): Promise<void> {
  const html    = buildDigestHtml(user, items);
  const subject = `Your ${user.frequency} digest — ${new Date(now * 1000).toDateString()}`;

  const payload = {
    personalizations: [{ to: [{ email: user.email }] }],
    from: { email: 'digest@example.com', name: 'Orchords Digest' },
    subject,
    content: [{ type: 'text/html', value: html }],
  };

  const res = await fetch('https://api.mailchannels.net/tx/v1/send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    throw new Error(`MailChannels error ${res.status}: ${await res.text()}`);
  }
}

// Unsubscribe endpoint (separate Worker route)
export async function handleUnsubscribeDigest(
  req: Request,
  env: Env
): Promise<Response> {
  const url    = new URL(req.url);
  const userId = url.searchParams.get('uid');

  if (!userId) return new Response('Missing uid', { status: 400 });

  await env.DB.prepare(`
    UPDATE digest_preferences
    SET    unsubscribed = 1
    WHERE  user_id = ?
  `).bind(userId).run();

  return new Response(
    '<h1>You have been unsubscribed from digests.</h1>',
    { headers: { 'Content-Type': 'text/html' } }
  );
}

// Helpers
function groupByCategory(items: DigestItem[]): Record<string, DigestItem[]> {
  return items.reduce((acc, item) => {
    const cat = item.category ?? 'General';
    (acc[cat] ??= []).push(item);
    return acc;
  }, {} as Record<string, DigestItem[]>);
}

function escapeHtml(s: string): string {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// Types
interface DigestPreference {
  user_id:      string;
  email:        string;
  frequency:    'daily' | 'weekly';
  last_sent_at: number | null;
}

interface DigestItem {
  title:      string;
  url:        string;
  summary:    string | null;
  category:   string | null;
  created_at: number;
}
```

### wrangler.toml

```toml
[[d1_databases]]
binding  = "DB"
database_name = "digest-db"
database_id   = "<your-d1-id>"

[triggers]
crons = ["0 8 * * *"]
```

## Implementation Details

- **Frequency gating** is done at query time by comparing `last_sent_at` against the current epoch minus the user's interval. This means the daily cron covers both daily and weekly users; weekly users are simply skipped until 7 days have elapsed.
- **Empty digest suppression**: if a user has zero new items since their last send, the loop `continue`s and does not update `last_sent_at`, so the next run will check the same window again.
- **`ctx.waitUntil`** ensures the async digest cycle completes even after the scheduled event handler returns.
- **Batch limit of 50 items** per digest prevents oversized emails. Add pagination or a summary-only mode for high-volume users.
- Items are inserted by your application layer via a standard D1 insert whenever activity occurs; the digest Worker only reads.

## Anti-patterns

- Do not run the digest send loop synchronously inside the `scheduled` handler without `waitUntil` — the Worker will terminate before all emails are sent.
- Do not track `last_sent_at` in KV for this use-case; D1 gives you transactional updates and avoids double-send races.
- Do not hardcode the `since` window as `now - WEEK_S` for everyone; always derive it from the per-user `last_sent_at`.
- Do not skip the empty-items check — sending an empty digest erodes trust and increases unsubscribe rates.

## Gotchas

- MailChannels requires DKIM to be configured on your sending domain; without it, deliverability is poor. See `documentation/docs/policies/email/mailchannels-dkim-workers.md`.
- Cloudflare Cron Triggers have a minimum granularity of 1 minute; for digest use-cases daily or hourly is typical.
- D1 `unixepoch()` returns seconds; `Date.now()` returns milliseconds — always divide by 1000 when inserting from TypeScript.
- The `scheduled` event does not have an inbound `Request`, so you cannot read headers. Use KV or D1 for all shared state.

## Verification

```bash
# 1. Apply the migration
npx wrangler d1 execute digest-db --file=migrations/0001_digest.sql

# 2. Seed a test user
npx wrangler d1 execute digest-db \
  --command "INSERT INTO digest_preferences (user_id, email, frequency) VALUES ('u1','test@example.com','daily')"

# 3. Seed a test item
npx wrangler d1 execute digest-db \
  --command "INSERT INTO digest_items (user_id, title, url, summary, category) VALUES ('u1','Hello World','https://example.com','Test item','News')"

# 4. Trigger the digest manually
curl https://<worker>.workers.dev/trigger-digest

# 5. Confirm last_sent_at was updated
npx wrangler d1 execute digest-db \
  --command "SELECT user_id, last_sent_at FROM digest_preferences"
```

## Related

- `documentation/docs/policies/email/mailchannels-dkim-workers.md`
- `documentation/docs/policies/email/workers-email-suppression-list-kv.md`
- `documentation/docs/policies/email/workers-transactional-email-queue.md`
- `documentation/docs/policies/email/workers-email-template-engine-r2.md`

## Sources

- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://developers.cloudflare.com/d1/
- https://api.mailchannels.net/tx/v1/documentation
