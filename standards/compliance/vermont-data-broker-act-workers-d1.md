# Vermont Data Broker Act (9 V.S.A. § 2430) — Cloudflare Workers + D1

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your platform acquires, sells, or trades personal information about Vermont residents without a direct relationship with those individuals. You need to:

- **Annually register** with the Vermont Secretary of State as a data broker by **31 January** each year.
- Track opt-out-of-sale requests and honor them within **45 days**.
- Implement a security program that meets the 9 V.S.A. § 2447 minimum standard.
- Maintain records of data broker activity for regulatory inspection.

---

## Context

Vermont's Act 171 (2018) — codified at 9 V.S.A. §§ 2430–2447 — was the first US state data broker registration law. Key obligations:

- **Who must register**: Any business that knowingly collects and sells or licenses brokered personal data of Vermont residents and does not have a direct relationship with the subject.
- **Annual fee**: $100 per year, due by 31 January.
- **Disclosure requirements**: Register must state number of records, opt-out mechanisms, security incidents in prior year.
- **Security program**: Written information security policy covering administrative, technical, and physical safeguards proportional to the size and scope of data.
- **Opt-out mechanism**: Must be provided; honor requests within **45 days**.
- **Child data prohibition**: Cannot sell data on minors without affirmative opt-in from a parent.

---

## 1. D1 Schema — Data Broker Registry

```sql
-- migrations/0001_vermont_data_broker.sql

-- Annual registration snapshot (one row per year)
CREATE TABLE IF NOT EXISTS vt_registration (
  year              INTEGER PRIMARY KEY,
  registered_at     TEXT NOT NULL,
  record_count      INTEGER NOT NULL,   -- approx # VT resident records held
  opt_out_url       TEXT NOT NULL,
  security_incident_count INTEGER NOT NULL DEFAULT 0,
  filing_ref        TEXT               -- Secretary of State confirmation #
);

-- Consumer opt-out requests
CREATE TABLE IF NOT EXISTS vt_optout_requests (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  email         TEXT    NOT NULL,
  full_name     TEXT,
  requested_at  TEXT    NOT NULL DEFAULT (datetime('now')),
  deadline_at   TEXT    NOT NULL,      -- +45 days from requested_at
  completed_at  TEXT,
  status        TEXT    NOT NULL DEFAULT 'pending'
    CHECK(status IN ('pending','completed','rejected')),
  rejection_reason TEXT
);

CREATE INDEX idx_vt_optout_status ON vt_optout_requests(status, deadline_at);

-- Immutable audit log for all brokered-data transactions
CREATE TABLE IF NOT EXISTS vt_broker_audit (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  event_type      TEXT NOT NULL,
  subject_email   TEXT,
  data_recipient  TEXT,
  occurred_at     TEXT NOT NULL DEFAULT (datetime('now')),
  suppressed      INTEGER NOT NULL DEFAULT 0,  -- 1 = sale blocked by opt-out
  notes           TEXT
);
```

---

## 2. Opt-Out Intake Worker

```typescript
// workers/vt-optout.ts
export interface Env {
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    const { email, full_name } = await request.json<{
      email: string;
      full_name?: string;
    }>();

    if (!email) {
      return new Response(JSON.stringify({ error: "email required" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
    }

    const deadline = new Date();
    deadline.setDate(deadline.getDate() + 45); // 9 V.S.A. § 2430 — 45-day window

    await env.DB.prepare(
      `INSERT OR REPLACE INTO vt_optout_requests
         (email, full_name, requested_at, deadline_at, status)
       VALUES (?, ?, datetime('now'), ?, 'pending')`
    )
      .bind(email.toLowerCase(), full_name ?? null, deadline.toISOString())
      .run();

    return new Response(
      JSON.stringify({
        message:
          "Vermont data broker opt-out received. Your request will be honored within 45 days.",
        deadline: deadline.toISOString(),
      }),
      { status: 202, headers: { "Content-Type": "application/json" } }
    );
  },
};
```

---

## 3. Sale-Suppression Guard

```typescript
// lib/vt-sale-guard.ts
export async function checkVermontOptOut(
  email: string,
  db: D1Database
): Promise<boolean> {
  const row = await db
    .prepare(
      `SELECT 1 FROM vt_optout_requests
       WHERE email = ? AND status = 'completed'
       LIMIT 1`
    )
    .bind(email.toLowerCase())
    .first<{ 1: number }>();
  return row !== null;
}

export async function recordBrokerTransaction(
  subjectEmail: string,
  recipient: string,
  suppressed: boolean,
  db: D1Database
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO vt_broker_audit
         (event_type, subject_email, data_recipient, suppressed, occurred_at)
       VALUES ('data_sale', ?, ?, ?, datetime('now'))`
    )
    .bind(subjectEmail.toLowerCase(), recipient, suppressed ? 1 : 0)
    .run();
}

export async function sellOrSuppressBrokeredRecord(
  subjectEmail: string,
  recipient: string,
  payload: object,
  db: D1Database
): Promise<{ sent: boolean; reason?: string }> {
  // Check child data prohibition first — handled upstream by DOB check
  const optedOut = await checkVermontOptOut(subjectEmail, db);
  if (optedOut) {
    await recordBrokerTransaction(subjectEmail, recipient, true, db);
    return { sent: false, reason: "vermont_optout" };
  }
  // ... forward payload to recipient
  await recordBrokerTransaction(subjectEmail, recipient, false, db);
  return { sent: true };
}
```

---

## 4. Annual Registration Reminder (Cron Trigger)

```typescript
// workers/vt-registration-reminder.ts — scheduled: "0 9 1 12 *" (1 Dec each year)
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const nextYear = new Date().getFullYear() + 1;

    // Count approximate Vermont resident records
    const { results } = await env.DB.prepare(
      `SELECT COUNT(*) AS cnt FROM users WHERE state = 'VT'`
    ).all<{ cnt: number }>();
    const recordCount = results[0]?.cnt ?? 0;

    // Count security incidents in past year
    const { results: incidents } = await env.DB.prepare(
      `SELECT COUNT(*) AS cnt FROM security_incidents
       WHERE occurred_at >= date('now', '-1 year')`
    ).all<{ cnt: number }>();
    const incidentCount = incidents[0]?.cnt ?? 0;

    console.log(
      `[VT-BROKER] Annual registration due 31 Jan ${nextYear}. ` +
        `~${recordCount} VT records. ${incidentCount} incidents to disclose.`
    );
    // Trigger Slack/email alert to compliance team
  },
};
```

---

## 5. Security Program Minimum Controls Checklist Worker

```typescript
// workers/vt-security-check.ts — returns 200 if all controls pass
const REQUIRED_CONTROLS = [
  "encryption_at_rest",
  "encryption_in_transit",
  "access_control_mfa",
  "incident_response_plan",
  "employee_training_annual",
  "vendor_agreements_signed",
] as const;

type Control = (typeof REQUIRED_CONTROLS)[number];

export async function getSecurityProgramStatus(
  db: D1Database
): Promise<Record<Control, boolean>> {
  const { results } = await db
    .prepare(
      `SELECT control_name, passed FROM security_controls
       WHERE control_name IN (${REQUIRED_CONTROLS.map(() => "?").join(",")})
         AND assessed_at >= date('now', '-1 year')`
    )
    .bind(...REQUIRED_CONTROLS)
    .all<{ control_name: Control; passed: number }>();

  const status = Object.fromEntries(
    REQUIRED_CONTROLS.map((c) => [c, false])
  ) as Record<Control, boolean>;
  for (const row of results) {
    status[row.control_name] = row.passed === 1;
  }
  return status;
}
```

---

## Anti-patterns

- **Assuming CCPA opt-out covers Vermont**: Vermont has a separate 45-day window (vs. CCPA's 15 business days) and different scope — maintain distinct tracking.
- **Failing to register because "we're not a data broker"**: If you aggregate third-party data and license it, you almost certainly qualify — review the definition broadly.
- **Missing the 31 January deadline**: Vermont AG has publicly named non-registered brokers; $50/day penalties accrue.
- **Treating child opt-in as opt-out**: Minors require affirmative **parental opt-in** — not just honoring an opt-out request.

---

## Gotchas

- **Annual registration is public**: The Vermont AG publishes the list of registered brokers and any security incidents they disclose — factor this into incident disclosure decisions.
- **Security incident disclosure on registration**: Incidents from the prior calendar year must be disclosed on the annual form, even if under active litigation.
- **No private right of action**: Enforcement is AG-only, but AG has been active; $10,000 per violation cap.
- **"Direct relationship" exception is narrow**: A one-time transactional relationship does not qualify; the exemption requires an ongoing, primary relationship with the individual.

---

## Verification

```bash
# Pending opt-outs within 5 days of deadline
wrangler d1 execute DB --command \
  "SELECT email, deadline_at,
     CAST((julianday(deadline_at) - julianday('now')) AS INTEGER) AS days_left
   FROM vt_optout_requests WHERE status='pending'
   ORDER BY deadline_at ASC LIMIT 20;"

# Annual registration readiness — approximate VT record count
wrangler d1 execute DB --command \
  "SELECT COUNT(*) AS vt_residents FROM users WHERE state='VT';"

# Verify suppression is working
wrangler d1 execute DB --command \
  "SELECT suppressed, COUNT(*) FROM vt_broker_audit GROUP BY suppressed;"
```

---

## Related

- `nevada-sb220-consumer-privacy-workers-d1.md` — Nevada opt-out-of-sale
- `ccpa-data-broker-registration.md` — California data broker requirements
- `data-minimization-workers-d1-pii-redaction.md` — Reduce brokered data footprint
- `audit-log-mandatory.md` — Immutable broker transaction logging

---

## Sources

- Vermont Act 171 (2018): https://legislature.vermont.gov/Documents/2018/Docs/ACTS/ACT171/ACT171%20As%20Enacted.pdf
- 9 V.S.A. § 2430: https://legislature.vermont.gov/statutes/section/09/062/02430
- Vermont AG Data Broker Registry: https://ago.vermont.gov/data-brokers
- Vermont AG enforcement actions: https://ago.vermont.gov/press-releases
