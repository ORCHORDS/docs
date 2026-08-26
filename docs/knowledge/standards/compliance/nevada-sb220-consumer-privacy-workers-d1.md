# Nevada SB 220 / SB 260 Consumer Privacy — Cloudflare Workers + D1

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your service collects personal information from Nevada residents and you need to:

- Honor opt-out-of-sale requests within **60 days** (SB 220, 2019) or **60 days** (SB 260, 2021 expansion).
- Stop selling covered information to data brokers after a verified opt-out.
- Maintain a designated opt-out email address or web form.
- Avoid "sale" of information collected from children under 13 at all times.

---

## Context

Nevada's SB 220 (effective 1 Oct 2019) amended NRS Chapter 603A to add an opt-out-of-sale right distinct from CCPA. SB 260 (2021) expanded "sale" to include data brokers and introduced a consumer request portal requirement. Key differences from CCPA/CPRA:

- **No private right of action** — enforcement is by the Nevada AG only.
- **Sale** means exchange for monetary consideration only (no "valuable consideration" expansion).
- **Covered information** maps to NRS 603A.320 categories (name, address, SSN, email, phone, DOB, financial account numbers, medical info, passport number).
- Operators must designate an email address **or** web form for opt-out requests.
- Response window: **60 calendar days**, extendable by 30 days with notice.

---

## 1. Opt-Out Request Intake Worker

```typescript
// workers/nevada-optout.ts
export interface Env {
  DB: D1Database;
  OPTOUT_SECRET: string;
}

interface OptOutRequest {
  email: string;
  name?: string;
  requestedAt?: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }
    const body = await request.json<OptOutRequest>();
    if (!body.email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(body.email)) {
      return new Response(JSON.stringify({ error: "valid email required" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
    }

    const deadline = new Date();
    deadline.setDate(deadline.getDate() + 60); // NRS 603A — 60-day response window

    await env.DB.prepare(
      `INSERT OR REPLACE INTO nevada_optouts
         (email, name, requested_at, deadline_at, status)
       VALUES (?, ?, datetime('now'), ?, 'pending')`
    )
      .bind(body.email.toLowerCase(), body.name ?? null, deadline.toISOString())
      .run();

    return new Response(
      JSON.stringify({
        message: "Opt-out request received. We will process it within 60 days.",
        deadline: deadline.toISOString(),
      }),
      { status: 202, headers: { "Content-Type": "application/json" } }
    );
  },
};
```

---

## 2. D1 Schema for Opt-Out Registry

```sql
-- migrations/0001_nevada_optouts.sql
CREATE TABLE IF NOT EXISTS nevada_optouts (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  email       TEXT    NOT NULL UNIQUE,
  name        TEXT,
  requested_at TEXT   NOT NULL DEFAULT (datetime('now')),
  deadline_at  TEXT   NOT NULL,
  processed_at TEXT,
  status      TEXT    NOT NULL DEFAULT 'pending'
    CHECK(status IN ('pending','processing','completed','rejected')),
  rejection_reason TEXT,
  extension_notice_sent_at TEXT  -- if 30-day extension was invoked
);

CREATE INDEX idx_nevada_optouts_status ON nevada_optouts(status);
CREATE INDEX idx_nevada_optouts_deadline ON nevada_optouts(deadline_at);
```

---

## 3. Sale-Suppression Check in Data Pipeline

```typescript
// lib/nevada-sale-check.ts
export async function isNevadaOptedOut(
  email: string,
  db: D1Database
): Promise<boolean> {
  const result = await db
    .prepare(
      `SELECT 1 FROM nevada_optouts
       WHERE email = ? AND status = 'completed'
       LIMIT 1`
    )
    .bind(email.toLowerCase())
    .first<{ 1: number }>();
  return result !== null;
}

// Usage in data export / monetization pipeline:
export async function enrichUserForPartner(
  userId: string,
  db: D1Database
): Promise<object | null> {
  const user = await db
    .prepare("SELECT email, profile FROM users WHERE id = ?")
    .bind(userId)
    .first<{ email: string; profile: string }>();
  if (!user) return null;

  if (await isNevadaOptedOut(user.email, db)) {
    // Log suppression event for compliance audit trail
    await db
      .prepare(
        `INSERT INTO sale_suppression_log (email, suppressed_at, reason)
         VALUES (?, datetime('now'), 'nevada_sb220_optout')`
      )
      .bind(user.email)
      .run();
    return null; // do not pass to partner
  }
  return JSON.parse(user.profile);
}
```

---

## 4. Deadline-Approaching Alert (Cron Trigger)

```typescript
// workers/nevada-deadline-alert.ts — scheduled: "0 8 * * *"
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const twoDaysOut = new Date();
    twoDaysOut.setDate(twoDaysOut.getDate() + 2);

    const { results } = await env.DB.prepare(
      `SELECT id, email, deadline_at FROM nevada_optouts
       WHERE status = 'pending'
         AND deadline_at <= ?
       ORDER BY deadline_at ASC`
    )
      .bind(twoDaysOut.toISOString())
      .all<{ id: number; email: string; deadline_at: string }>();

    for (const row of results) {
      console.log(
        `[NEVADA-SB220] URGENT: opt-out ${row.email} deadline ${row.deadline_at}`
      );
      // integrate with PagerDuty / Slack webhook as needed
    }
  },
};
```

---

## 5. Opt-Out Completion and Audit Record

```typescript
// workers/nevada-optout-complete.ts
export async function completeOptOut(
  email: string,
  db: D1Database
): Promise<void> {
  const { success } = await db
    .prepare(
      `UPDATE nevada_optouts
       SET status = 'completed', processed_at = datetime('now')
       WHERE email = ? AND status IN ('pending','processing')`
    )
    .bind(email.toLowerCase())
    .run();

  if (!success) throw new Error(`No pending opt-out found for ${email}`);

  // Immutable audit entry
  await db
    .prepare(
      `INSERT INTO compliance_audit_log
         (event_type, subject_email, occurred_at, law_reference)
       VALUES ('nevada_optout_completed', ?, datetime('now'), 'NRS 603A.340')`
    )
    .bind(email.toLowerCase())
    .run();
}
```

---

## Anti-patterns

- **Ignoring sale to data brokers**: SB 260 extended "sale" beyond advertisers — any paid data transfer is covered.
- **Using CCPA as Nevada substitute**: Nevada has no "sensitive data" category or cure period — treat it separately.
- **Failing to suppress on sub-processors**: Opt-out must propagate to every downstream partner that monetizes the data.
- **Processing email opt-outs manually**: Automate intake and suppression; the 60-day clock starts at receipt, not when staff reads the email.

---

## Gotchas

- **No CCPA alignment required**: Nevada "sale" excludes non-monetary valuable consideration; a data swap may not be a "sale" under Nevada law but still falls under CCPA.
- **Extension requires written notice**: If you invoke the 30-day extension you must notify the consumer in writing before the original 60-day deadline expires.
- **Children under 13**: No sale whatsoever permitted, regardless of opt-out status.
- **Designated email is legally required**: Posting only a web form without an email address does not satisfy SB 220.

---

## Verification

```bash
# Check pending opt-outs approaching deadline
wrangler d1 execute DB --command \
  "SELECT email, deadline_at,
     CAST((julianday(deadline_at) - julianday('now')) AS INTEGER) AS days_remaining
   FROM nevada_optouts WHERE status='pending' ORDER BY deadline_at ASC;"

# Confirm suppression log is populated
wrangler d1 execute DB --command \
  "SELECT COUNT(*) AS suppressed FROM sale_suppression_log WHERE reason='nevada_sb220_optout';"
```

---

## Related

- `ccpa-opt-out.md` — California opt-out-of-sale (broader "valuable consideration" definition)
- `data-retention-automated-deletion-workers.md` — Automated PII lifecycle
- `audit-log-mandatory.md` — Immutable audit logging patterns
- `us-state-privacy-laws-2026-multi-state-compliance.md` — Multi-state opt-out routing

---

## Sources

- Nevada SB 220 (2019): https://www.leg.state.nv.us/Session/80th2019/Bills/SB/SB220_EN.pdf
- Nevada SB 260 (2021): https://www.leg.state.nv.us/Session/81st2021/Bills/SB/SB260_EN.pdf
- NRS Chapter 603A: https://www.leg.state.nv.us/NRS/NRS-603A.html
- Nevada AG guidance: https://ag.nv.gov/Privacy/Privacy_Home/
