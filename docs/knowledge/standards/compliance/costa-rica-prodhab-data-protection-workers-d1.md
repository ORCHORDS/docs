# Costa Rica PRODHAB Data Protection — Cloudflare Workers & D1

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your SaaS product accepts sign-ups from Costa Rica. Legal counsel flags that Costa Rica has a
dedicated data-protection regulator (PRODHAB) and Law 8968 imposes consent, security, and
cross-border transfer rules. You need to know what changes to make in a Cloudflare Workers + D1
stack to reach a defensible compliance posture.

---

## Context

**Law 8968** ("Ley de Protección de la Persona Frente al Tratamiento de sus Datos Personales"),
enacted 2011, is Costa Rica's primary data-protection statute. The **Agencia de Protección de
Datos de los Habitantes (PRODHAB)** enforces it. Key obligations:

| Principle | Requirement |
|---|---|
| Consent | Explicit, informed, prior consent for non-vital processing |
| Purpose limitation | Data collected for a declared purpose only |
| Data quality | Accurate, up-to-date, adequate, not excessive |
| Security | Technical and organisational measures proportional to sensitivity |
| Cross-border transfers | Allowed only to countries with "adequate" protection or with PRODHAB authorisation |
| Database registration | Public and private databases containing personal data must be registered with PRODHAB |
| Rights | Access, rectification, cancellation, objection (ARCO) |

Sanctions reach up to **₡23 million CRC** (~USD 43 k at 2025 rates) per violation.

---

## Database Registration

Article 17 of Law 8968 requires registering every "base de datos" holding personal data with
PRODHAB. Registration is done via the PRODHAB online portal. Record the registration ID and
renewal date in your compliance tracker.

**Practical tip:** Register one database per logical processing purpose rather than one per D1
table. Group "marketing" tables separately from "billing" tables so you can demonstrate purpose
limitation.

---

## Consent Management in Workers KV

```typescript
// workers/consent.ts
interface CostaRicaConsent {
  userId: string;
  purposes: string[];       // e.g. ["analytics","marketing"]
  timestamp: string;        // ISO-8601
  ipCountry: string;        // from CF-IPCountry header
  consentVersion: string;   // must match current privacy-notice version
  registeredDatabase: string; // PRODHAB registration number
}

export async function recordCRConsent(
  env: Env,
  userId: string,
  purposes: string[],
  request: Request
): Promise<void> {
  const ipCountry = request.headers.get("CF-IPCountry") ?? "XX";

  const consent: CostaRicaConsent = {
    userId,
    purposes,
    timestamp: new Date().toISOString(),
    ipCountry,
    consentVersion: env.PRIVACY_NOTICE_VERSION,
    registeredDatabase: env.PRODHAB_DB_REGISTRATION_ID,
  };

  // Store in KV with 5-year TTL (retention limit)
  const ttl = 5 * 365 * 24 * 60 * 60;
  await env.CONSENT_KV.put(
    `cr:consent:${userId}`,
    JSON.stringify(consent),
    { expirationTtl: ttl }
  );
}

export async function hasCRConsent(
  env: Env,
  userId: string,
  purpose: string
): Promise<boolean> {
  const raw = await env.CONSENT_KV.get(`cr:consent:${userId}`);
  if (!raw) return false;
  const c = JSON.parse(raw) as CostaRicaConsent;
  return c.purposes.includes(purpose);
}
```

---

## D1 Schema — Personal Data Tracking

```sql
-- Track every personal-data attribute against its consent basis
CREATE TABLE IF NOT EXISTS cr_personal_data_inventory (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id       TEXT    NOT NULL,
  attribute     TEXT    NOT NULL,   -- e.g. "email","phone","dob"
  purpose       TEXT    NOT NULL,
  legal_basis   TEXT    NOT NULL DEFAULT 'consent',
  prodhab_db_id TEXT    NOT NULL,
  collected_at  TEXT    NOT NULL,
  expires_at    TEXT,               -- NULL = until consent withdrawn
  erased_at     TEXT
);

CREATE INDEX IF NOT EXISTS idx_cr_pdi_user ON cr_personal_data_inventory(user_id);
CREATE INDEX IF NOT EXISTS idx_cr_pdi_expires ON cr_personal_data_inventory(expires_at);
```

---

## ARCO Rights Handler (Workers)

```typescript
// workers/arco-handler.ts
export async function handleARCO(
  request: Request,
  env: Env
): Promise<Response> {
  const { userId, right } = await request.json<{
    userId: string;
    right: "access" | "rectification" | "cancellation" | "objection";
  }>();

  switch (right) {
    case "access":
      return handleAccess(userId, env);
    case "rectification":
      return handleRectification(userId, request, env);
    case "cancellation":
      return handleCancellation(userId, env);
    case "objection":
      return handleObjection(userId, env);
    default:
      return new Response("Unknown right", { status: 400 });
  }
}

async function handleCancellation(userId: string, env: Env): Promise<Response> {
  // Mark rows as erased; retain a tombstone for regulatory accountability
  await env.DB.prepare(`
    UPDATE cr_personal_data_inventory
    SET    erased_at = ?
    WHERE  user_id   = ?
    AND    erased_at IS NULL
  `).bind(new Date().toISOString(), userId).run();

  // Purge KV consent record
  await env.CONSENT_KV.delete(`cr:consent:${userId}`);

  // Log the erasure event
  await env.DB.prepare(`
    INSERT INTO audit_log (event_type, subject_id, performed_at, detail)
    VALUES ('CR_CANCELLATION', ?, ?, 'ARCO cancellation executed')
  `).bind(userId, new Date().toISOString()).run();

  return new Response(JSON.stringify({ status: "cancelled" }), {
    headers: { "Content-Type": "application/json" },
  });
}
```

---

## Cross-Border Transfer Gate

PRODHAB publishes a list of countries considered adequate. Before transferring personal data
outside Costa Rica to a non-adequate destination, you must obtain PRODHAB authorisation or use
Binding Corporate Rules.

```typescript
// workers/transfer-gate.ts
// Countries PRODHAB considers adequate (verify regularly against official list)
const CR_ADEQUATE_COUNTRIES = new Set([
  "AR","BR","CL","CO","MX","PE","UY", // LatAm with sectoral laws
  "AT","BE","BG","CY","CZ","DE","DK","EE","ES","FI","FR","GR","HR",
  "HU","IE","IT","LT","LU","LV","MT","NL","PL","PT","RO","SE","SI","SK",
  "GB","NO","IS","LI", // EEA/UK
  "CA","AU","NZ","JP","KR",
]);

export function checkCRTransferLegality(destinationCountry: string): boolean {
  return CR_ADEQUATE_COUNTRIES.has(destinationCountry.toUpperCase());
}

export async function transferGuard(
  env: Env,
  destinationCountry: string,
  dataCategories: string[]
): Promise<void> {
  if (!checkCRTransferLegality(destinationCountry)) {
    // Log attempted transfer for compliance audit
    await env.DB.prepare(`
      INSERT INTO transfer_attempts (destination, data_categories, blocked_at, reason)
      VALUES (?, ?, ?, 'CR_PRODHAB_NO_ADEQUACY')
    `).bind(
      destinationCountry,
      JSON.stringify(dataCategories),
      new Date().toISOString()
    ).run();

    throw new Error(
      `Transfer to ${destinationCountry} requires PRODHAB authorisation under Law 8968 Art. 21`
    );
  }
}
```

---

## Security Measures Required by Law 8968 Article 12

The law requires "necessary technical and organisational measures". For a Workers/D1 deployment:

```typescript
// workers/security-controls.ts

// 1. Encrypt sensitive fields before writing to D1
import { subtle } from "node:crypto";

export async function encryptField(
  plaintext: string,
  keyHex: string
): Promise<string> {
  const key = await subtle.importKey(
    "raw",
    Buffer.from(keyHex, "hex"),
    { name: "AES-GCM" },
    false,
    ["encrypt"]
  );
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ciphertext = await subtle.encrypt(
    { name: "AES-GCM", iv },
    key,
    new TextEncoder().encode(plaintext)
  );
  return Buffer.from(iv).toString("hex") + ":" +
         Buffer.from(ciphertext).toString("hex");
}

// 2. Rate-limit ARCO endpoints to prevent enumeration
export function arcoRateLimiter(request: Request): boolean {
  // Use Cloudflare Rate Limiting rules in wrangler.toml instead of in-band logic
  // This is a placeholder for documentation purposes
  return true;
}
```

---

## Anti-patterns

- **Skipping PRODHAB database registration.** Article 17 makes registration mandatory. Launching
  without registering exposes you to fines before any breach occurs.
- **Relying on legitimate interest for marketing.** Costa Rica's law requires explicit consent
  for most commercial communications; legitimate interest is not as broadly available as under
  GDPR.
- **Treating Costa Rican residents as EU residents.** ARCO ≠ GDPR DSAR. The workflows differ;
  PRODHAB has its own forms and timelines (10 business days for access, 5 for cancellation).
- **No Spanish-language privacy notice.** PRODHAB requires notices in Spanish accessible to the
  data subject.

---

## Gotchas

- The PRODHAB database registry requires renewal. Put a calendar reminder 30 days before
  expiry and store the expiry date in your compliance tracker.
- PRODHAB may conduct on-site inspections (Article 27). Maintain an offline copy of your
  processing records.
- Law 8968 applies to data processors established in Costa Rica **or** to processing of data
  relating to Costa Rican *inhabitants*, regardless of where the processor is located.
- The concept of "special categories" mirrors GDPR sensitive data; these require heightened
  justification.

---

## Verification

```bash
# 1. Confirm PRODHAB registration IDs are set in wrangler.toml secrets
wrangler secret list | grep PRODHAB

# 2. Verify D1 schema exists
wrangler d1 execute <DB_NAME> --command "SELECT * FROM cr_personal_data_inventory LIMIT 1"

# 3. Run ARCO cancellation test
curl -X POST https://your-worker.workers.dev/arco \
  -H "Content-Type: application/json" \
  -d '{"userId":"test-cr-001","right":"cancellation"}'

# 4. Verify transfer gate blocks non-adequate countries
wrangler dev &
curl -s -X POST http://localhost:8787/transfer-check \
  -d '{"destination":"CN","categories":["email"]}' | jq .
```

---

## Related

- `gdpr-consent-management-cloudflare-workers.md`
- `colombia-habeas-data-workers-d1-compliance.md`
- `peru-lpdp-workers-d1.md`
- `cross-border-data-transfer-mechanisms.md`
- `data-retention-automated-deletion-workers.md`

---

## Sources

- Law 8968 "Ley de Protección de la Persona Frente al Tratamiento de sus Datos Personales" (2011)
- PRODHAB Regulation 37554-JP
- PRODHAB official portal: https://www.prodhab.go.cr/
- Cloudflare Workers D1 docs: https://developers.cloudflare.com/d1/
