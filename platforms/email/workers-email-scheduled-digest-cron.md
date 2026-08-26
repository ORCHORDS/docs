# Scheduled Email Digest with Cron Workers and D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You accumulate events or notifications in D1 throughout the day and want to send
each user a single batched digest email once per day rather than one email per
event. A Cloudflare Cron Worker queries D1 for unsent items grouped by user,
batches them into a single email per user via MailChannels, and marks rows as
sent atomically.

## Context

Cloudflare Workers support scheduled triggers via `wrangler.toml` cron
expressions. The `scheduled` handler receives a `ScheduledController` instead of
a `Request`. D1 transactions ensure rows are marked sent only after the email is
successfully dispatched, preventing double-sends on retry.

---

## Section 1 – D1 Schema: Digest Queue

```sql
-- migrations/0001_digest_queue.sql

CREATE TABLE IF NOT EXISTS users (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  email   TEXT NOT NULL UNIQUE,
  name    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS digest_items (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id     INTEGER NOT NULL REFERENCES users(id),
  category    TEXT    NOT NULL,   -- e.g. 'new_order', 'comment', 'alert'
  title       TEXT    NOT NULL,
  body        TEXT    NOT NULL,
  created_at  INTEGER NOT NULL DEFAULT (unixepoch()),
  sent_at     INTEGER,            -- NULL = unsent
  digest_run  TEXT                -- ISO date of the cron run that sent it
);

CREATE INDEX idx_digest_items_unsent
  ON digest_items(user_id, sent_at)
  WHERE sent_at IS NULL;
```

---

## Section 2 – Querying Unsent Items Grouped by User

```typescript
// src/lib/digest/query.ts

export interface DigestItem {
  id: number;
  category: string;
  title: string;
  body: string;
  created_at: number;
}

export interface UserDigest {
  userId: number;
  email: string;
  name: string;
  items: DigestItem[];
}

export async function fetchUnsentDigests(db: D1Database): Promise<UserDigest[]> {
  // Fetch all unsent items with their user info, ordered by user then time
  const rows = await db
    .prepare(
      `SELECT
         u.id        AS userId,
         u.email     AS email,
         u.name      AS name,
         d.id        AS itemId,
         d.category  AS category,
         d.title     AS title,
         d.body      AS body,
         d.created_at AS created_at
       FROM digest_items d
       JOIN users u ON u.id = d.user_id
       WHERE d.sent_at IS NULL
       ORDER BY u.id, d.created_at`
    )
    .all<{
      userId: number; email: string; name: string;
      itemId: number; category: string; title: string;
      body: string; created_at: number;
    }>();

  // Group by userId
  const map = new Map<number, UserDigest>();
  for (const row of rows.results) {
    if (!map.has(row.userId)) {
      map.set(row.userId, { userId: row.userId, email: row.email, name: row.name, items: [] });
    }
    map.get(row.userId)!.items.push({
      id: row.itemId,
      category: row.category,
      title: row.title,
      body: row.body,
      created_at: row.created_at,
    });
  }

  return Array.from(map.values());
}
```

---

## Section 3 – Building the Digest Email Body

```typescript
// src/lib/digest/template.ts

import { DigestItem } from './query';

function formatDate(unixSeconds: number): string {
  return new Date(unixSeconds * 1000).toUTCString();
}

export function buildDigestText(name: string, items: DigestItem[]): string {
  const lines = [`Hello ${name},`, '', 'Your daily digest:', ''];
  for (const item of items) {
    lines.push(`[${item.category.toUpperCase()}] ${item.title}`);
    lines.push(item.body);
    lines.push(`Received: ${formatDate(item.created_at)}`);
    lines.push('---');
  }
  lines.push('', 'Have a great day!', 'The Orchords Team');
  return lines.join('\n');
}

export function buildDigestHtml(name: string, items: DigestItem[]): string {
  const itemsHtml = items
    .map(
      (item) => `
    <tr>
      <td style="padding:8px;border-bottom:1px solid #eee;">
        <strong>[${item.category}]</strong> ${escapeHtml(item.title)}
        <br/><span style="color:#555;font-size:0.9em;">${escapeHtml(item.body)}</span>
        <br/><small style="color:#999;">${formatDate(item.created_at)}</small>
      </td>
    </tr>`
    )
    .join('');

  return `<!DOCTYPE html>
<html><body style="font-family:sans-serif;max-width:600px;margin:0 auto;">
  <h2>Hello ${escapeHtml(name)},</h2>
  <p>Your daily digest:</p>
  <table width="100%" style="border-collapse:collapse;">${itemsHtml}</table>
  <p style="color:#999;font-size:0.85em;">You are receiving this because you have an Orchords account.</p>
</body></html>`;
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
```

---

## Section 4 – Sending and Atomically Marking Sent

```typescript
// src/lib/digest/send.ts

import { UserDigest } from './query';
import { buildDigestText, buildDigestHtml } from './template';

export async function sendDigestForUser(
  db: D1Database,
  fromAddress: string,
  digest: UserDigest,
  runDate: string // ISO date string, e.g. '2026-08-24'
): Promise<void> {
  const { email, name, items } = digest;
  const itemIds = items.map((i) => i.id);

  const textBody = buildDigestText(name, items);
  const htmlBody = buildDigestHtml(name, items);

  // Send via MailChannels
  const res = await fetch('https://api.mailchannels.net/tx/v1/send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      personalizations: [{ to: [{ email, name }] }],
      from: { email: fromAddress, name: 'Orchords Digest' },
      subject: `Your Orchords digest for ${runDate}`,
      content: [
        { type: 'text/plain', value: textBody },
        { type: 'text/html', value: htmlBody },
      ],
    }),
  });

  if (!res.ok) {
    throw new Error(`MailChannels error ${res.status} for ${email}: ${await res.text()}`);
  }

  // Mark items as sent atomically using D1 batch
  // D1 does not support dynamic IN(?) bindings, so use a batch
  const nowSeconds = Math.floor(Date.now() / 1000);
  const statements = itemIds.map((id) =>
    db.prepare(
      'UPDATE digest_items SET sent_at = ?, digest_run = ? WHERE id = ? AND sent_at IS NULL'
    ).bind(nowSeconds, runDate, id)
  );

  await db.batch(statements);
}
```

---

## Section 5 – Scheduled Worker Handler

```typescript
// src/index.ts

import { fetchUnsentDigests } from './lib/digest/query';
import { sendDigestForUser } from './lib/digest/send';

export interface Env {
  DB: D1Database;
  FROM_ADDRESS: string;
}

export default {
  async scheduled(_controller: ScheduledController, env: Env, ctx: ExecutionContext): Promise<void> {
    const runDate = new Date().toISOString().slice(0, 10); // 'YYYY-MM-DD'
    console.log(`[digest] Running for ${runDate}`);

    const digests = await fetchUnsentDigests(env.DB);
    console.log(`[digest] Found ${digests.length} users with unsent items`);

    const results = await Promise.allSettled(
      digests.map((digest) =>
        sendDigestForUser(env.DB, env.FROM_ADDRESS, digest, runDate)
      )
    );

    for (const [i, result] of results.entries()) {
      if (result.status === 'rejected') {
        console.error(`[digest] Failed for user ${digests[i].email}: ${result.reason}`);
      } else {
        console.log(`[digest] Sent to ${digests[i].email} (${digests[i].items.length} items)`);
      }
    }
  },

  // Keep a no-op fetch handler so wrangler dev works
  async fetch(_request: Request, _env: Env): Promise<Response> {
    return new Response('Digest worker — use scheduled trigger', { status: 200 });
  },
};
```

```toml
# wrangler.toml
name = "digest-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[triggers]
crons = ["0 8 * * *"]   # Daily at 08:00 UTC

[[d1_databases]]
binding      = "DB"
database_name = "my-db"
database_id   = "YOUR_D1_DATABASE_ID"
```

---

## Anti-patterns

- **SELECT then UPDATE in separate statements without a batch** – a Worker
  timeout between the two leaves rows stuck as unsent forever.
- **Sending one email per item instead of batching per user** – triggers
  rate limits and overwhelms recipients.
- **Using `Promise.all` instead of `Promise.allSettled`** – one failed send
  cancels all remaining users in the batch.
- **Storing only the count, not the item IDs** – makes idempotent mark-sent
  impossible.

## Gotchas

- Cron Workers have a maximum CPU time of 30 seconds per invocation on the free
  plan and 15 minutes on paid plans. For very large user bases, paginate the
  query and use a Queue to fan out.
- `db.batch()` with an empty array throws. Guard with `if (statements.length)`.
- `Promise.allSettled` is always correct here: it waits for all sends before
  exiting the scheduled handler.
- MailChannels does not deduplicate on your behalf. The `sent_at IS NULL`
  guard in the UPDATE is the sole idempotency mechanism — preserve it.
- Cron schedule syntax in `wrangler.toml` uses UTC; convert local business
  hours accordingly.

## Verification

```bash
# Seed test data
wrangler d1 execute MY_DB --command \
  "INSERT INTO users (email, name) VALUES ('alice@example.com', 'Alice');"
wrangler d1 execute MY_DB --command \
  "INSERT INTO digest_items (user_id, category, title, body) VALUES (1, 'alert', 'Low stock', 'Item X is below threshold');"

# Trigger the cron manually via wrangler
wrangler dev --test-scheduled
curl "http://localhost:8787/__scheduled?cron=0+8+*+*+*"

# Verify rows are marked sent
wrangler d1 execute MY_DB --command \
  "SELECT id, title, sent_at, digest_run FROM digest_items;"
```

## Related

- `workers-email-threading-message-id.md`
- `workers-email-multipart-mime-builder.md`
- `workers-email-rate-limit-per-recipient.md`

## Sources

- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://developers.cloudflare.com/d1/
- https://mailchannels.zendesk.com/hc/en-us/articles/4565898358413
- https://developers.cloudflare.com/workers/runtime-apis/scheduled-event/
