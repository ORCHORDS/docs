# Zimbabwe Cyber and Data Protection Act 2021 (CDPA) — Workers & D1 Compliance

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your example project platform operates in or serves users in Zimbabwe, or a Zimbabwean entity uses your services to process personal data. The Cyber and Data Protection Act [Chapter 12:07] (CDPA 2021), signed into law 3 December 2021, establishes data protection obligations enforced by the Postal and Telecommunications Regulatory Authority of Zimbabwe (POTRAZ) acting as interim regulator, with a dedicated Cyber Security Centre and Data Protection Authority established under the Act. A regulatory inquiry asks whether the Cloudflare Workers / D1 stack satisfies registration, consent, data-localisation, and breach-notification requirements.

## Context

The CDPA 2021 applies to any data controller or processor that processes personal data of Zimbabwe residents, regardless of where the controller is established ("effects-based" jurisdiction). Highlights:

- **Registration** — controllers and processors must register with the Cyber Security Centre (CSC) created under Part III of the CDPA before processing personal data.
- **Data protection principles** — purpose limitation, data minimisation, accuracy, storage limitation, integrity/confidentiality; closely mirror GDPR principles.
- **Sensitive data** — racial/ethnic origin, political opinions, religious beliefs, trade-union membership, genetic data, biometric data, health data, sex life/sexual orientation; requires **explicit consent** or a statutory exemption (Section 27).
- **Cross-border transfers** — restricted to countries with "adequate" data protection or via safeguards approved by the CSC (Section 29); no formal adequacy list published as of mid-2026, so SCCs or explicit consent are the practical mechanisms.
- **Data localisation** — certain categories of "critical data" as designated by the Minister must be stored on servers physically located in Zimbabwe (Statutory Instrument guidance pending full implementation).
- **Breach notification** — controllers must notify the CSC "as soon as reasonably practicable" after discovery; within 72 hours is the operational target per CSC guidance.
- **Cybercrime provisions** — Part IV creates offences for unauthorised access, unlawful interception, and computer fraud; keep audit logs accordingly.
- Penalties: up to ZWL 20 million or USD equivalent per offence; criminal liability for officers.

## 1. Registration Flag and Kill-Switch

```typescript
// workers/zw-cdpa-registration.ts
export interface Env {
  KV: KVNamespace;
  DB: D1Database;
}

interface ZWRegistration {
  registered:  boolean;
  reg_ref:     string;
  issued_at:   string;
  expiry_date: string;
  categories:  string[];   // processing categories declared at registration
}

export async function getZWRegistration(env: Env): Promise<ZWRegistration | null> {
  return env.KV.get<ZWRegistration>('zw_cdpa_registration', 'json');
}

export async function assertZWRegistration(env: Env): Promise<void> {
  const reg = await getZWRegistration(env);
  if (!reg?.registered) {
    throw new Error('ZW CDPA 2021: CSC registration required before processing personal data');
  }
  if (new Date(reg.expiry_date) < new Date()) {
    throw new Error(`ZW CDPA 2021: registration expired ${reg.expiry_date}; renew with CSC/POTRAZ`);
  }
}
```

```bash
# Store registration details
wrangler kv key put zw_cdpa_registration \
  '{"registered":true,"reg_ref":"CSC-2025-00789","issued_at":"2025-03-01","expiry_date":"2026-12-31","categories":["marketing","analytics","user_accounts"]}' \
  --binding KV --env production
```

## 2. Consent Collection and Sensitive-Data Gate

```typescript
// workers/zw-cdpa-consent.ts
const ZW_SENSITIVE = new Set([
  'race_ethnicity', 'political_opinion', 'religion', 'trade_union',
  'genetic', 'biometric', 'health', 'sex_life_sexual_orientation'
]);

export async function recordZWConsent(
  env: Env,
  userId: string,
  purpose: string,
  isSensitive: boolean,
  granted: boolean,
  noticeVersion: string
): Promise<void> {
  await env.DB.prepare(
    `INSERT INTO zw_cdpa_consent
       (user_id, purpose, sensitive, granted, notice_version, captured_at, withdrawn_at)
     VALUES (?,?,?,?,?,CURRENT_TIMESTAMP,NULL)
     ON CONFLICT(user_id, purpose) DO UPDATE
     SET granted=excluded.granted, notice_version=excluded.notice_version,
         captured_at=CURRENT_TIMESTAMP, withdrawn_at=NULL`
  ).bind(userId, purpose, isSensitive ? 1 : 0, granted ? 1 : 0, noticeVersion).run();
}

export async function assertZWSensitiveConsent(
  env: Env,
  userId: string,
  category: string
): Promise<void> {
  if (!ZW_SENSITIVE.has(category)) return;

  const row = await env.DB.prepare(
    `SELECT granted FROM zw_cdpa_consent
     WHERE user_id = ? AND purpose = ? AND withdrawn_at IS NULL`
  ).bind(userId, category).first<{ granted: number }>();

  if (!row || row.granted !== 1) {
    throw new Error(
      `ZW CDPA 2021 §27: explicit consent required for sensitive category '${category}'`
    );
  }
}
```

```sql
CREATE TABLE IF NOT EXISTS zw_cdpa_consent (
  user_id        TEXT NOT NULL,
  purpose        TEXT NOT NULL,
  sensitive      INTEGER NOT NULL DEFAULT 0,
  granted        INTEGER NOT NULL DEFAULT 0,
  notice_version TEXT NOT NULL,
  captured_at    TEXT NOT NULL,
  withdrawn_at   TEXT,
  PRIMARY KEY (user_id, purpose)
);
```

## 3. Cross-Border Transfer Controls

No formal adequacy list exists; treat all outbound transfers as requiring documented safeguards.

```typescript
// workers/zw-cdpa-transfers.ts
type TransferMechanism = 'SCC' | 'BCR' | 'explicit_consent' | 'vital_interests' | 'legal_claim';

interface TransferRecord {
  transfer_id:  string;
  destination:  string;
  mechanism:    TransferMechanism;
  data_types:   string[];
  approved_at:  string;
  approved_by:  string;
}

export async function logAndAssertTransfer(
  env: Env,
  destination: string,
  mechanism: TransferMechanism | undefined,
  dataTypes: string[]
): Promise<void> {
  const PERMITTED_MECHANISMS = new Set<TransferMechanism>([
    'SCC', 'BCR', 'explicit_consent', 'vital_interests', 'legal_claim'
  ]);

  if (!mechanism || !PERMITTED_MECHANISMS.has(mechanism)) {
    throw new Error(
      `ZW CDPA 2021 §29: transfer to '${destination}' requires an approved safeguard (SCC, BCR, explicit consent)`
    );
  }

  await env.DB.prepare(
    `INSERT INTO zw_cdpa_transfer_log
       (transfer_id, destination, mechanism, data_types, logged_at)
     VALUES (?,?,?,?,CURRENT_TIMESTAMP)`
  ).bind(
    crypto.randomUUID(), destination, mechanism, JSON.stringify(dataTypes)
  ).run();
}
```

## 4. Data-Subject Rights Handler

```typescript
// workers/zw-cdpa-dsr.ts
type ZWRight = 'access' | 'rectification' | 'erasure' | 'objection' | 'restriction';

export async function handleZWDSR(
  env: Env,
  requestId: string,
  userId: string,
  right: ZWRight,
  payload?: Record<string, unknown>
): Promise<Record<string, unknown>> {
  await env.DB.prepare(
    `INSERT OR IGNORE INTO zw_cdpa_dsr_log
       (request_id, user_id, right_type, received_at, deadline, status)
     VALUES (?,?,?,CURRENT_TIMESTAMP,datetime(CURRENT_TIMESTAMP,'+30 days'),'pending')`
  ).bind(requestId, userId, right).run();

  let result: Record<string, unknown> = {};

  switch (right) {
    case 'access': {
      const rows = await env.DB.prepare('SELECT * FROM user_data WHERE user_id = ?')
        .bind(userId).all();
      result = { records: rows.results };
      break;
    }
    case 'erasure': {
      await env.DB.batch([
        env.DB.prepare('DELETE FROM user_data WHERE user_id = ?').bind(userId),
        env.DB.prepare('DELETE FROM zw_cdpa_consent WHERE user_id = ?').bind(userId),
      ]);
      result = { erased: true };
      break;
    }
    case 'rectification': {
      const sets = Object.keys(payload ?? {}).map(k => `${k} = ?`).join(', ');
      if (sets) {
        await env.DB.prepare(`UPDATE user_data SET ${sets} WHERE user_id = ?`)
          .bind(...Object.values(payload ?? {}), userId).run();
      }
      result = { rectified: true };
      break;
    }
    default:
      result = { acknowledged: true };
  }

  await env.DB.prepare(
    `UPDATE zw_cdpa_dsr_log SET status='completed', completed_at=CURRENT_TIMESTAMP
     WHERE request_id = ?`
  ).bind(requestId).run();

  return result;
}
```

## 5. Breach Notification Log

```typescript
// workers/zw-cdpa-breach.ts
export async function logZWBreach(
  env: Env,
  breachId: string,
  description: string,
  categories: string[],
  affectedCount: number,
  discoveredAt: string,
  riskLevel: 'high' | 'medium' | 'low'
): Promise<void> {
  // CSC guidance target: notify within 72 hours
  const deadline = new Date(
    new Date(discoveredAt).getTime() + 72 * 60 * 60 * 1000
  ).toISOString();

  await env.DB.prepare(
    `INSERT INTO zw_cdpa_breach_log
       (breach_id, description, categories, affected_count,
        discovered_at, risk_level, csc_notify_deadline, csc_notified_at)
     VALUES (?,?,?,?,?,?,?,NULL)`
  ).bind(
    breachId, description, JSON.stringify(categories),
    affectedCount, discoveredAt, riskLevel, deadline
  ).run();

  if (riskLevel === 'high') {
    console.error(`ZW CDPA BREACH [HIGH]: notify CSC/POTRAZ by ${deadline}`);
  }
}
```

```sql
CREATE TABLE IF NOT EXISTS zw_cdpa_breach_log (
  breach_id            TEXT PRIMARY KEY,
  description          TEXT NOT NULL,
  categories           TEXT NOT NULL,
  affected_count       INTEGER NOT NULL,
  discovered_at        TEXT NOT NULL,
  risk_level           TEXT NOT NULL,
  csc_notify_deadline  TEXT NOT NULL,
  csc_notified_at      TEXT
);

CREATE TABLE IF NOT EXISTS zw_cdpa_dsr_log (
  request_id   TEXT PRIMARY KEY,
  user_id      TEXT NOT NULL,
  right_type   TEXT NOT NULL,
  received_at  TEXT NOT NULL,
  deadline     TEXT NOT NULL,
  completed_at TEXT,
  status       TEXT NOT NULL DEFAULT 'pending'
);

CREATE TABLE IF NOT EXISTS zw_cdpa_transfer_log (
  transfer_id TEXT PRIMARY KEY,
  destination TEXT NOT NULL,
  mechanism   TEXT NOT NULL,
  data_types  TEXT NOT NULL,
  logged_at   TEXT NOT NULL
);
```

## Anti-patterns

- **Processing before CSC registration** — the Act provides no grace period; processing is unlawful from day one.
- **Assuming EU SCCs are automatically valid in Zimbabwe** — ZW does not have an EU adequacy decision; SCCs are accepted as a safeguard by CSC guidance, but the controller must still file the transfer record with the CSC.
- **Treating the data-localisation obligation as aspirational** — while implementing Statutory Instruments are still evolving (as of mid-2026), build localisation capability now (e.g., D1 database pinned to a Johannesburg-proximate edge or on-premises backup) to avoid retrofit costs.
- **No cybercrime audit trail** — CDPA Part IV creates criminal offences for employees who access systems without authority; application-level audit logs of privileged access are expected in any regulatory inspection.

## Gotchas

- **POTRAZ acts as interim regulator** until the dedicated Data Protection Authority under Section 8 is fully constituted; correspondence should currently go to POTRAZ's Cyber Security Centre.
- **"As soon as reasonably practicable"** for breach notification is operationally interpreted as 72 hours; in practice the CSC has accepted 72-hour self-imposed deadlines as compliant.
- **USD vs. ZWL penalties** — the Act specifies ZWL amounts, but enforcement may be converted to USD at the interbank rate; the practical exposure is moderate but reputational risk is high for a foreign-operated platform.
- **CF-IPCountry = 'ZW'** is a reliable indicator for Zimbabwe routing; pair it with a user-declared country field for accounts.

## Verification

```bash
# Registration status
wrangler kv key get zw_cdpa_registration --binding KV --env production

# Open breaches missing CSC notification
wrangler d1 execute PROD_DB --command \
  "SELECT breach_id, risk_level, discovered_at, csc_notify_deadline
   FROM zw_cdpa_breach_log WHERE csc_notified_at IS NULL"

# Overdue DSRs
wrangler d1 execute PROD_DB --command \
  "SELECT request_id, user_id, right_type, received_at FROM zw_cdpa_dsr_log
   WHERE status = 'pending' AND julianday('now') > julianday(deadline)"

# Transfer log audit
wrangler d1 execute PROD_DB --command \
  "SELECT destination, mechanism, COUNT(*) FROM zw_cdpa_transfer_log GROUP BY 1,2"
```

## Related

- `ghana-data-protection-act-workers-d1-compliance.md`
- `kenya-data-protection-act-workers-d1.md`
- `nigeria-ndpr-workers-d1.md`
- `south-africa-popia-workers-d1.md`
- `uganda-data-protection-privacy-act-workers.md`
- `cross-border-data-transfer-mechanisms.md`

## Sources

- Cyber and Data Protection Act [Chapter 12:07], Zimbabwe, signed 3 December 2021
- POTRAZ Cyber Security Centre Data Protection Guidelines, 2022
- IAPP Africa Privacy Law Overview — https://iapp.org
- ITU Zimbabwe ICT Regulation Profile — https://www.itu.int
