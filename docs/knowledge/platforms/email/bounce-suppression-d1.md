# Bounce Handling and Suppression List Management with Cloudflare D1

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

Sending email to addresses that have previously bounced or marked your message as spam degrades IP and domain reputation rapidly. ESP accounts can be suspended when complaint rates exceed 0.1% (Google/Yahoo threshold) or when hard-bounce rates stay above 5%. A suppression list—maintained in a queryable, durable store—prevents re-sending to addresses known to be problematic.

Cloudflare **D1** (the serverless SQLite edge database) is the right fit: it is co-located with Workers, supports full SQL queries for list management, and scales to millions of rows without provisioning overhead.

---

## Context

Bounces come in two classes:

| Class | Cause | Action |
|-------|-------|--------|
| **Hard bounce** | Address does not exist (550, 551, 553) | Suppress permanently |
| **Soft bounce** | Mailbox full, server unavailable (421, 450, 452) | Retry with backoff; suppress after N consecutive failures |

Spam complaints arrive via **Feedback Loops (FBL)**—ISPs send an Abuse Reporting Format (ARF) message to the email address listed in the `List-Unsubscribe` header, or via a dedicated FBL signup. ESPs (SendGrid, Resend, Postmark) surface both bounce events and complaint events as webhook payloads that a Worker can process synchronously.

---

## Section 1: D1 Schema

```sql
-- migrations/0001_suppression.sql
CREATE TABLE IF NOT EXISTS suppression (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  email       TEXT    NOT NULL,
  domain      TEXT    NOT NULL GENERATED ALWAYS AS (
                LOWER(SUBSTR(email, INSTR(email, '@') + 1))
              ) STORED,
  reason      TEXT    NOT NULL CHECK (reason IN (
                'hard_bounce', 'soft_bounce', 'complaint', 'manual', 'unsubscribe'
              )),
  source      TEXT    NOT NULL,    -- 'sendgrid', 'resend', 'postmark', 'manual'
  suppressed_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  raw_event   TEXT,               -- JSON blob of original webhook payload
  expires_at  TEXT                -- NULL = permanent; ISO-8601 for temporary
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_suppression_email
  ON suppression (LOWER(email));

CREATE INDEX IF NOT EXISTS idx_suppression_domain
  ON suppression (domain);

CREATE INDEX IF NOT EXISTS idx_suppression_reason
  ON suppression (reason);

-- Soft-bounce tracking: count consecutive failures per address
CREATE TABLE IF NOT EXISTS bounce_streak (
  email         TEXT PRIMARY KEY,
  streak        INTEGER NOT NULL DEFAULT 1,
  last_bounced_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
```

Apply with:

```bash
wrangler d1 execute email-db --file=migrations/0001_suppression.sql
```

---

## Section 2: Wrangler Configuration

```toml
# wrangler.toml
name = "email-suppression-worker"
main = "src/index.ts"
compatibility_date = "2026-01-01"

[[d1_databases]]
binding = "DB"
database_name = "email-db"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[vars]
SOFT_BOUNCE_THRESHOLD = "3"     # suppress after 3 consecutive soft bounces
WEBHOOK_SECRET = ""              # set via wrangler secret put WEBHOOK_SECRET
```

---

## Section 3: Bounce Event Ingestion Worker

The Worker receives webhook POSTs from your ESP, normalizes the event, and writes to D1.

```typescript
// src/index.ts
import type { D1Database, ExecutionContext } from "@cloudflare/workers-types";

export interface Env {
  DB: D1Database;
  WEBHOOK_SECRET: string;
  SOFT_BOUNCE_THRESHOLD: string;
}

// ---- Type definitions ----

interface BounceEvent {
  email: string;
  type: "hard_bounce" | "soft_bounce" | "complaint";
  source: string;
  rawPayload: unknown;
}

// ---- SendGrid adapter ----

function parseSendGridWebhook(body: unknown[]): BounceEvent[] {
  return body.flatMap((event: any) => {
    if (event.event === "bounce") {
      const isSoft = event.type === "blocked" || event.status?.startsWith("4");
      return [{
        email: event.email.toLowerCase(),
        type: isSoft ? "soft_bounce" : "hard_bounce",
        source: "sendgrid",
        rawPayload: event,
      }];
    }
    if (event.event === "spamreport") {
      return [{
        email: event.email.toLowerCase(),
        type: "complaint",
        source: "sendgrid",
        rawPayload: event,
      }];
    }
    return [];
  });
}

// ---- Resend adapter ----

function parseResendWebhook(body: any): BounceEvent[] {
  const { type, data } = body;
  if (type === "email.bounced") {
    return [{
      email: data.to[0].toLowerCase(),
      type: data.bounce?.type === "Permanent" ? "hard_bounce" : "soft_bounce",
      source: "resend",
      rawPayload: body,
    }];
  }
  if (type === "email.complained") {
    return [{
      email: data.to[0].toLowerCase(),
      type: "complaint",
      source: "resend",
      rawPayload: body,
    }];
  }
  return [];
}

// ---- Suppression logic ----

async function handleBounceEvents(events: BounceEvent[], env: Env): Promise<void> {
  const threshold = parseInt(env.SOFT_BOUNCE_THRESHOLD, 10);

  for (const evt of events) {
    if (evt.type === "hard_bounce" || evt.type === "complaint") {
      // Upsert into suppression immediately
      await env.DB.prepare(`
        INSERT INTO suppression (email, reason, source, raw_event)
        VALUES (LOWER(?1), ?2, ?3, ?4)
        ON CONFLICT (LOWER(email)) DO UPDATE SET
          reason        = excluded.reason,
          source        = excluded.source,
          raw_event     = excluded.raw_event,
          suppressed_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
      `)
        .bind(evt.email, evt.type, evt.source, JSON.stringify(evt.rawPayload))
        .run();
    } else {
      // Soft bounce — increment streak
      const result = await env.DB.prepare(`
        INSERT INTO bounce_streak (email, streak, last_bounced_at)
        VALUES (LOWER(?1), 1, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        ON CONFLICT (email) DO UPDATE SET
          streak          = bounce_streak.streak + 1,
          last_bounced_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
        RETURNING streak
      `)
        .bind(evt.email)
        .first<{ streak: number }>();

      if (result && result.streak >= threshold) {
        await env.DB.prepare(`
          INSERT INTO suppression (email, reason, source, raw_event)
          VALUES (LOWER(?1), 'soft_bounce', ?2, ?3)
          ON CONFLICT (LOWER(email)) DO NOTHING
        `)
          .bind(evt.email, evt.source, JSON.stringify(evt.rawPayload))
          .run();
      }
    }
  }
}

// ---- Request handler ----

export default {
  async fetch(request: Request, env: Env, _ctx: ExecutionContext): Promise<Response> {
    if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

    // Validate shared secret (Resend, Mailgun) or HMAC (SendGrid)
    const secret = <redacted-secret>"X-Webhook-Secret") ?? "";
    if (secret !== env.WEBHOOK_SECRET) {
      return new Response("Unauthorized", { status: 401 });
    }

    const url = new URL(request.url);
    const body = await request.json();

    let events: BounceEvent[] = [];
    if (url.pathname === "/webhooks/sendgrid") {
      events = parseSendGridWebhook(body as unknown[]);
    } else if (url.pathname === "/webhooks/resend") {
      events = parseResendWebhook(body);
    } else {
      return new Response("Unknown webhook source", { status: 400 });
    }

    await handleBounceEvents(events, env);
    return new Response("OK", { status: 200 });
  },
};
```

---

## Section 4: Pre-Send Suppression Check

Before queuing any outbound email, check D1 for suppression. This should be called from your send pipeline or API layer.

```typescript
// src/suppression-check.ts
import type { D1Database } from "@cloudflare/workers-types";

interface SuppressionRecord {
  email: string;
  reason: string;
  suppressed_at: string;
}

export async function isSuppressed(
  email: string,
  db: D1Database
): Promise<SuppressionRecord | null> {
  const row = await db
    .prepare(`
      SELECT email, reason, suppressed_at
      FROM suppression
      WHERE LOWER(email) = LOWER(?1)
        AND (expires_at IS NULL OR expires_at > strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
    `)
    .bind(email)
    .first<SuppressionRecord>();

  return row ?? null;
}

// Batch variant — efficient for bulk campaigns
export async function filterSuppressed(
  emails: string[],
  db: D1Database
): Promise<string[]> {
  if (emails.length === 0) return [];

  const placeholders = emails.map((_, i) => `LOWER(?${i + 1})`).join(", ");
  const rows = await db
    .prepare(`
      SELECT LOWER(email) AS email
      FROM suppression
      WHERE LOWER(email) IN (${placeholders})
        AND (expires_at IS NULL OR expires_at > strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
    `)
    .bind(...emails.map((e) => e.toLowerCase()))
    .all<{ email: string }>();

  const suppressed = new Set(rows.results.map((r) => r.email));
  return emails.filter((e) => !suppressed.has(e.toLowerCase()));
}
```

---

## Section 5: Suppression List Management API

Expose endpoints for manual list management (customer support tools, admin dashboards).

```typescript
// src/admin-api.ts
import type { D1Database } from "@cloudflare/workers-types";

export async function addManualSuppression(
  email: string,
  reason: "manual" | "unsubscribe",
  db: D1Database
): Promise<void> {
  await db
    .prepare(`
      INSERT INTO suppression (email, reason, source)
      VALUES (LOWER(?1), ?2, 'manual')
      ON CONFLICT (LOWER(email)) DO UPDATE SET
        reason = excluded.reason,
        suppressed_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
    `)
    .bind(email, reason)
    .run();
}

export async function removeSuppression(
  email: string,
  db: D1Database
): Promise<boolean> {
  const result = await db
    .prepare(`DELETE FROM suppression WHERE LOWER(email) = LOWER(?1)`)
    .bind(email)
    .run();

  // Also clear soft-bounce streak on re-activation
  await db
    .prepare(`DELETE FROM bounce_streak WHERE email = LOWER(?1)`)
    .bind(email)
    .run();

  return (result.meta.changes ?? 0) > 0;
}

export async function listSuppressions(
  db: D1Database,
  options: { limit?: number; offset?: number; reason?: string } = {}
): Promise<{ results: unknown[]; total: number }> {
  const { limit = 100, offset = 0, reason } = options;

  const whereClause = reason ? `WHERE reason = ?3` : "";
  const bindings: (string | number)[] = [limit, offset];
  if (reason) bindings.push(reason);

  const [rows, count] = await Promise.all([
    db
      .prepare(`
        SELECT email, reason, source, suppressed_at
        FROM suppression
        ${whereClause}
        ORDER BY suppressed_at DESC
        LIMIT ?1 OFFSET ?2
      `)
      .bind(...bindings)
      .all(),
    db
      .prepare(`SELECT COUNT(*) AS total FROM suppression ${whereClause}`)
      .bind(...(reason ? [reason] : []))
      .first<{ total: number }>(),
  ]);

  return { results: rows.results, total: count?.total ?? 0 };
}
```

---

## Section 6: Suppression Metrics and Alerting

Surface suppression rate per campaign via a daily D1 query, pushed to a monitoring endpoint.

```typescript
// src/metrics.ts
import type { D1Database } from "@cloudflare/workers-types";

export async function getSuppressionStats(db: D1Database) {
  const stats = await db
    .prepare(`
      SELECT
        reason,
        COUNT(*) AS count,
        DATE(suppressed_at) AS date
      FROM suppression
      WHERE suppressed_at >= DATE('now', '-30 days')
      GROUP BY reason, DATE(suppressed_at)
      ORDER BY date DESC, count DESC
    `)
    .all();

  return stats.results;
}
```

---

## Anti-Patterns

- **Checking suppression after queuing** — the email is already queued by the time you check. The suppression check must happen synchronously before any queue insert or ESP API call.
- **Storing email in mixed case** — `User@Example.com` and `user@example.com` are the same address. Always normalize to lowercase before insert and lookup; the schema uses `LOWER(email)` in the unique index but the application layer should also normalize.
- **Deleting suppression records on unsubscribe request** — do not delete; update the `reason` column to `'unsubscribe'`. Deletion loses the audit trail and may violate GDPR record-keeping requirements.
- **Not resetting the soft-bounce streak on a successful delivery** — a streak that never resets will suppress valid but temporarily unreachable addresses. Call `DELETE FROM bounce_streak WHERE email = ?` after a confirmed delivery.
- **Using D1 for real-time lookups in hot loops** — D1 read latency is ~1-3 ms from a nearby PoP; in a tight loop sending thousands of emails per second, this adds up. Cache the suppression result in Worker memory or KV for the duration of a batch job.

---

## Gotchas

- **D1 `ON CONFLICT` syntax** — D1 (SQLite) uses `ON CONFLICT (column) DO UPDATE`, not `ON DUPLICATE KEY UPDATE` (MySQL). The column in the conflict target must match an index.
- **`RETURNING` clause** — available in SQLite 3.35+ and D1's compatibility layer. If the `RETURNING` clause silently fails, fall back to a follow-up `SELECT` for the streak value.
- **D1 row size limit** — individual rows are limited to 1 MB. The `raw_event` BLOB should be truncated or summarized if the ESP payload is unusually large.
- **Webhook replay / idempotency** — ESPs may deliver the same bounce event more than once. The `ON CONFLICT DO NOTHING` / `DO UPDATE` approach makes the handler idempotent.
- **GDPR right to erasure** — suppression records may be subject to deletion requests. A `is_pseudonymized` column or hashed email (SHA-256) can satisfy erasure while retaining the statistical record.

---

## Verification

```bash
# Check schema was applied
wrangler d1 execute email-db --command="SELECT name FROM sqlite_master WHERE type='table';"

# Manual suppression insert
wrangler d1 execute email-db \
  --command="INSERT INTO suppression (email, reason, source) VALUES ('test@example.com', 'manual', 'manual');"

# Confirm suppression check
wrangler d1 execute email-db \
  --command="SELECT * FROM suppression WHERE email = 'test@example.com';"

# Simulate soft bounce threshold
wrangler d1 execute email-db \
  --command="INSERT INTO bounce_streak (email, streak) VALUES ('soft@example.com', 3) ON CONFLICT (email) DO UPDATE SET streak = 3;"

# Verify suppression list endpoint
curl -X GET https://email-suppression-worker.example.workers.dev/admin/suppressions \
  -H "Authorization: Bearer <admin-token>"
```

---

## Related

- `bounce-handling-hard-soft.md` — classification of bounce types
- `bounce-classification-list-hygiene.md` — list hygiene after bounce events
- `suppression-list-management.md` — general suppression list patterns
- `email-webhook-idempotency-deduplication.md` — idempotent webhook processing
- `email-feedback-loop-setup.md` — FBL registration with ISPs

---

## Sources

- [Cloudflare D1 documentation](https://developers.cloudflare.com/d1/)
- [SendGrid Event Webhooks — bounce types](https://docs.sendgrid.com/for-developers/tracking-events/event#bounce)
- [Resend Webhooks — email.bounced](https://resend.com/docs/dashboard/webhooks/event-types)
- [RFC 5965 — An Extensible Format for Email Feedback Reports (ARF)](https://datatracker.ietf.org/doc/html/rfc5965)
- [Google Postmaster Tools — Spam Rate guidelines](https://postmaster.google.com/u/0/guidelines)
- [Yahoo Postmaster — Complaint rate limits](https://senders.yahooinc.com/best-practices/)
