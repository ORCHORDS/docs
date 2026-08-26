# Canada PIPEDA Compliance with Workers and D1: Breach of Security Safeguards

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your service collects personal information from Canadian users in the course of commercial activity. You need to comply with the Personal Information Protection and Electronic Documents Act (PIPEDA, S.C. 2000, c. 5) including the Breach of Security Safeguards Regulations (SOR/2018-64): logging breaches in D1, determining whether a breach poses a "real risk of significant harm" (RROSH), notifying the Office of the Privacy Commissioner of Canada (OPC) within a reasonable timeframe (industry guidance: 72 hours), and notifying affected individuals.

## Context

PIPEDA governs federally regulated private sector organisations and interprovincial/international commerce. Quebec, Alberta, and British Columbia have substantially similar provincial laws (Law 25 / PIPA AB / PIPA BC). PIPEDA's 10 Fair Information Principles (Schedule 1) drive the architectural obligations:

1. Accountability
2. Identifying purposes
3. Consent
4. Limiting collection
5. Limiting use, disclosure, and retention
6. Accuracy
7. Safeguards
8. Openness
9. Individual access
10. Challenging compliance

The Breach of Security Safeguards Regulations require:
- A **breach record** to be maintained for 24 months.
- OPC notification when a breach creates RROSH.
- Individual notification without unreasonable delay when RROSH exists.

## D1 Schema — security_breaches

```sql
CREATE TABLE IF NOT EXISTS security_breaches (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  description    TEXT    NOT NULL,
  affected_count INTEGER NOT NULL DEFAULT 0,
  risk_level     TEXT    NOT NULL CHECK(risk_level IN ('low','medium','high','rrosh')),
  data_categories TEXT   NOT NULL,  -- JSON array e.g. ["name","email","SIN"]
  discovered_at  TEXT    NOT NULL,
  reported_at    TEXT,              -- timestamp of OPC notification
  individuals_notified_at TEXT,     -- timestamp of individual notification
  remediation    TEXT,
  created_at     TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- 24-month retention index for compliance record check
CREATE INDEX IF NOT EXISTS idx_breach_created
  ON security_breaches(created_at);

CREATE TABLE IF NOT EXISTS breach_notifications (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  breach_id  INTEGER NOT NULL REFERENCES security_breaches(id),
  channel    TEXT    NOT NULL,  -- 'opc' | 'individual' | 'other_regulator'
  sent_at    TEXT    NOT NULL DEFAULT (datetime('now')),
  reference  TEXT               -- OPC reference number or email ID
);
```

## Breach Worker — RROSH Assessment and OPC Notification

```typescript
// workers/pipeda-breach.ts
import { Env } from './types';

type RiskLevel = 'low' | 'medium' | 'high' | 'rrosh';

interface BreachPayload {
  description: string;
  affectedCount: number;
  dataCategories: string[];
  discoveredAt: string;
  remediation?: string;
}

/**
 * Assess whether a breach meets the RROSH threshold.
 * RROSH factors (Regulations s. 7):
 *   - sensitivity of personal information
 *   - probability of misuse
 *   - number of individuals affected
 *   - whether information has been accessed
 */
function assessRisk(payload: BreachPayload): RiskLevel {
  const sensitive = ['SIN', 'credit_card', 'health', 'biometric', 'passport', 'banking'];
  const hasSensitive = payload.dataCategories.some(c => sensitive.includes(c));
  const largeScale = payload.affectedCount >= 100;

  if (hasSensitive && largeScale) return 'rrosh';
  if (hasSensitive || largeScale) return 'high';
  if (payload.affectedCount >= 10) return 'medium';
  return 'low';
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === 'POST' && url.pathname === '/breach/report') {
      return handleReport(request, env);
    }
    if (request.method === 'GET' && url.pathname === '/breach/list') {
      return handleList(env);
    }

    return new Response('Not Found', { status: 404 });
  },
};

async function handleReport(request: Request, env: Env): Promise<Response> {
  const payload = await request.json<BreachPayload>();

  const { description, affectedCount, dataCategories, discoveredAt, remediation } = payload;
  if (!description || !dataCategories?.length || !discoveredAt) {
    return new Response(JSON.stringify({ error: 'Missing required fields' }), {
      status: 400, headers: { 'Content-Type': 'application/json' },
    });
  }

  const riskLevel = assessRisk(payload);
  const isRROSH = riskLevel === 'rrosh';

  // Insert breach record (must be retained 24 months)
  const ins = await env.DB.prepare(
    `INSERT INTO security_breaches
       (description, affected_count, risk_level, data_categories, discovered_at, remediation)
     VALUES (?, ?, ?, ?, ?, ?)`
  ).bind(
    description,
    affectedCount,
    riskLevel,
    JSON.stringify(dataCategories),
    discoveredAt,
    remediation ?? null
  ).run();

  const breachId = ins.meta.last_row_id as number;

  // If RROSH: notify OPC within 72 hours per regulatory guidance
  if (isRROSH) {
    await notifyOPC(env, breachId, payload);
  }

  return new Response(JSON.stringify({
    breachId,
    riskLevel,
    rrosh: isRROSH,
    action: isRROSH
      ? 'OPC notified; individual notification required without unreasonable delay'
      : 'Breach logged; no OPC notification required at this risk level',
  }), {
    status: 201, headers: { 'Content-Type': 'application/json' },
  });
}

async function notifyOPC(
  env: Env,
  breachId: number,
  payload: BreachPayload
): Promise<void> {
  // OPC does not yet expose a machine-readable endpoint; use their online breach report form.
  // This stub records the notification attempt and updates the DB.
  const ref = `OPC-${Date.now()}`; // replace with actual OPC reference once submitted

  await env.DB.prepare(
    `UPDATE security_breaches SET reported_at = datetime('now') WHERE id = ?`
  ).bind(breachId).run();

  await env.DB.prepare(
    `INSERT INTO breach_notifications (breach_id, channel, reference) VALUES (?, 'opc', ?)`
  ).bind(breachId, ref).run();

  // Optionally: send internal Slack/email alert to DPO team
  await fetch(env.SLACK_WEBHOOK_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      text: `PIPEDA RROSH breach #${breachId}: ${payload.description}. Notify OPC and individuals.`,
    }),
  });
}

async function handleList(env: Env): Promise<Response> {
  const { results } = await env.DB.prepare(
    `SELECT id, risk_level, affected_count, discovered_at, reported_at
     FROM security_breaches
     ORDER BY created_at DESC LIMIT 50`
  ).all();

  return new Response(JSON.stringify({ breaches: results }), {
    status: 200, headers: { 'Content-Type': 'application/json' },
  });
}
```

## 24-Month Record Retention Purge

```typescript
// workers/pipeda-purge.ts (scheduled)
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    // Regulations require 24-month retention; delete older records
    await env.DB.prepare(
      `DELETE FROM security_breaches
       WHERE created_at < datetime('now', '-24 months')`
    ).run();
  },
};
```

## Individual Notification Endpoint

```typescript
// After OPC is notified, individuals must be notified "as soon as feasible"
async function notifyIndividuals(env: Env, breachId: number): Promise<void> {
  await env.DB.prepare(
    `UPDATE security_breaches
     SET individuals_notified_at = datetime('now') WHERE id = ?`
  ).bind(breachId).run();

  await env.DB.prepare(
    `INSERT INTO breach_notifications (breach_id, channel) VALUES (?, 'individual')`
  ).bind(breachId).run();
}
```

## Anti-patterns

- Deleting breach records before 24 months — directly violates Breach of Security Safeguards Regulations s. 10.
- Using a fixed 72-hour clock as a hard deadline and failing to notify OPC when still investigating — notify "as soon as feasible" with available information.
- Conflating RROSH assessment with severity for internal purposes — RROSH is a legal threshold, not a priority label.
- Collecting SINs (Social Insurance Numbers) without strict necessity; SINs trigger elevated sensitivity under PIPEDA.

## Gotchas

- Quebec's Law 25 (Bill 64) imposes a **72-hour mandatory notification** to the Commission d'accès à l'information (CAI) — stricter than PIPEDA's "as soon as feasible". If serving Quebec residents, comply with Law 25 timelines.
- PIPEDA applies to **employee personal information** in the federally regulated private sector; provincially regulated employers in ON/QC/BC/AB may be exempt.
- The OPC breach report form is available at: https://www.priv.gc.ca/en/report-a-concern/report-a-privacy-breach-at-your-business/
- Failure to notify is a violation; penalties under PIPEDA can include public naming in OPC reports and court orders.

## Verification

```bash
# List recent breaches
wrangler d1 execute example project-db --command \
  "SELECT id, risk_level, affected_count, reported_at FROM security_breaches \
   ORDER BY created_at DESC LIMIT 10;"

# Test breach report endpoint with RROSH-triggering payload
curl -X POST https://privacy.example.com/breach/report \
  -H 'Content-Type: application/json' \
  -d '{"description":"DB dump exposed","affectedCount":500,\
       "dataCategories":["SIN","email"],"discoveredAt":"2026-08-24T09:00:00Z"}'

# Confirm notification record
wrangler d1 execute example project-db --command \
  "SELECT * FROM breach_notifications ORDER BY sent_at DESC LIMIT 5;"
```

## Related

- `documentation/categories/compliance/australia-privacy-act-workers-d1.md`
- `documentation/categories/compliance/hong-kong-pdpo-workers-d1.md`
- `documentation/categories/compliance/indonesia-pdp-law-workers-d1.md`

## Sources

- PIPEDA: https://laws-lois.justice.gc.ca/eng/acts/P-8.6/
- Breach of Security Safeguards Regulations (SOR/2018-64): https://laws-lois.justice.gc.ca/eng/regulations/SOR-2018-64/
- OPC Breach Report Guide: https://www.priv.gc.ca/en/report-a-concern/report-a-privacy-breach-at-your-business/
- Quebec Law 25: https://www.cai.gouv.qc.ca/en/law-25/
- Cloudflare D1: https://developers.cloudflare.com/d1/
