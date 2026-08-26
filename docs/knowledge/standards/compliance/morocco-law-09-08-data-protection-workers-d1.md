# Morocco Law 09-08 Data Protection — Cloudflare Workers & D1

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your application serves users in Morocco. Your legal team has flagged **Law 09-08** (promulgated
February 2009) and its enforcement body, the **Commission Nationale de contrôle de la protection
des Données à caractère Personnel (CNDP)**. You need to understand the filing requirements,
consent model, and cross-border rules, then implement them in a Cloudflare Workers + D1 stack.

---

## Context

Morocco's Law 09-08 on the Protection of Individuals with regard to the Processing of Personal
Data is heavily influenced by the EU Data Protection Directive 95/46/EC. Morocco was the
**first African country** to obtain adequacy recognition from the EU Council of Europe
(Convention 108). Key obligations:

| Obligation | Detail |
|---|---|
| Declaration / Authorisation | Controllers must declare processing to CNDP or obtain prior authorisation for sensitive data |
| Consent | Required for most processing; sensitive data needs explicit written consent |
| Data quality | Accurate, adequate, relevant, not excessive for the declared purpose |
| Security | Technical and organisational measures; Article 23 |
| Cross-border transfers | Only to countries with an adequate level of protection |
| Individual rights | Access, rectification, deletion, objection |
| Breach notification | No statutory 72-hour clock, but notify CNDP promptly in practice |

**Fines:** Articles 52–69 set criminal penalties up to **MAD 300 000** and/or imprisonment
for serious violations.

---

## CNDP Declaration vs. Authorisation

| Processing type | Filing needed |
|---|---|
| Ordinary processing (non-sensitive) | Simple declaration (Déclaration) |
| Sensitive data, biometrics, criminal records | Prior authorisation (Autorisation préalable) |
| Research/statistics | Simplified authorisation |
| Video surveillance | Specific authorisation |

Store your CNDP declaration/authorisation numbers as environment secrets:

```toml
# wrangler.toml
[vars]
MA_CNDP_DECLARATION_ID = "MA-DECL-2026-XXXXXX"
MA_PROCESSING_REGISTER_VERSION = "1.0"
```

---

## D1 Schema — Processing Register

```sql
-- Processing activities register required by Law 09-08 Article 15
CREATE TABLE IF NOT EXISTS ma_processing_register (
  id                   INTEGER PRIMARY KEY AUTOINCREMENT,
  processing_name      TEXT    NOT NULL,
  cndp_reference       TEXT    NOT NULL,   -- declaration or authorisation number
  legal_basis          TEXT    NOT NULL,   -- 'consent' | 'contract' | 'legal_obligation' | 'vital_interest'
  data_categories      TEXT    NOT NULL,   -- JSON array
  purposes             TEXT    NOT NULL,   -- JSON array
  recipients           TEXT,              -- JSON array (internal/external)
  retention_days       INTEGER,
  cross_border         INTEGER DEFAULT 0,  -- 1 if data transferred outside Morocco
  cross_border_country TEXT,
  created_at           TEXT    NOT NULL,
  updated_at           TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS ma_consent_log (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id          TEXT    NOT NULL,
  purpose          TEXT    NOT NULL,
  language         TEXT    NOT NULL DEFAULT 'fr', -- 'fr' | 'ar'
  consent_given    INTEGER NOT NULL,  -- 1 = yes, 0 = no
  notice_version   TEXT    NOT NULL,
  ip_country       TEXT,
  recorded_at      TEXT    NOT NULL,
  withdrawn_at     TEXT
);

CREATE INDEX IF NOT EXISTS idx_ma_consent_user ON ma_consent_log(user_id);
```

---

## Consent Recording Worker

```typescript
// workers/ma-consent.ts
export interface MoroccoConsentPayload {
  userId: string;
  purpose: string;
  language: "fr" | "ar";
  noticeVersion: string;
}

export async function recordMoroccoConsent(
  env: Env,
  payload: MoroccoConsentPayload,
  request: Request
): Promise<void> {
  const ipCountry = request.headers.get("CF-IPCountry") ?? "XX";

  await env.DB.prepare(`
    INSERT INTO ma_consent_log
      (user_id, purpose, language, consent_given, notice_version, ip_country, recorded_at)
    VALUES (?, ?, ?, 1, ?, ?, ?)
  `).bind(
    payload.userId,
    payload.purpose,
    payload.language,
    payload.noticeVersion,
    ipCountry,
    new Date().toISOString()
  ).run();
}

export async function withdrawMoroccoConsent(
  env: Env,
  userId: string,
  purpose: string
): Promise<void> {
  await env.DB.prepare(`
    UPDATE ma_consent_log
    SET    withdrawn_at = ?
    WHERE  user_id      = ?
    AND    purpose      = ?
    AND    withdrawn_at IS NULL
  `).bind(new Date().toISOString(), userId, purpose).run();
}

export async function hasActiveConsent(
  env: Env,
  userId: string,
  purpose: string
): Promise<boolean> {
  const row = await env.DB.prepare(`
    SELECT id FROM ma_consent_log
    WHERE  user_id     = ?
    AND    purpose     = ?
    AND    consent_given = 1
    AND    withdrawn_at  IS NULL
    ORDER  BY recorded_at DESC
    LIMIT  1
  `).bind(userId, purpose).first();
  return row !== null;
}
```

---

## Cross-Border Transfer Gate

Morocco is a party to Council of Europe Convention 108 and is on the EU's list of adequate
countries. However, when Morocco-resident data is transferred **out of Morocco** to a non-adequate
country, CNDP authorisation is required under Article 43.

```typescript
// workers/ma-transfer-gate.ts

// Countries CNDP considers adequate (Convention 108 signatories + EU adequacy)
// Always verify against https://www.cndp.ma before finalising
const MA_ADEQUATE_COUNTRIES = new Set([
  // EU/EEA
  "AT","BE","BG","CY","CZ","DE","DK","EE","ES","FI","FR","GR","HR",
  "HU","IE","IT","LT","LU","LV","MT","NL","PL","PT","RO","SE","SI","SK",
  "NO","IS","LI",
  // Convention 108 parties
  "GB","CH","AD","BA","GE","MD","ME","MK","RS","TR","UA","AM","AZ",
  // Other CNDP-approved
  "CA","AU","NZ","JP","AR","UY","IL",
]);

export function isMoroccoTransferPermitted(destinationCountry: string): boolean {
  return MA_ADEQUATE_COUNTRIES.has(destinationCountry.toUpperCase());
}

export async function assertMoroccoTransferPermitted(
  env: Env,
  destinationCountry: string,
  processingName: string
): Promise<void> {
  if (!isMoroccoTransferPermitted(destinationCountry)) {
    await env.DB.prepare(`
      INSERT INTO transfer_block_log
        (destination_country, processing_name, blocked_at, law_reference)
      VALUES (?, ?, ?, 'MA_LAW_09-08_ART43')
    `).bind(destinationCountry, processingName, new Date().toISOString()).run();

    throw new Error(
      `Cross-border transfer to ${destinationCountry} blocked: ` +
      `CNDP authorisation required under Law 09-08 Article 43.`
    );
  }
}
```

---

## Individual Rights Handler (Droits d'accès / Rectification / Suppression)

```typescript
// workers/ma-rights.ts
type MARightType = "access" | "rectification" | "deletion" | "objection";

export async function handleMoroccoRight(
  env: Env,
  userId: string,
  right: MARightType,
  details?: Record<string, unknown>
): Promise<Response> {
  const ref = `MA-${right.toUpperCase()}-${Date.now()}`;

  await env.DB.prepare(`
    INSERT INTO rights_requests
      (reference, user_id, right_type, jurisdiction, status, submitted_at)
    VALUES (?, ?, ?, 'MA', 'pending', ?)
  `).bind(ref, userId, right, new Date().toISOString()).run();

  if (right === "deletion") {
    // Soft-delete personal data; retain reference for CNDP accountability
    await env.DB.prepare(`
      UPDATE ma_consent_log
      SET    withdrawn_at = ?
      WHERE  user_id = ? AND withdrawn_at IS NULL
    `).bind(new Date().toISOString(), userId).run();
  }

  // Deadline: 30 days under Law 09-08 Article 10
  const deadline = new Date();
  deadline.setDate(deadline.getDate() + 30);

  return new Response(JSON.stringify({
    reference: ref,
    status: "pending",
    deadlineIso: deadline.toISOString(),
  }), { headers: { "Content-Type": "application/json" } });
}
```

---

## Anti-patterns

- **Skipping CNDP declaration before launch.** Unlike GDPR where you maintain an internal
  register, Morocco requires an **external filing** with CNDP. Going live without it is an
  immediate violation.
- **Using an English-only privacy notice.** Morocco requires notices to be accessible; French
  and/or Arabic are expected. CNDP publishes model notices in both languages.
- **Assuming EU-style legitimate interest applies.** Law 09-08 relies more heavily on consent
  and has a narrower list of processing bases than GDPR Article 6.
- **Storing sensitive data (health, religion, political opinions) without prior authorisation.**
  Declaration is not sufficient for sensitive categories; authorisation préalable is required.

---

## Gotchas

- Morocco updated its approach to align with GDPR via a proposed 2024 reform bill. Monitor
  CNDP publications — requirements may tighten on breach notification timelines.
- CNDP declarations must be renewed or updated when the processing purpose, data categories,
  or transfer destinations change materially.
- Law 09-08 applies to controllers **established in Morocco** or where the processing means are
  located in Morocco. Cloud hosting outside Morocco does not exempt you if you target Moroccan
  residents and operate locally.
- The right-of-access response deadline is **30 days**, not the 30-day GDPR standard — confirm
  this when setting SLA clocks.

---

## Verification

```bash
# 1. Check secrets present
wrangler secret list | grep MA_CNDP

# 2. Verify consent schema
wrangler d1 execute <DB> --command \
  "SELECT COUNT(*) FROM ma_consent_log"

# 3. Test consent recording
curl -X POST https://your-worker.workers.dev/consent/ma \
  -H "Content-Type: application/json" \
  -d '{"userId":"ma-test-001","purpose":"analytics","language":"fr","noticeVersion":"1.0"}'

# 4. Test transfer gate
curl -X POST https://your-worker.workers.dev/transfer-check \
  -H "Content-Type: application/json" \
  -d '{"destination":"US","processing":"user-profiles"}' | jq .
```

---

## Related

- `gdpr-consent-management-cloudflare-workers.md`
- `cross-border-data-transfer-mechanisms.md`
- `nigeria-ndpr-workers-d1.md`
- `egypt-personal-data-protection-law-workers.md`
- `data-retention-automated-deletion-workers.md`

---

## Sources

- Law 09-08 on Protection of Individuals with regard to the Processing of Personal Data (Morocco, 2009)
- CNDP official site: https://www.cndp.ma/
- Council of Europe Convention 108 signatories list
- CNDP model privacy notices and filing guides
- Cloudflare Workers KV & D1 docs: https://developers.cloudflare.com/
