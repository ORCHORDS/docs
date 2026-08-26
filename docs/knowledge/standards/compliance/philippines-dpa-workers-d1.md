# Philippines Data Privacy Act Compliance on Cloudflare Workers and D1

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

example project reaches Filipino users whose personal information is protected by Republic Act 10173, the Data Privacy Act of 2012 (DPA), enforced by the National Privacy Commission (NPC). Non-compliance exposes the platform to imprisonment terms for responsible officers and fines up to PHP 5 million per violation. The NPC's 2023 Implementing Rules and Regulations (IRR) update tightened consent standards and added mandatory privacy management programmes.

## Context

The Philippines DPA closely mirrors GDPR in structure: lawful basis, data subject rights (access, correction, erasure, data portability, object), privacy-by-design obligations, and a Data Protection Officer (DPO) requirement for processors handling personal information of at least 250 individuals or sensitive personal information of any number. Unlike GDPR, the Philippines DPA maintains a criminal liability framework alongside administrative penalties, making officer-level accountability significant. For an anonymous social platform, the principal obligations are lawful collection under section 12 (or section 13 for sensitive PI), a mandatory DPO registration with the NPC, breach notification within 72 hours, and a Privacy Management Programme (PMP) documented under NPC Circular 16-01.

## Lawful Basis and Consent Mechanics

Section 12 of the DPA enumerates six lawful criteria for processing personal information; consent (section 12(a)) is the default for social platforms. Consent must be "evidenced by written, electronic or recorded means." The example project Worker records consent with a structured evidence object meeting NPC evidentiary requirements.

```typescript
// worker/ph-dpa-consent.ts
export type DpaLawfulBasis =
  | "consent"               // s.12(a)
  | "contract"              // s.12(b)
  | "legal_obligation"      // s.12(c)
  | "vital_interests"       // s.12(d)
  | "public_interest"       // s.12(e)
  | "legitimate_interests"; // s.12(f)

export interface DpaConsentEvidence {
  subjectRef: string;
  purposeCode: string;
  lawfulBasis: DpaLawfulBasis;
  consentText: string;        // exact wording shown to user
  consentTextHash: string;    // SHA-256 of consentText for tamper-evidence
  consentedAt: number;
  channel: "web" | "mobile" | "api";
  ipHash: string;
  withdrawnAt: number | null;
}

export async function recordDpaConsent(
  db: D1Database,
  evidence: DpaConsentEvidence,
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO ph_dpa_consents
         (subject_ref, purpose_code, lawful_basis, consent_text, consent_text_hash,
          consented_at, channel, ip_hash, withdrawn_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
       ON CONFLICT (subject_ref, purpose_code)
       DO UPDATE SET
         lawful_basis       = excluded.lawful_basis,
         consent_text       = excluded.consent_text,
         consent_text_hash  = excluded.consent_text_hash,
         consented_at       = excluded.consented_at,
         channel            = excluded.channel,
         ip_hash            = excluded.ip_hash,
         withdrawn_at       = NULL`,
    )
    .bind(
      evidence.subjectRef,
      evidence.purposeCode,
      evidence.lawfulBasis,
      evidence.consentText,
      evidence.consentTextHash,
      evidence.consentedAt,
      evidence.channel,
      evidence.ipHash,
      evidence.withdrawnAt,
    )
    .run();
}

export async function withdrawConsent(
  db: D1Database,
  subjectRef: string,
  purposeCode: string,
): Promise<void> {
  await db
    .prepare(
      `UPDATE ph_dpa_consents
          SET withdrawn_at = ?
        WHERE subject_ref = ? AND purpose_code = ? AND withdrawn_at IS NULL`,
    )
    .bind(Date.now(), subjectRef, purposeCode)
    .run();
}
```

## Data Subject Rights Implementation

Sections 16–20 of the DPA provide rights to be informed, to object, to access, to rectification, to erasure/blocking, and to data portability. The rights router handles all five in a single Worker middleware.

```typescript
// worker/ph-dpa-rights.ts
export async function handleDpaRightsRequest(
  request: Request,
  db: D1Database,
  subjectRef: string,
): Promise<Response | null> {
  const url = new URL(request.url);

  // Right to Access (s.16(c))
  if (request.method === "GET" && url.pathname === "/ph-dpa/access") {
    const [profile, posts, consents] = await Promise.all([
      db.prepare("SELECT * FROM user_profiles WHERE subject_ref = ?").bind(subjectRef).first(),
      db.prepare("SELECT post_id, created_at FROM posts WHERE subject_ref = ?").bind(subjectRef).all(),
      db.prepare("SELECT purpose_code, lawful_basis, consented_at FROM ph_dpa_consents WHERE subject_ref = ?")
        .bind(subjectRef).all(),
    ]);
    return Response.json({ profile, posts: posts.results, consents: consents.results });
  }

  // Right to Rectification (s.16(d))
  if (request.method === "PATCH" && url.pathname === "/ph-dpa/rectify") {
    const { field, value } = await request.json<{ field: string; value: string }>();
    const ALLOWED = new Set(["display_name", "bio"]);
    if (!ALLOWED.has(field)) return new Response("Not rectifiable", { status: 422 });
    await db.prepare(`UPDATE user_profiles SET ${field} = ? WHERE subject_ref = ?`)
      .bind(value, subjectRef).run();
    return Response.json({ rectified: field });
  }

  // Right to Erasure / Blocking (s.16(e))
  if (request.method === "DELETE" && url.pathname === "/ph-dpa/erase") {
    await db.batch([
      db.prepare("DELETE FROM posts WHERE subject_ref = ?").bind(subjectRef),
      db.prepare("DELETE FROM user_profiles WHERE subject_ref = ?").bind(subjectRef),
      db.prepare("UPDATE ph_dpa_consents SET withdrawn_at = ? WHERE subject_ref = ?")
        .bind(Date.now(), subjectRef),
    ]);
    return new Response(null, { status: 204 });
  }

  // Right to Data Portability (s.16(f))
  if (request.method === "GET" && url.pathname === "/ph-dpa/portability") {
    const posts = await db
      .prepare("SELECT post_id, content_hash, created_at FROM posts WHERE subject_ref = ?")
      .bind(subjectRef).all();
    const export_ = {
      format: "application/json",
      generatedAt: new Date().toISOString(),
      regulation: "PH DPA s.16(f)",
      data: posts.results,
    };
    return new Response(JSON.stringify(export_), {
      headers: { "Content-Type": "application/json" },
    });
  }

  return null; // Not a DPA rights path
}
```

## Sensitive Personal Information Controls

Section 13 of the DPA requires explicit written consent or specific statutory grounds for processing sensitive personal information (SPI), which includes racial/ethnic origin, health data, religious beliefs, and government-issued ID numbers. example project must flag and gate any SPI collection.

```typescript
// worker/ph-dpa-spi.ts
export const SPI_FIELDS = new Set([
  "race", "ethnicity", "religion", "health_status",
  "sexual_orientation", "government_id", "biometric_data",
]) as ReadonlySet<string>;

export function containsSpi(data: Record<string, unknown>): boolean {
  return Object.keys(data).some((k) => SPI_FIELDS.has(k));
}

export async function assertSpiConsent(
  db: D1Database,
  subjectRef: string,
  purposeCode: string,
): Promise<void> {
  const row = await db
    .prepare(
      `SELECT lawful_basis, withdrawn_at FROM ph_dpa_consents
        WHERE subject_ref = ? AND purpose_code = ?`,
    )
    .bind(subjectRef, purposeCode)
    .first<{ lawful_basis: string; withdrawn_at: number | null }>();

  if (!row || row.withdrawn_at !== null) {
    throw Object.assign(new Error("No valid SPI consent"), { status: 403 });
  }
  if (row.lawful_basis !== "consent") {
    // SPI requires explicit consent under s.13; legitimate interest is insufficient
    throw Object.assign(
      new Error("SPI requires explicit consent basis, not " + row.lawful_basis),
      { status: 403 },
    );
  }
}
```

## Breach Notification – NPC 72-Hour Requirement

NPC Circular 16-03 (as amended) requires notification to the NPC within 72 hours of a breach likely to give rise to a real risk of serious harm. Affected data subjects must be notified without undue delay.

```typescript
// worker/ph-dpa-breach.ts
export async function registerBreachIncident(
  db: D1Database,
  queue: Queue,
  opts: {
    description: string;
    affectedCount: number;
    spiInvolved: boolean;
    discoveredAt: number;
  },
): Promise<string> {
  const id = crypto.randomUUID();
  const npcDeadline = opts.discoveredAt + 72 * 60 * 60 * 1000;

  await db
    .prepare(
      `INSERT INTO breach_incidents
         (id, description, affected_count, spi_involved, discovered_at, npc_deadline_ms, status)
       VALUES (?, ?, ?, ?, ?, ?, 'open')`,
    )
    .bind(id, opts.description, opts.affectedCount, opts.spiInvolved ? 1 : 0,
      opts.discoveredAt, npcDeadline)
    .run();

  await queue.send({ type: "ph_dpa_breach", incidentId: id, npcDeadline, spiInvolved: opts.spiInvolved });
  return id;
}
```

## Anti-patterns

- Bundling sensitive personal information collection into a general platform-use consent; the DPA and NPC guidance require a separate, explicit consent item for each SPI category.
- Failing to register the DPO with the NPC within 30 days of appointment; NPC's online DPO registration is mandatory and public.
- Treating consent withdrawal as prospective only while continuing to process already-collected data under the original consent after withdrawal; the NPC interprets withdrawal as triggering immediate cessation of processing and deletion.

## Gotchas

- The Philippines DPA applies extraterritorially to any entity that uses equipment located in the Philippines or employs Philippine nationals to process data—even for foreign users. This is broader than the GDPR targeting rule.
- The NPC's definition of "personal information controller" (PIC) and "personal information processor" (PIP) determines liability allocation. Operating example project through a Cloudflare Workers deployment requires a Data Processing Agreement designating Cloudflare as PIP.

## Verification

```bash
# Check consent evidence records
wrangler d1 execute example project-prod \
  --command "SELECT purpose_code, lawful_basis, consent_text_hash FROM ph_dpa_consents WHERE subject_ref = 'test-ph-001';"

# Confirm breach incidents table exists and NPC deadline is populated
wrangler d1 execute example project-prod \
  --command "SELECT id, affected_count, spi_involved, npc_deadline_ms FROM breach_incidents ORDER BY discovered_at DESC LIMIT 3;"

# Exercise portability endpoint
curl -si -H "Authorization: Bearer $TEST_TOKEN" \
  https://example project.example.com/ph-dpa/portability | jq .format
```

## Related

- `compliance/gdpr-data-subject-rights-api.md`
- `compliance/gdpr-breach-notification-72h.md`
- `compliance/appi-japan-compliance.md`

## Sources

- https://privacy.gov.ph/data-privacy-act/
- https://www.officialgazette.gov.ph/2012/08/15/republic-act-no-10173/
- https://privacy.gov.ph/circulars/
