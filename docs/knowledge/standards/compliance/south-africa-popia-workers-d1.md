# South Africa POPIA Compliance on Cloudflare Workers and D1

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

example project has South African users whose personal information is protected by the Protection of Personal Information Act 4 of 2013 (POPIA), which became fully enforceable in July 2021. The platform must implement lawful processing grounds, data subject rights, and cross-border transfer safeguards or risk fines of up to ZAR 10 million and criminal liability for responsible parties.

## Context

POPIA is South Africa's comprehensive data protection law administered by the Information Regulator. It establishes eight conditions for lawful processing of personal information (PI): accountability, processing limitation, purpose specification, further processing limitation, information quality, openness, security safeguards, and data subject participation. For an anonymous social platform, the critical conditions are processing limitation (consent or legitimate interest must exist), security safeguards (technical and organisational measures), and data subject participation (access, correction, deletion). Cross-border transfers to Cloudflare's US-located data centres require that the destination country or recipient provides an adequate level of protection—practically achieved through binding corporate rules or contractual commitments.

## Condition 1 – Processing Limitation and Lawful Basis

Section 11 of POPIA requires at least one lawful processing ground. For example project, user-generated posts use consent; abuse detection uses legitimate interest. The lawful basis is recorded in D1 at collection time.

```typescript
// worker/popia-consent.ts
export type PopiaBasis =
  | "consent"
  | "contract"
  | "legitimate_interest"
  | "legal_obligation";

export interface ProcessingRecord {
  subjectRef: string;      // pseudonymous ID, not name
  purpose: string;
  basis: PopiaBasis;
  collectedAt: number;
  retentionDays: number;
}

export async function recordProcessingBasis(
  db: D1Database,
  record: ProcessingRecord,
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO popia_processing_records
         (subject_ref, purpose, basis, collected_at, retention_days)
       VALUES (?, ?, ?, ?, ?)`,
    )
    .bind(
      record.subjectRef,
      record.purpose,
      record.basis,
      record.collectedAt,
      record.retentionDays,
    )
    .run();
}

export async function getProcessingRecords(
  db: D1Database,
  subjectRef: string,
): Promise<ProcessingRecord[]> {
  const { results } = await db
    .prepare(
      `SELECT subject_ref, purpose, basis, collected_at, retention_days
         FROM popia_processing_records
        WHERE subject_ref = ?`,
    )
    .bind(subjectRef)
    .all<ProcessingRecord>();
  return results;
}
```

## Condition 7 – Security Safeguards

Section 19 requires appropriate, reasonable technical and organisational measures to prevent loss, damage, or unauthorised access. Personal information at rest in D1 is encrypted at the platform level using AES-GCM before insertion.

```typescript
// worker/popia-crypto.ts
const ALGORITHM = { name: "AES-GCM", length: 256 };

export async function importEncKey(rawBase64: string): Promise<CryptoKey> {
  const raw = Uint8Array.from(atob(rawBase64), (c) => c.charCodeAt(0));
  return crypto.subtle.importKey("raw", raw, ALGORITHM, false, [
    "encrypt",
    "decrypt",
  ]);
}

export async function encryptField(
  key: CryptoKey,
  plaintext: string,
): Promise<string> {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ct = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv },
    key,
    new TextEncoder().encode(plaintext),
  );
  // Store iv:ciphertext as base64 separated by "."
  const encode = (b: ArrayBuffer) =>
    btoa(String.fromCharCode(...new Uint8Array(b)));
  return `${encode(iv.buffer)}.${encode(ct)}`;
}

export async function decryptField(
  key: CryptoKey,
  encoded: string,
): Promise<string> {
  const [ivB64, ctB64] = encoded.split(".");
  const decode = (b64: string) =>
    Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  const plainBuf = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: decode(ivB64) },
    key,
    decode(ctB64),
  );
  return new TextDecoder().decode(plainBuf);
}
```

## Condition 8 – Data Subject Participation (Rights API)

Section 23 grants data subjects the right to access their information; section 24 grants the right to correction; section 24(2) grants the right to deletion. The example project rights API handles all three via a single Worker route.

```typescript
// worker/popia-rights.ts
export async function handlePopiaDsr(
  request: Request,
  db: D1Database,
  subjectRef: string,
): Promise<Response> {
  const { pathname } = new URL(request.url);

  if (request.method === "GET" && pathname === "/popia/access") {
    const { results } = await db
      .prepare(
        `SELECT post_id, created_at, content_hash
           FROM posts WHERE subject_ref = ? ORDER BY created_at DESC`,
      )
      .bind(subjectRef)
      .all();
    return Response.json({ data: results });
  }

  if (request.method === "PATCH" && pathname === "/popia/correct") {
    const { field, value } = await request.json<{ field: string; value: string }>();
    const ALLOWED_FIELDS = new Set(["display_name", "bio"]);
    if (!ALLOWED_FIELDS.has(field)) {
      return new Response("Field not correctable", { status: 422 });
    }
    await db
      .prepare(`UPDATE user_profiles SET ${field} = ? WHERE subject_ref = ?`)
      .bind(value, subjectRef)
      .run();
    return Response.json({ corrected: field });
  }

  if (request.method === "DELETE" && pathname === "/popia/delete") {
    await db.batch([
      db.prepare("DELETE FROM posts WHERE subject_ref = ?").bind(subjectRef),
      db.prepare("DELETE FROM user_profiles WHERE subject_ref = ?").bind(subjectRef),
      db.prepare("DELETE FROM popia_processing_records WHERE subject_ref = ?").bind(subjectRef),
    ]);
    return new Response(null, { status: 204 });
  }

  return new Response("Not Found", { status: 404 });
}
```

## Cross-Border Transfer Safeguards

Section 72 of POPIA restricts transfers of PI to other countries unless adequate protection exists. Cloudflare processes data in multiple regions; the example project Cloudflare Workers agreement must include Section 72-compliant data processing clauses. At runtime, a Cloudflare Smart Placement hint can confine processing to a South African PoP where latency allows, and the transfer record is logged.

```typescript
// worker/popia-transfer-log.ts
export async function logCrossBorderTransfer(
  db: D1Database,
  subjectRef: string,
  destinationCountry: string,
  safeguard: "contractual_clauses" | "adequacy_decision" | "consent",
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO popia_transfer_log
         (subject_ref, destination_country, safeguard, transferred_at)
       VALUES (?, ?, ?, ?)`,
    )
    .bind(subjectRef, destinationCountry, safeguard, Date.now())
    .run();
}
```

## Anti-patterns

- Storing clear-text email addresses or mobile numbers in D1 without field-level encryption violates Condition 7 and the reasonableness standard in section 19.
- Omitting a lawful processing basis record makes it impossible to demonstrate compliance during an Information Regulator investigation; silence is not a defence.
- Using a blanket consent checkbox that does not specify each processing purpose violates Condition 3 (purpose specification) and renders the consent invalid under section 11(1)(a).

## Gotchas

- POPIA's definition of "personal information" is broad and includes IP addresses, device identifiers, and online identifiers—even when the platform is "anonymous." Pseudonymous IDs that can be re-linked to an individual still count.
- The Information Regulator requires a designated Information Officer (IO) to be registered; failure to register the IO is a separate offence from data protection failures.

## Verification

```bash
# Confirm processing basis records exist for a test subject
wrangler d1 execute example project-prod \
  --command "SELECT * FROM popia_processing_records WHERE subject_ref = 'test-user-001';"

# Confirm transfer log entries include safeguard type
wrangler d1 execute example project-prod \
  --command "SELECT destination_country, safeguard FROM popia_transfer_log LIMIT 5;"

# Exercise the access right end-to-end
curl -si -H "Authorization: Bearer $TEST_TOKEN" \
  https://example project.example.com/popia/access | jq .
```

## Related

- `compliance/gdpr-data-subject-rights-api.md`
- `compliance/cross-border-data-transfer-mechanisms.md`
- `compliance/data-retention-automated-deletion-workers.md`

## Sources

- https://www.inforegulator.org.za/
- https://popia.co.za/ (unofficial consolidated text)
- https://www.gov.za/documents/protection-personal-information-act
