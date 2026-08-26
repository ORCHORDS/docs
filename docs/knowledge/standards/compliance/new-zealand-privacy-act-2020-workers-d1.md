# New Zealand Privacy Act 2020 — Compliance via Cloudflare Workers and D1

- Date: 2026-08-22
- Author: example.com
- Status: production

## Problem: Implementing NZ Privacy Act 2020 Obligations for a Global SaaS

New Zealand's Privacy Act 2020 (in force 1 December 2020) modernised the 1993 Act with binding Information Privacy Principles (IPPs), mandatory notifiable breach reporting to the Privacy Commissioner within 72 hours where serious harm is reasonably likely, and statutory damages of up to NZD 10,000 for interference with privacy. The Act has extra-territorial reach: an overseas business that collects personal information from New Zealand individuals in the course of doing business in New Zealand must comply, regardless of where servers are located.

For a cloud SaaS operating on Cloudflare, the key engineering obligations are: (1) IPP 1 — collect only information necessary for a lawful purpose; (2) IPP 5 — store information securely; (3) IPP 6 — provide access on request within 20 working days; (4) IPP 7 — correct inaccurate information; (5) IPP 10 — use information only for the purpose it was collected; (6) IPP 11 — only disclose if an exception applies. The breach reporting obligation (section 113) requires internal assessment of whether harm is "reasonably likely" before a report is made — unlike GDPR's objective risk threshold, this is a harm-focused test considering the nature of the information and the likely adverse effects on individuals.

The architecture uses Workers for the access/correction API endpoints and a scheduled breach-assessment Worker, D1 for the personal data register and breach log, and Queues for the Privacy Commissioner notification pipeline. New Zealand users must be identifiable in the data store so that access requests are scoped accurately.

## Context

- Runtime: Cloudflare Workers (ES modules)
- Database: D1 (personal data register, breach log, access request tracker)
- Queue: Cloudflare Queues (breach notification dispatch)
- Regulation: Privacy Act 2020 (NZ), IPPs 1–13, Sections 113–120 (breach reporting)
- Privacy Commissioner contact: privacy.org.nz

## IPP 6 — Access Request API (20 Working Day SLA)

The access request endpoint accepts authenticated requests and returns all personal information held about the individual across the D1 tables registered in the personal_data_inventory. The Worker calculates the 20-working-day deadline (excluding New Zealand public holidays) and records the request for SLA monitoring.

```ts
// src/handlers/access-request.ts
import { Env } from '../types';

// NZ public holidays 2025-2026 (extend annually)
const NZ_HOLIDAYS = new Set([
  '2026-01-01','2026-01-02','2026-01-26','2026-02-06','2026-04-03',
  '2026-04-06','2026-04-27','2026-06-01','2026-10-26','2026-12-25','2026-12-28',
]);

function addWorkingDays(start: Date, days: number): Date {
  let count = 0;
  const d = new Date(start);
  while (count < days) {
    d.setDate(d.getDate() + 1);
    const iso = d.toISOString().slice(0, 10);
    if (d.getDay() !== 0 && d.getDay() !== 6 && !NZ_HOLIDAYS.has(iso)) count++;
  }
  return d;
}

export async function handleAccessRequest(req: Request, env: Env): Promise<Response> {
  const userId = (req as any).userId as string;
  const now = new Date();
  const deadline = addWorkingDays(now, 20);

  await env.DB.prepare(
    `INSERT INTO access_requests (user_id, requested_at, deadline, status)
     VALUES (?, ?, ?, 'pending')`
  ).bind(userId, now.toISOString(), deadline.toISOString()).run();

  // Collect data across registered tables
  const inventory = await env.DB.prepare(
    `SELECT table_name, pii_columns FROM personal_data_inventory WHERE active = 1`
  ).all<{ table_name: string; pii_columns: string }>();

  const data: Record<string, unknown[]> = {};
  for (const table of inventory.results) {
    const cols = JSON.parse(table.pii_columns) as string[];
    const rows = await env.DB.prepare(
      `SELECT ${cols.join(', ')} FROM "${table.table_name}" WHERE user_id = ?`
    ).bind(userId).all();
    data[table.table_name] = rows.results;
  }

  await env.DB.prepare(
    `UPDATE access_requests SET status='completed', completed_at=? WHERE user_id=? AND status='pending'`
  ).bind(new Date().toISOString(), userId).run();

  return Response.json({
    requestedAt: now.toISOString(),
    deadlineAt: deadline.toISOString(),
    data,
    note: 'Provided under section 44 Privacy Act 2020 (NZ). To correct any information, submit a correction request.',
  });
}
```

## IPP 7 — Correction Request Handler

```ts
// src/handlers/correction-request.ts
interface CorrectionPayload {
  table: string;
  field: string;
  currentValue: string;
  correctedValue: string;
  reason: string;
}

export async function handleCorrectionRequest(req: Request, env: Env): Promise<Response> {
  const userId = (req as any).userId as string;
  const body = await req.json<CorrectionPayload>();

  // Validate field is in the PII inventory for this table
  const inv = await env.DB.prepare(
    `SELECT pii_columns FROM personal_data_inventory WHERE table_name = ? AND active = 1`
  ).bind(body.table).first<{ pii_columns: string }>();
  if (!inv) return new Response('Table not in PII inventory', { status: 400 });

  const allowedCols = JSON.parse(inv.pii_columns) as string[];
  if (!allowedCols.includes(body.field)) {
    return new Response('Field not in PII inventory', { status: 400 });
  }

  const now = new Date().toISOString();
  // Record correction before applying it (immutable audit)
  await env.DB.prepare(
    `INSERT INTO correction_log (user_id, table_name, field, old_value, new_value, reason, requested_at, status)
     VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')`
  ).bind(userId, body.table, body.field, body.currentValue, body.correctedValue, body.reason, now).run();

  // Apply correction
  await env.DB.prepare(
    `UPDATE "${body.table}" SET "${body.field}" = ? WHERE user_id = ?`
  ).bind(body.correctedValue, userId).run();

  await env.DB.prepare(
    `UPDATE correction_log SET status='applied', applied_at=? WHERE user_id=? AND table_name=? AND field=? AND status='pending'`
  ).bind(new Date().toISOString(), userId, body.table, body.field).run();

  return Response.json({ corrected: true, appliedAt: new Date().toISOString() });
}
```

## Section 113 — Notifiable Privacy Breach Assessment

A scheduled Worker runs daily to assess any security events flagged by other Workers. The harm-likelihood assessment uses a matrix: sensitive-data categories (health, financial, identity) combined with breach scope (number of individuals) yields an automatic "serious harm reasonably likely" finding that triggers the Privacy Commissioner notification queue.

```ts
// src/scheduled/breach-assessment.ts
const SENSITIVE_CATEGORIES = new Set(['health','financial','identity','biometric','criminal']);

interface BreachEvent {
  id: number;
  event_type: string;
  data_categories: string;   // JSON array
  affected_count: number;
  detected_at: string;
  assessment_status: string;
}

export async function assessBreaches(env: Env): Promise<void> {
  const pending = await env.DB.prepare(
    `SELECT * FROM breach_events WHERE assessment_status = 'pending'`
  ).all<BreachEvent>();

  for (const evt of pending.results) {
    const categories = JSON.parse(evt.data_categories) as string[];
    const hasSensitive = categories.some(c => SENSITIVE_CATEGORIES.has(c));
    // Section 113: serious harm reasonably likely if sensitive data + >1 individual, or any data + >100 individuals
    const seriousHarm = (hasSensitive && evt.affected_count >= 1) || evt.affected_count >= 100;

    const now = new Date().toISOString();
    await env.DB.prepare(
      `UPDATE breach_events SET assessment_status=?, assessed_at=?, serious_harm=? WHERE id=?`
    ).bind(seriousHarm ? 'reportable' : 'not_reportable', now, seriousHarm ? 1 : 0, evt.id).run();

    if (seriousHarm) {
      await env.BREACH_QUEUE.send({
        type: 'NZ_PRIVACY_COMMISSIONER_NOTIFICATION',
        breachId: evt.id,
        detectedAt: evt.detected_at,
        assessedAt: now,
        affectedCount: evt.affected_count,
        dataCategories: categories,
        reportDeadline: new Date(new Date(evt.detected_at).getTime() + 72 * 3600_000).toISOString(),
      });
    }
  }
}
```

## D1 Schema

```sql
-- D1 schema: nz_privacy_act.sql
CREATE TABLE IF NOT EXISTS personal_data_inventory (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  table_name TEXT NOT NULL UNIQUE,
  pii_columns TEXT NOT NULL,  -- JSON array of column names
  purpose TEXT NOT NULL,       -- IPP 1: lawful purpose
  retention_days INTEGER,
  active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS access_requests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL,
  requested_at TEXT NOT NULL,
  deadline TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  completed_at TEXT
);

CREATE TABLE IF NOT EXISTS correction_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL,
  table_name TEXT NOT NULL,
  field TEXT NOT NULL,
  old_value TEXT,
  new_value TEXT NOT NULL,
  reason TEXT,
  requested_at TEXT NOT NULL,
  applied_at TEXT,
  status TEXT NOT NULL DEFAULT 'pending'
);

CREATE TABLE IF NOT EXISTS breach_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_type TEXT NOT NULL,
  data_categories TEXT NOT NULL,  -- JSON array
  affected_count INTEGER NOT NULL DEFAULT 0,
  detected_at TEXT NOT NULL,
  assessment_status TEXT NOT NULL DEFAULT 'pending',
  assessed_at TEXT,
  serious_harm INTEGER,
  notified_commissioner_at TEXT,
  notified_individuals_at TEXT
);
```

## Anti-patterns

- Assuming NZ Privacy Act 2020 is equivalent to GDPR and sharing the same access/erasure pipeline — the 20-working-day SLA, harm-focused breach test, and correction rights differ materially from GDPR's 30-day SAR deadline and high-risk breach threshold.
- Calculating the 20-working-day deadline in calendar days — public holidays and weekends must be excluded; a miscalculation puts the organisation in breach of section 44.
- Treating a "notifiable breach" as equivalent to a GDPR 72-hour breach notification — under section 113 the notification is to the Privacy Commissioner *and* to affected individuals, not just the regulator.
- Deleting breach event records once the incident is resolved — these are regulatory evidence that must be retained for the duration of any investigation.

## Gotchas

- The Privacy Commissioner may grant an extension to the 20 working day access period (section 47); record any Commissioner correspondence as part of the access request row.
- IPP 11 (disclosure) does not require consent for disclosure required by law; log the legal basis alongside any third-party disclosure in the audit trail.
- New Zealand's extra-territorial reach applies to organisations that "carry on business in New Zealand" even without a physical presence — operating a paid SaaS with NZ subscribers typically qualifies.
- Correction requests under IPP 7 must be actioned even if you dispute the inaccuracy; where disputed, the individual can require a statement of the correction sought to be attached to the record.

## Verification

```ts
// tests/access-request.spec.ts
import { expect, test } from 'vitest';

test('20-working-day deadline excludes NZ public holidays', async () => {
  // Start on 2026-04-01 (Wednesday before Good Friday 3 Apr and Easter Monday 6 Apr)
  const start = new Date('2026-04-01T00:00:00Z');
  const { addWorkingDays } = await import('../src/handlers/access-request');
  const deadline = addWorkingDays(start, 20);
  // Should be later than simple 28 calendar days due to Easter and ANZAC Day (27 Apr)
  expect(deadline > new Date('2026-04-29T00:00:00Z')).toBe(true);
});

test('breach with sensitive health data triggers reportable status', async () => {
  const env = getMiniflareEnv();
  await env.DB.prepare(
    `INSERT INTO breach_events (event_type, data_categories, affected_count, detected_at, assessment_status)
     VALUES ('unauthorised_access', '["health"]', 1, datetime('now'), 'pending')`
  ).run();

  await assessBreaches(env);

  const evt = await env.DB.prepare(`SELECT serious_harm FROM breach_events`).first<{ serious_harm: number }>();
  expect(evt?.serious_harm).toBe(1);
});
```

## Related

- [gdpr-breach-notification-72h.md](gdpr-breach-notification-72h.md)
- [gdpr-data-subject-rights-api.md](gdpr-data-subject-rights-api.md)
- [australia-privacy-act-reform-2026.md](australia-privacy-act-reform-2026.md)
- [data-retention-automated-deletion-workers.md](data-retention-automated-deletion-workers.md)
- [singapore-pdpa-notifiable-breach-assessment-clock.md](singapore-pdpa-notifiable-breach-assessment-clock.md)

## Sources

- Privacy Act 2020 (NZ): https://www.legislation.govt.nz/act/public/2020/0031/latest/LMS23223.html
- NZ Privacy Commissioner — Notifiable Privacy Breaches Guide: https://www.privacy.org.nz/privacy-act-2020/privacy-breaches/notifiable-privacy-breaches/
- Information Privacy Principles (Schedule 1): https://www.legislation.govt.nz/act/public/2020/0031/latest/LMS23342.html
- Cloudflare D1 Documentation: https://developers.cloudflare.com/d1/
- Cloudflare Queues Documentation: https://developers.cloudflare.com/queues/
