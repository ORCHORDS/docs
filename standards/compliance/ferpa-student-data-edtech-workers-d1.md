# FERPA: Student Education Record Compliance for EdTech APIs on Cloudflare Workers and D1

**Date:** 2026-08-22
**Author:** example.com
**Status:** production

---

## Symptom / Use-Case

You are building an EdTech SaaS (LMS, assessment tool, student portal) on Cloudflare Workers and D1. A U.S. school district signs a data-sharing agreement and immediately asks: "Are you FERPA-compliant?" Your legal team needs a written data-governance posture; your engineering team needs guard-rails in code before the first API key ships.

---

## Context

The **Family Educational Rights and Privacy Act** (20 U.S.C. § 1232g; 34 CFR Part 99) governs access to *education records* — any record directly related to a student that an educational institution maintains. Key obligations fall on **school officials** and their **contractors** (you, as a third-party *school official* acting under legitimate educational interest):

- Disclose records only with written consent or a FERPA exception.
- Maintain a disclosure log for records shared without consent.
- Honour parent/eligible-student access and correction requests within 45 days.
- Prohibit re-disclosure of records without written consent.
- Delete records when no longer needed for the contracted purpose.

Cloudflare's infrastructure does **not** carry a FERPA certification — FERPA compliance is a contractual and engineering responsibility of the application layer. Workers, D1, and R2 give you the primitives; this article shows you how to wire them together.

---

## Section 1 — Schema Design: Tagging Education Records in D1

Every row touching student PII must be labelled so automated controls can act on it.

```sql
-- migrations/001_ferpa_schema.sql
CREATE TABLE education_records (
  id          TEXT PRIMARY KEY,
  student_id  TEXT NOT NULL,
  institution_id TEXT NOT NULL,
  record_type TEXT NOT NULL CHECK(record_type IN (
    'grade','attendance','discipline','health','financial_aid','assessment'
  )),
  payload     TEXT NOT NULL,          -- AES-GCM encrypted JSON blob
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  deleted_at  TEXT,                   -- soft-delete for audit trail
  retention_days INTEGER NOT NULL DEFAULT 2555  -- 7-year default
);

CREATE TABLE disclosure_log (
  id              TEXT PRIMARY KEY,
  record_id       TEXT NOT NULL REFERENCES education_records(id),
  disclosed_to    TEXT NOT NULL,
  purpose         TEXT NOT NULL,
  ferpa_exception TEXT,              -- e.g. "school_official", "audit"
  consent_id      TEXT,              -- FK to consents table if applicable
  disclosed_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE student_consents (
  id             TEXT PRIMARY KEY,
  student_id     TEXT NOT NULL,
  institution_id TEXT NOT NULL,
  scope          TEXT NOT NULL,      -- JSON array of record_types covered
  granted_at     TEXT NOT NULL,
  revoked_at     TEXT,
  signed_by      TEXT NOT NULL       -- parent or eligible student (18+)
);

CREATE INDEX idx_er_student  ON education_records(student_id, deleted_at);
CREATE INDEX idx_dl_record   ON disclosure_log(record_id);
CREATE INDEX idx_sc_student  ON student_consents(student_id, institution_id);
```

---

## Section 2 — Encryption at the Application Layer

FERPA does not mandate encryption, but it requires "reasonable methods" to protect records. Encrypt before writing to D1; decrypt in the Worker on authorised read paths only.

```typescript
// src/ferpa/crypto.ts
const ALGORITHM = { name: 'AES-GCM', length: 256 };

export async function encryptRecord(
  plaintext: string,
  keyMaterial: string   // base64-encoded 256-bit key from env
): Promise<string> {
  const rawKey = Uint8Array.from(atob(keyMaterial), c => c.charCodeAt(0));
  const cryptoKey = await crypto.subtle.importKey('raw', rawKey, ALGORITHM, false, ['encrypt']);
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ciphertext = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv },
    cryptoKey,
    new TextEncoder().encode(plaintext)
  );
  // Encode iv + ciphertext together
  const combined = new Uint8Array(iv.byteLength + ciphertext.byteLength);
  combined.set(iv, 0);
  combined.set(new Uint8Array(ciphertext), iv.byteLength);
  return btoa(String.fromCharCode(...combined));
}

export async function decryptRecord(
  encoded: string,
  keyMaterial: string
): Promise<string> {
  const rawKey = Uint8Array.from(atob(keyMaterial), c => c.charCodeAt(0));
  const cryptoKey = await crypto.subtle.importKey('raw', rawKey, ALGORITHM, false, ['decrypt']);
  const combined = Uint8Array.from(atob(encoded), c => c.charCodeAt(0));
  const iv = combined.slice(0, 12);
  const ciphertext = combined.slice(12);
  const plaintext = await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, cryptoKey, ciphertext);
  return new TextDecoder().decode(plaintext);
}
```

Store `FERPA_ENCRYPTION_KEY` as a Cloudflare Workers secret (`wrangler secret put FERPA_ENCRYPTION_KEY`). Rotate the key annually; re-encrypt in a background migration Worker.

---

## Section 3 — Role-Based Access Control and Legitimate Educational Interest Gate

FERPA allows disclosure to "school officials with a legitimate educational interest." Your Worker must enforce this before returning any record.

```typescript
// src/ferpa/access-control.ts
export type FerpaRole = 'teacher' | 'counselor' | 'admin' | 'parent' | 'student' | 'third_party';

const ROLE_RECORD_PERMISSIONS: Record<FerpaRole, string[]> = {
  teacher:     ['grade', 'attendance', 'assessment'],
  counselor:   ['grade', 'attendance', 'discipline', 'health', 'assessment'],
  admin:       ['grade', 'attendance', 'discipline', 'health', 'financial_aid', 'assessment'],
  parent:      ['grade', 'attendance', 'discipline', 'health', 'financial_aid', 'assessment'],
  student:     ['grade', 'attendance', 'assessment'],        // eligible students (18+)
  third_party: [],   // always requires explicit consent
};

export function hasLegitimateInterest(
  role: FerpaRole,
  recordType: string,
  purposeJustification: string
): boolean {
  const allowed = ROLE_RECORD_PERMISSIONS[role] ?? [];
  return allowed.includes(recordType) && purposeJustification.length > 0;
}

// src/ferpa/middleware.ts
import { hasLegitimateInterest } from './access-control';

export async function ferpaGuard(
  request: Request,
  env: Env,
  studentId: string,
  recordType: string
): Promise<Response | null> {
  const token = request.headers.get('Authorization')?.replace('Bearer ', '');
  if (!token) return new Response('Unauthorized', { status: 401 });

  // Verify JWT — your existing auth layer
  const claims = await verifyJwt(token, env.JWT_SECRET);
  if (!claims) return new Response('Forbidden', { status: 403 });

  const purpose = request.headers.get('X-Ferpa-Purpose') ?? '';
  if (!hasLegitimateInterest(claims.role as FerpaRole, recordType, purpose)) {
    return new Response(JSON.stringify({
      error: 'FERPA_ACCESS_DENIED',
      message: `Role '${claims.role}' lacks legitimate educational interest for '${recordType}' records`,
    }), { status: 403, headers: { 'Content-Type': 'application/json' } });
  }

  // Write disclosure log entry (fire-and-forget to avoid latency on hot path)
  env.ctx.waitUntil(logDisclosure(env.DB, studentId, recordType, claims, purpose));

  return null;  // access granted
}
```

---

## Section 4 — Disclosure Log Writer and Retention Enforcement

```typescript
// src/ferpa/disclosure-log.ts
import { nanoid } from 'nanoid';

export async function logDisclosure(
  db: D1Database,
  recordId: string,
  disclosedTo: string,
  purpose: string,
  ferpaException: string,
  consentId?: string
): Promise<void> {
  await db.prepare(`
    INSERT INTO disclosure_log (id, record_id, disclosed_to, purpose, ferpa_exception, consent_id, disclosed_at)
    VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
  `).bind(nanoid(), recordId, disclosedTo, purpose, ferpaException, consentId ?? null).run();
}

// Scheduled Worker: purge records past retention window
// wrangler.toml: [triggers] crons = ["0 3 * * *"]
export async function handleRetentionPurge(env: Env): Promise<void> {
  const result = await env.DB.prepare(`
    UPDATE education_records
    SET deleted_at = datetime('now'), payload = '[PURGED]'
    WHERE deleted_at IS NULL
      AND julianday('now') - julianday(created_at) > retention_days
  `).run();

  console.log(`FERPA retention purge: ${result.meta.changes} records soft-deleted`);
}
```

---

## Section 5 — Student / Parent Access Request Handler (45-Day Window)

FERPA requires institutions to provide access to education records within 45 days of a request.

```typescript
// src/ferpa/access-request.ts
export async function handleAccessRequest(request: Request, env: Env): Promise<Response> {
  const { studentId, institutionId, requestedBy } = await request.json<{
    studentId: string; institutionId: string; requestedBy: 'parent' | 'student';
  }>();

  const deadline = new Date();
  deadline.setDate(deadline.getDate() + 45);

  // Retrieve all non-purged records
  const { results } = await env.DB.prepare(`
    SELECT id, record_type, created_at
    FROM education_records
    WHERE student_id = ? AND institution_id = ? AND deleted_at IS NULL
    ORDER BY created_at DESC
  `).bind(studentId, institutionId).all();

  // Queue fulfillment task — actual decryption done in secure background job
  await env.FERPA_QUEUE.send({
    type: 'ACCESS_REQUEST',
    studentId,
    institutionId,
    requestedBy,
    recordIds: results.map(r => r.id),
    deadlineIso: deadline.toISOString(),
    requestedAt: new Date().toISOString(),
  });

  return Response.json({
    status: 'queued',
    recordCount: results.length,
    deadline: deadline.toISOString(),
    message: 'You will receive your records within 45 days as required by FERPA.',
  });
}
```

---

## Section 6 — Data Sharing Agreement Enforcement at API Gateway

Third-party vendors receiving student data must have a signed FERPA-compliant data sharing agreement on file.

```typescript
// src/ferpa/dsa-gate.ts
export async function dssGate(request: Request, env: Env): Promise<Response | null> {
  const apiKey = <redacted-secret>'X-Api-Key');
  if (!apiKey) return new Response('Missing API key', { status: 401 });

  const vendor = await env.DB.prepare(`
    SELECT v.id, v.name, v.dsa_signed_at, v.dsa_expires_at, v.allowed_record_types
    FROM vendors v
    JOIN vendor_api_keys k ON k.vendor_id = v.id
    WHERE k.key_hash = ? AND k.revoked_at IS NULL
  `).bind(await hashKey(apiKey)).first<{
    id: string; name: string; dsa_signed_at: string;
    dsa_expires_at: string; allowed_record_types: string;
  }>();

  if (!vendor) return new Response('Invalid API key', { status: 401 });

  const dsaExpiry = new Date(vendor.dsa_expires_at);
  if (dsaExpiry < new Date()) {
    return Response.json({
      error: 'DSA_EXPIRED',
      message: `Data sharing agreement with ${vendor.name} expired ${vendor.dsa_expires_at}. Renew before accessing student records.`,
    }, { status: 403 });
  }

  return null;  // proceed
}

async function hashKey(key: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(key));
  return Array.from(new Uint8Array(digest)).map(b => b.toString(16).padStart(2, '0')).join('');
}
```

---

## Anti-Patterns

- **Logging full PII in Cloudflare logpush** — Logpush events flow to third-party sinks (e.g. Datadog) that are not your FERPA sub-processors. Strip student identifiers before logging; use opaque IDs.
- **Storing unencrypted records in D1** — D1 encryption at rest is Cloudflare infrastructure encryption; FERPA requires you to control the keys. Encrypt at the application layer.
- **Sharing `student_id` with analytics Workers** — Any integration that receives an education record must appear in your DSA inventory.
- **Treating FERPA as consent-first by default** — School consent for data sharing is generally not from the student/parent; it flows from the institution's legitimate educational interest exception. Never prompt students to "consent" to your data use in lieu of a proper DSA with the institution.

---

## Gotchas

- **Eligible students (≥18) supersede parental rights** — Your access-request handler must check age at request time, not at enrolment time.
- **Directory information is still restricted unless the school has opted in** — Do not expose student names, email addresses, or photos as "public" without confirming the institution's FERPA directory information policy.
- **Annual notification requirement is the institution's, not yours** — You must contractually enable institutions to meet it (e.g. by providing a data inventory on request).
- **FERPA does not pre-empt state student privacy laws** — California's SOPIPA, New York Ed Law §2-d, and others impose stricter obligations. Build the stricter controls.

---

## Verification Checklist

- [ ] All `education_records` rows have `deleted_at` enforcement via a scheduled Cron Trigger.
- [ ] Every read path calls `ferpaGuard()` before decrypting payload.
- [ ] `disclosure_log` entries are written on every authorised record access.
- [ ] DSA expiry check in `dsa-gate.ts` is enforced for all third-party API keys.
- [ ] `FERPA_ENCRYPTION_KEY` is stored as a Wrangler secret, not in `wrangler.toml`.
- [ ] Vendor table lists all D1/R2/Queue consumers and their DSA dates.
- [ ] Access request handler queues fulfillment within 45-day window.
- [ ] Logpush filter strips `student_id` from forwarded events.

---

## Related Articles

- `data-minimization-workers-d1-pii-redaction.md`
- `gdpr-data-subject-rights-api.md`
- `hipaa-technical-safeguards-web-api.md`
- `data-retention-automated-deletion-workers.md`
- `childrens-privacy-2026-coppa-2-state-laws.md`

---

## Sources

- 20 U.S.C. § 1232g (FERPA statute)
- 34 CFR Part 99 (FERPA regulations)
- U.S. Dept of Education FERPA guidance: https://studentprivacy.ed.gov/
- PTAC: Data Sharing Agreements under FERPA (2023)
- California SOPIPA (Bus. & Prof. Code § 22584)
- New York Ed Law § 2-d and Part 121
- Cloudflare D1 documentation: https://developers.cloudflare.com/d1/
- Cloudflare Workers Secrets: https://developers.cloudflare.com/workers/configuration/secrets/
