# Panama Ley 81 Data Protection — Cloudflare Workers & D1

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your product has users in Panama or you incorporate there. Counsel flags **Law 81 of 2019**
("Ley 81 sobre Protección de Datos Personales") and its implementing **Executive Decree 285 of
2021**. The enforcement body is the **Autoridad Nacional de Transparencia y Acceso a la
Información (ANTAI)**. You need to bring your Cloudflare Workers + D1 stack into compliance.

---

## Context

Panama's Law 81 came into force on **March 29, 2021** (after a transitional period).
Executive Decree 285/2021 provides the implementing rules. Key features:

| Principle | Requirement |
|---|---|
| Lawful basis | Consent (primary), contract, legal obligation, vital interests, public interest |
| Consent | Must be free, unambiguous, specific, and informed; can be withdrawn at any time |
| Sensitive data | Health, sexual orientation, biometrics, political/religious opinions require explicit consent |
| Individual rights | Access (ARCO: Acceso, Rectificación, Cancelación, Oposición) |
| Security | Technical and administrative safeguards proportional to sensitivity |
| Cross-border transfers | Allowed to adequate countries or with data-subject consent or ANTAI-approved safeguards |
| Breach notification | Notify ANTAI within 72 hours of becoming aware |
| Data retention | No longer than necessary for the declared purpose |

**Fines:** ANTAI can impose fines from **USD 1 000** to **USD 100 000** per violation.

---

## Applicability

Law 81 applies to:
1. Data controllers or processors **established in Panama**
2. Processing of personal data of persons **located in Panama**, regardless of where the
   controller is established

This means a Worker deployed globally that collects data from Panamanian residents is in scope.

---

## D1 Schema

```sql
-- Panama Law 81 compliance tables
CREATE TABLE IF NOT EXISTS pa_consent_records (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id        TEXT    NOT NULL,
  purpose        TEXT    NOT NULL,
  is_sensitive   INTEGER NOT NULL DEFAULT 0,
  notice_version TEXT    NOT NULL,
  language       TEXT    NOT NULL DEFAULT 'es',  -- Spanish required
  given_at       TEXT    NOT NULL,
  withdrawn_at   TEXT,
  withdrawal_reason TEXT,
  ip_country     TEXT,
  evidence_hash  TEXT    -- SHA-256 of the consent notice shown
);

CREATE TABLE IF NOT EXISTS pa_arco_requests (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  reference     TEXT    NOT NULL UNIQUE,
  user_id       TEXT    NOT NULL,
  right_type    TEXT    NOT NULL,  -- 'access'|'rectification'|'cancellation'|'objection'
  status        TEXT    NOT NULL DEFAULT 'pending',
  submitted_at  TEXT    NOT NULL,
  deadline_at   TEXT    NOT NULL,
  resolved_at   TEXT,
  resolution    TEXT
);

CREATE TABLE IF NOT EXISTS pa_breach_log (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  reference         TEXT    NOT NULL UNIQUE,
  discovered_at     TEXT    NOT NULL,
  reported_to_antai TEXT,          -- timestamp of ANTAI notification
  affected_count    INTEGER,
  data_categories   TEXT    NOT NULL, -- JSON
  severity          TEXT    NOT NULL DEFAULT 'medium',
  status            TEXT    NOT NULL DEFAULT 'open'
);

CREATE INDEX IF NOT EXISTS idx_pa_consent_user ON pa_consent_records(user_id);
CREATE INDEX IF NOT EXISTS idx_pa_arco_user    ON pa_arco_requests(user_id);
```

---

## Consent Worker

```typescript
// workers/pa-consent.ts

export interface PanamaConsentPayload {
  userId: string;
  purpose: string;
  isSensitive: boolean;
  noticeVersion: string;
  noticeContentHash: string; // SHA-256 of exact notice text shown
}

export async function recordPanamaConsent(
  env: Env,
  payload: PanamaConsentPayload,
  request: Request
): Promise<void> {
  const ipCountry = request.headers.get("CF-IPCountry") ?? "XX";

  // Sensitive data: require separate, explicit confirmation
  if (payload.isSensitive) {
    const explicitHeader = request.headers.get("X-Explicit-Sensitive-Consent");
    if (explicitHeader !== "confirmed") {
      throw new Error(
        "Sensitive data consent under Panama Ley 81 requires explicit, " +
        "separate affirmative action."
      );
    }
  }

  await env.DB.prepare(`
    INSERT INTO pa_consent_records
      (user_id, purpose, is_sensitive, notice_version, given_at, ip_country, evidence_hash)
    VALUES (?, ?, ?, ?, ?, ?, ?)
  `).bind(
    payload.userId,
    payload.purpose,
    payload.isSensitive ? 1 : 0,
    payload.noticeVersion,
    new Date().toISOString(),
    ipCountry,
    payload.noticeContentHash
  ).run();
}

export async function withdrawPanamaConsent(
  env: Env,
  userId: string,
  purpose: string,
  reason?: string
): Promise<void> {
  // Law 81 Article 10: consent can be withdrawn at any time
  await env.DB.prepare(`
    UPDATE pa_consent_records
    SET    withdrawn_at = ?,
           withdrawal_reason = ?
    WHERE  user_id = ?
    AND    purpose = ?
    AND    withdrawn_at IS NULL
  `).bind(new Date().toISOString(), reason ?? null, userId, purpose).run();
}
```

---

## ARCO Rights Handler

```typescript
// workers/pa-arco.ts
type ARCORightType = "access" | "rectification" | "cancellation" | "objection";

// Law 81 Article 15: respond within 30 business days (extend by 15 with notice)
const PA_RESPONSE_CALENDAR_DAYS = 30;

export async function handlePanamaARCO(
  env: Env,
  userId: string,
  right: ARCORightType,
  details?: Record<string, unknown>
): Promise<Response> {
  const ref = `PA-${right.toUpperCase().slice(0, 3)}-${Date.now()}`;
  const deadline = new Date();
  deadline.setDate(deadline.getDate() + PA_RESPONSE_CALENDAR_DAYS);

  await env.DB.prepare(`
    INSERT INTO pa_arco_requests
      (reference, user_id, right_type, submitted_at, deadline_at)
    VALUES (?, ?, ?, ?, ?)
  `).bind(
    ref,
    userId,
    right,
    new Date().toISOString(),
    deadline.toISOString()
  ).run();

  if (right === "cancellation") {
    await processCancellation(env, userId, ref);
  }

  if (right === "access") {
    const data = await collectUserData(env, userId);
    await env.DB.prepare(`
      UPDATE pa_arco_requests SET status='resolved', resolved_at=?, resolution='data_provided'
      WHERE reference = ?
    `).bind(new Date().toISOString(), ref).run();
    return new Response(JSON.stringify({ reference: ref, data }), {
      headers: { "Content-Type": "application/json" },
    });
  }

  return new Response(JSON.stringify({
    reference: ref,
    right,
    status: "pending",
    deadlineIso: deadline.toISOString(),
    message: `Your ${right} request (ref: ${ref}) will be processed within 30 days.`,
  }), { headers: { "Content-Type": "application/json" } });
}

async function processCancellation(
  env: Env,
  userId: string,
  requestRef: string
): Promise<void> {
  // Anonymise PII while preserving audit tombstone
  await env.DB.prepare(`
    UPDATE users
    SET    email     = 'deleted+' || id || '@pa-deleted.invalid',
           full_name = 'PA Deleted User',
           deleted_at = ?
    WHERE  external_id = ?
  `).bind(new Date().toISOString(), userId).run();

  await env.DB.prepare(`
    UPDATE pa_consent_records
    SET    withdrawn_at = ?, withdrawal_reason = 'ARCO_CANCELLATION'
    WHERE  user_id = ? AND withdrawn_at IS NULL
  `).bind(new Date().toISOString(), userId).run();

  await env.DB.prepare(`
    UPDATE pa_arco_requests
    SET    status = 'resolved', resolved_at = ?, resolution = 'data_cancelled'
    WHERE  reference = ?
  `).bind(new Date().toISOString(), requestRef).run();
}

async function collectUserData(
  env: Env,
  userId: string
): Promise<Record<string, unknown>> {
  const consents = await env.DB.prepare(`
    SELECT purpose, given_at, withdrawn_at FROM pa_consent_records WHERE user_id = ?
  `).bind(userId).all();
  return { consents: consents.results };
}
```

---

## Breach Notification (72-hour Clock)

```typescript
// workers/pa-breach.ts
export interface PanamaBreachReport {
  discoveredAt: string;
  affectedCount: number;
  dataCategories: string[];
  likelyConsequences: string;
  measuresTaken: string;
}

export async function reportPanamaBreach(
  env: Env,
  report: PanamaBreachReport
): Promise<string> {
  const ref = `PA-BREACH-${Date.now()}`;
  const notifyDeadline = new Date(report.discoveredAt);
  notifyDeadline.setHours(notifyDeadline.getHours() + 72);

  await env.DB.prepare(`
    INSERT INTO pa_breach_log
      (reference, discovered_at, affected_count, data_categories, status)
    VALUES (?, ?, ?, ?, 'open')
  `).bind(
    ref,
    report.discoveredAt,
    report.affectedCount,
    JSON.stringify(report.dataCategories)
  ).run();

  // Enqueue ANTAI notification for immediate human action
  await env.BREACH_NOTIFICATION_QUEUE.send({
    ref,
    jurisdiction: "PA",
    antaiEndpoint: "https://www.antai.gob.pa/",  // submit via their portal
    notifyBy: notifyDeadline.toISOString(),
    summary: report,
  });

  return ref;
}
```

---

## Cross-Border Transfer Gate

```typescript
// workers/pa-transfer-gate.ts
// Law 81 Article 25 — transfers only to adequate countries or with safeguards/consent
// Decree 285 does not yet publish a formal adequacy list; use ANTAI guidance + OECD members
const PA_ADEQUATE_COUNTRIES = new Set([
  "AT","BE","BG","CY","CZ","DE","DK","EE","ES","FI","FR","GR","HR",
  "HU","IE","IT","LT","LU","LV","MT","NL","PL","PT","RO","SE","SI","SK",
  "NO","IS","LI","GB","CH","CA","AU","NZ","JP","AR","UY","CR","CO","MX",
]);

export async function assertPanamaTransferOk(
  env: Env,
  destination: string,
  userId?: string
): Promise<void> {
  if (PA_ADEQUATE_COUNTRIES.has(destination)) return;

  // Check for ANTAI-approved safeguard or data-subject consent to transfer
  if (userId) {
    const consent = await env.DB.prepare(`
      SELECT id FROM pa_consent_records
      WHERE  user_id = ? AND purpose = 'cross_border_transfer_' || ?
      AND    withdrawn_at IS NULL
      LIMIT  1
    `).bind(userId, destination).first();
    if (consent) return;
  }

  throw new Error(
    `Cross-border transfer to ${destination} requires ANTAI-approved safeguards ` +
    `or explicit data-subject consent under Panama Ley 81 Article 25.`
  );
}
```

---

## Anti-patterns

- **No Spanish-language privacy notice.** Panama requires notices to be clear and in Spanish
  accessible to average users; English-only notices are insufficient.
- **Implicit opt-in for sensitive categories.** Health, biometric, or political-opinion data
  always needs an explicit, granular consent checkbox — pre-ticked boxes are void.
- **Missing 72-hour breach notification.** ANTAI expects timely notification. Set up a monitored
  breach-notification queue with an alerting timeout at 48 hours.
- **Reusing consent for new purposes.** A consent given for purpose A cannot be extended to
  purpose B without a fresh consent capture.

---

## Gotchas

- ANTAI oversees **both** data protection and freedom of information. Breach reports and ARCO
  escalations go to the same authority through different channels.
- Panama Ley 81 allows data processors to process data on behalf of controllers; ensure your
  Data Processing Agreement (DPA) with any sub-processor references Ley 81 obligations.
- The law covers pseudonymous data if re-identification is reasonably possible.
- Executive Decree 285 may be supplemented by further implementing regulations; monitor the
  ANTAI Gaceta Oficial for updates.

---

## Verification

```bash
# 1. Confirm secrets
wrangler secret list

# 2. Verify D1 tables exist
wrangler d1 execute <DB> --command \
  "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'pa_%'"

# 3. Test consent recording
curl -X POST https://your-worker.workers.dev/consent/pa \
  -H "Content-Type: application/json" \
  -d '{
    "userId":"pa-001",
    "purpose":"analytics",
    "isSensitive":false,
    "noticeVersion":"1.0",
    "noticeContentHash":"abc123"
  }'

# 4. Test ARCO request
curl -X POST https://your-worker.workers.dev/arco/pa \
  -H "Content-Type: application/json" \
  -d '{"userId":"pa-001","right":"access"}'
```

---

## Related

- `costa-rica-prodhab-data-protection-workers-d1.md`
- `colombia-habeas-data-workers-d1-compliance.md`
- `peru-lpdp-workers-d1.md`
- `gdpr-breach-notification-72h.md`
- `cross-border-data-transfer-mechanisms.md`

---

## Sources

- Panama Law 81 of March 26, 2019 (Ley 81 sobre Protección de Datos Personales)
- Executive Decree 285 of 2021 (Implementing Regulations)
- ANTAI official portal: https://www.antai.gob.pa/
- Cloudflare Workers & D1 documentation: https://developers.cloudflare.com/
