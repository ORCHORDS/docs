# Jordan Personal Data Protection Law — Cloudflare Workers & D1

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your application serves Jordanian users or you operate a subsidiary in Jordan. Legal has flagged
**Personal Data Protection Law No. 24 of 2023** (the "PDPL"), which came into force in
September 2023 and is enforced by the **Personal Data Protection Commission (PDPC)**. You need
to map the obligations onto a Cloudflare Workers + D1 architecture.

---

## Context

Jordan's PDPL is the country's first comprehensive data-protection law. It is GDPR-influenced
but has locally specific requirements:

| Principle | Requirement |
|---|---|
| Lawful basis | Consent, contract, legal obligation, vital interests, public interest, legitimate interest |
| Sensitive data | Health, genetic, biometric, racial/ethnic origin, criminal records, political/religious opinions require explicit consent or legal mandate |
| Data subject rights | Access, rectification, deletion, restriction, portability, objection |
| Controller registration | Controllers must register with the PDPC |
| DPO | Required for large-scale processing or processing of sensitive data |
| Cross-border transfers | Permitted to countries with adequate protection or with PDPC approval / appropriate safeguards |
| Breach notification | Notify PDPC without undue delay (implementing regulations may set a specific clock) |
| Retention | Data must not be kept longer than necessary for the stated purpose |

The **PDPC** was established under the law and began operations in 2024. Fines under the PDPL
can reach **JOD 50 000** (~USD 70 k) per violation.

---

## Controller Registration

Register with PDPC before commencing processing. Maintain your registration number as a secret:

```toml
# wrangler.toml [vars]
JO_PDPC_REGISTRATION_ID = "JO-CTRL-2026-XXXXX"
JO_DPO_CONTACT_EMAIL    = "dpo@yourcompany.com"
```

---

## D1 Schema

```sql
-- Data processing activities register (PDPL Article 8 equivalent)
CREATE TABLE IF NOT EXISTS jo_processing_activities (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  activity_name      TEXT    NOT NULL,
  pdpc_ref           TEXT,                -- PDPC registration reference
  legal_basis        TEXT    NOT NULL,
  data_categories    TEXT    NOT NULL,   -- JSON array
  purposes           TEXT    NOT NULL,   -- JSON array
  recipients         TEXT,              -- JSON array
  retention_days     INTEGER,
  cross_border       INTEGER DEFAULT 0,
  cross_border_dest  TEXT,
  created_at         TEXT    NOT NULL,
  updated_at         TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS jo_consent_records (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id         TEXT    NOT NULL,
  purpose         TEXT    NOT NULL,
  sensitive       INTEGER NOT NULL DEFAULT 0,  -- 1 for sensitive-data consent
  consent_text_ar TEXT,                        -- Arabic notice text hash
  consent_text_en TEXT,                        -- English notice text hash
  notice_version  TEXT    NOT NULL,
  given_at        TEXT    NOT NULL,
  withdrawn_at    TEXT,
  ip_country      TEXT
);

CREATE TABLE IF NOT EXISTS jo_rights_log (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  reference    TEXT    NOT NULL UNIQUE,
  user_id      TEXT    NOT NULL,
  right_type   TEXT    NOT NULL,
  status       TEXT    NOT NULL DEFAULT 'pending',
  submitted_at TEXT    NOT NULL,
  resolved_at  TEXT,
  notes        TEXT
);

CREATE INDEX IF NOT EXISTS idx_jo_consent_user ON jo_consent_records(user_id);
CREATE INDEX IF NOT EXISTS idx_jo_rights_user  ON jo_rights_log(user_id);
```

---

## Consent Worker

```typescript
// workers/jo-consent.ts

export interface JordanConsentPayload {
  userId: string;
  purpose: string;
  isSensitive: boolean;
  noticeVersion: string;
  language: "ar" | "en";
}

export async function recordJordanConsent(
  env: Env,
  payload: JordanConsentPayload,
  request: Request
): Promise<{ consentId: number }> {
  const ipCountry = request.headers.get("CF-IPCountry") ?? "XX";

  // Sensitive data requires explicit, separate consent flow
  if (payload.isSensitive && payload.purpose !== "vital_interests") {
    const confirmed = request.headers.get("X-Explicit-Sensitive-Consent");
    if (confirmed !== "true") {
      throw new Error(
        "Explicit affirmative action required for sensitive-data consent under Jordan PDPL"
      );
    }
  }

  const result = await env.DB.prepare(`
    INSERT INTO jo_consent_records
      (user_id, purpose, sensitive, notice_version, given_at, ip_country)
    VALUES (?, ?, ?, ?, ?, ?)
  `).bind(
    payload.userId,
    payload.purpose,
    payload.isSensitive ? 1 : 0,
    payload.noticeVersion,
    new Date().toISOString(),
    ipCountry
  ).run();

  return { consentId: result.meta.last_row_id as number };
}

export async function withdrawJordanConsent(
  env: Env,
  userId: string,
  purpose?: string
): Promise<void> {
  if (purpose) {
    await env.DB.prepare(`
      UPDATE jo_consent_records
      SET    withdrawn_at = ?
      WHERE  user_id = ? AND purpose = ? AND withdrawn_at IS NULL
    `).bind(new Date().toISOString(), userId, purpose).run();
  } else {
    // Withdraw all consents
    await env.DB.prepare(`
      UPDATE jo_consent_records
      SET    withdrawn_at = ?
      WHERE  user_id = ? AND withdrawn_at IS NULL
    `).bind(new Date().toISOString(), userId).run();
  }
}
```

---

## Data Subject Rights Router

```typescript
// workers/jo-rights.ts
type JORightType = "access" | "rectification" | "deletion" | "restriction" | "portability" | "objection";

const JO_DEADLINE_DAYS: Record<JORightType, number> = {
  access:         30,
  rectification:  30,
  deletion:       30,
  restriction:    30,
  portability:    30,
  objection:      30,
};

export async function handleJordanRight(
  env: Env,
  userId: string,
  right: JORightType
): Promise<Response> {
  const ref = `JO-${right.toUpperCase()}-${Date.now()}`;
  const deadline = new Date();
  deadline.setDate(deadline.getDate() + JO_DEADLINE_DAYS[right]);

  await env.DB.prepare(`
    INSERT INTO jo_rights_log (reference, user_id, right_type, submitted_at)
    VALUES (?, ?, ?, ?)
  `).bind(ref, userId, right, new Date().toISOString()).run();

  if (right === "deletion") {
    await executeSoftDelete(env, userId);
  }

  if (right === "portability") {
    const data = await collectPortableData(env, userId);
    return new Response(JSON.stringify({ reference: ref, data }), {
      headers: { "Content-Type": "application/json" },
    });
  }

  return new Response(JSON.stringify({
    reference: ref,
    right,
    status: "pending",
    deadlineIso: deadline.toISOString(),
  }), { headers: { "Content-Type": "application/json" } });
}

async function executeSoftDelete(env: Env, userId: string): Promise<void> {
  // Anonymise rather than hard-delete to preserve audit trail
  await env.DB.prepare(`
    UPDATE users
    SET    email     = 'deleted-' || id || '@deleted.invalid',
           full_name = 'Deleted User',
           deleted_at = ?
    WHERE  id = ?
  `).bind(new Date().toISOString(), userId).run();

  await withdrawJordanConsent(env, userId);
}

async function collectPortableData(
  env: Env,
  userId: string
): Promise<Record<string, unknown>> {
  const rows = await env.DB.prepare(`
    SELECT purpose, given_at FROM jo_consent_records WHERE user_id = ?
  `).bind(userId).all();
  return { consents: rows.results };
}
```

---

## Cross-Border Transfer Controls

```typescript
// workers/jo-transfer-gate.ts

// Adequate countries per Jordan PDPC guidance (verify against official list)
const JO_ADEQUATE_COUNTRIES = new Set([
  // EU/EEA members
  "AT","BE","BG","CY","CZ","DE","DK","EE","ES","FI","FR","GR","HR",
  "HU","IE","IT","LT","LU","LV","MT","NL","PL","PT","RO","SE","SI","SK",
  "NO","IS","LI",
  // Others with recognised adequacy
  "GB","CH","CA","AU","NZ","JP","KR","AR","UY","IL","MA",
]);

export async function assertJordanTransferOk(
  env: Env,
  destinationCountry: string,
  dataCategories: string[]
): Promise<void> {
  if (!JO_ADEQUATE_COUNTRIES.has(destinationCountry)) {
    // Require a PDPC-approved transfer mechanism reference
    const mechanism = await env.DB.prepare(`
      SELECT mechanism_type, reference
      FROM   transfer_safeguards
      WHERE  destination = ?
      AND    jurisdiction = 'JO'
      AND    active = 1
      LIMIT  1
    `).bind(destinationCountry).first<{ mechanism_type: string; reference: string }>();

    if (!mechanism) {
      throw new Error(
        `No approved transfer safeguard on file for ${destinationCountry} ` +
        `under Jordan PDPL. Register one with the PDPC or use standard contractual clauses.`
      );
    }
  }
}
```

---

## Breach Notification Workflow

Jordan PDPL requires notification to PDPC "without undue delay." While specific hours are set
in implementing regulations, planning for 72 hours mirrors best practice.

```typescript
// workers/jo-breach.ts
export interface JordanBreachReport {
  discoveredAt: string;
  affectedCount: number;
  dataCategories: string[];
  likelyConsequences: string;
  measuresTaken: string;
  dpoContact: string;
}

export async function logJordanBreach(
  env: Env,
  report: JordanBreachReport
): Promise<string> {
  const ref = `JO-BREACH-${Date.now()}`;

  await env.DB.prepare(`
    INSERT INTO breach_log
      (reference, jurisdiction, discovered_at, affected_count,
       data_categories, consequences, measures, dpo_contact, status)
    VALUES (?, 'JO', ?, ?, ?, ?, ?, ?, 'pending_notification')
  `).bind(
    ref,
    report.discoveredAt,
    report.affectedCount,
    JSON.stringify(report.dataCategories),
    report.likelyConsequences,
    report.measuresTaken,
    report.dpoContact
  ).run();

  // Trigger alert via Cloudflare Queue for PDPC notification workflow
  await env.BREACH_QUEUE.send({
    ref,
    jurisdiction: "JO",
    discoveredAt: report.discoveredAt,
    pdpcEmail: "notifications@pdpc.gov.jo", // check current address
  });

  return ref;
}
```

---

## Anti-patterns

- **Treating Jordan PDPL identically to GDPR.** Though similar in structure, PDPL has its own
  registration requirement, its own adequacy list, and local-language notice requirements.
- **No Arabic privacy notice.** Jordan is an Arabic-speaking jurisdiction; the notice must be
  understandable to the average user.
- **Missing DPO appointment.** If you process health, biometric, or large-scale data, a DPO is
  mandatory; this must be registered with PDPC.
- **Processing sensitive data on consent alone.** Some categories (criminal records) may require
  explicit legal mandate regardless of consent.

---

## Gotchas

- The PDPC is relatively new (2024). Implementing regulations, adequacy decisions, and guidance
  notes will evolve; subscribe to PDPC official communications.
- Jordan's law extends to controllers outside Jordan that process data of Jordanian residents —
  extra-territorial scope similar to GDPR Article 3(2).
- "Legitimate interest" exists as a basis but the balancing test documentation must be retained
  and is reviewable by PDPC.
- Cloudflare's default data routing may not keep data in Jordan or in adequate countries. Review
  your Smart Routing and Tiered Caching settings.

---

## Verification

```bash
# 1. Check registration secret is set
wrangler secret list | grep JO_PDPC

# 2. Verify D1 tables
wrangler d1 execute <DB> --command \
  "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'jo_%'"

# 3. Smoke-test consent recording
curl -X POST https://your-worker.workers.dev/consent/jo \
  -H "Content-Type: application/json" \
  -H "X-Explicit-Sensitive-Consent: true" \
  -d '{"userId":"jo-test-1","purpose":"health_profile","isSensitive":true,"noticeVersion":"1.0","language":"ar"}'

# 4. Test rights endpoint
curl -X POST https://your-worker.workers.dev/rights/jo \
  -H "Content-Type: application/json" \
  -d '{"userId":"jo-test-1","right":"access"}'
```

---

## Related

- `gdpr-data-subject-rights-api.md`
- `saudi-arabia-pdpl-workers-d1.md`
- `uae-pdpl-personal-data-workers.md`
- `cross-border-data-transfer-mechanisms.md`
- `gdpr-breach-notification-72h.md`

---

## Sources

- Jordan Personal Data Protection Law No. 24 of 2023
- Jordan Personal Data Protection Commission (PDPC): official government portal
- GDPR adequacy parallels: EDPB guidance
- Cloudflare Workers & D1 documentation: https://developers.cloudflare.com/
