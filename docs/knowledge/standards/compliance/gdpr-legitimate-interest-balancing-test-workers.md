# GDPR Legitimate Interest Balancing Test on Cloudflare Workers

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

example project processes pseudonymous user data for fraud detection, spam prevention, and abuse reporting without prompting users for explicit consent—relying instead on GDPR Article 6(1)(f) legitimate interest. Without a documented, per-purpose balancing test (LIA) and a runtime enforcement mechanism, the legal basis is unenforceable and supervisory authorities can order processing to stop immediately.

## Context

Article 6(1)(f) of GDPR permits processing where it is "necessary for the purposes of the legitimate interests pursued by the controller or by a third party, except where such interests are overridden by the interests or fundamental rights and freedoms of the data subject." The EDPB's Guidelines 1/2024 on legitimate interest formalise a three-part test: (1) identify a legitimate interest, (2) demonstrate necessity (no less invasive means), and (3) show the interest is not overridden by individual rights via a balancing test. Each processing purpose needs its own LIA documented in the Record of Processing Activities (RoPA). On Cloudflare Workers and D1, the LIA outcome is stored as a compliance artefact, and the runtime gate enforces the recorded decision before any legitimate-interest processing executes.

## LIA Record Schema and Storage

Each legitimate-interest processing purpose is pre-approved by the DPO and stored in D1 as a signed LIA record. The signing key is held in Workers Secrets and rotated quarterly.

```typescript
// worker/lia-store.ts
export interface LiaRecord {
  purposeCode: string;
  legitimateInterest: string;    // what interest is pursued
  necessityJustification: string; // why less invasive means don't suffice
  balancingOutcome: "approved" | "rejected";
  mitigations: string[];         // measures that tipped the balance
  approvedBy: string;            // DPO identifier
  approvedAt: number;
  expiresAt: number;             // LIAs must be reviewed periodically
  hmacSignature: string;         // HMAC-SHA256 over canonical JSON
}

export async function storeLia(
  db: D1Database,
  record: LiaRecord,
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO lia_records
         (purpose_code, legitimate_interest, necessity_justification,
          balancing_outcome, mitigations, approved_by, approved_at,
          expires_at, hmac_signature)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
       ON CONFLICT (purpose_code) DO UPDATE SET
         legitimate_interest       = excluded.legitimate_interest,
         necessity_justification   = excluded.necessity_justification,
         balancing_outcome         = excluded.balancing_outcome,
         mitigations               = excluded.mitigations,
         approved_by               = excluded.approved_by,
         approved_at               = excluded.approved_at,
         expires_at                = excluded.expires_at,
         hmac_signature            = excluded.hmac_signature`,
    )
    .bind(
      record.purposeCode,
      record.legitimateInterest,
      record.necessityJustification,
      record.balancingOutcome,
      JSON.stringify(record.mitigations),
      record.approvedBy,
      record.approvedAt,
      record.expiresAt,
      record.hmacSignature,
    )
    .run();
}
```

## Runtime LIA Gate

Before any processing that relies on legitimate interest, the Worker queries D1 for a valid, unexpired, DPO-approved LIA record. If no valid record exists, processing is blocked and a compliance alert fires.

```typescript
// worker/lia-gate.ts
export class LiaGateError extends Error {
  constructor(public purposeCode: string, public reason: string) {
    super(`LIA gate blocked processing for '${purposeCode}': ${reason}`);
  }
}

export async function assertLiaApproved(
  db: D1Database,
  purposeCode: string,
): Promise<void> {
  const row = await db
    .prepare(
      `SELECT balancing_outcome, expires_at FROM lia_records
        WHERE purpose_code = ?`,
    )
    .bind(purposeCode)
    .first<{ balancing_outcome: string; expires_at: number }>();

  if (!row) {
    throw new LiaGateError(purposeCode, "no LIA record found");
  }
  if (row.balancing_outcome !== "approved") {
    throw new LiaGateError(purposeCode, "LIA outcome is not approved");
  }
  if (Date.now() > row.expires_at) {
    throw new LiaGateError(purposeCode, "LIA record has expired and must be reviewed");
  }
}

// Usage inside a fraud-detection Worker
export async function runFraudDetection(
  db: D1Database,
  subjectRef: string,
  signalData: Record<string, unknown>,
): Promise<void> {
  await assertLiaApproved(db, "fraud_detection");
  // Only reaches here if LIA is valid
  await db
    .prepare(
      `INSERT INTO fraud_signals (subject_ref, signals, evaluated_at)
       VALUES (?, ?, ?)`,
    )
    .bind(subjectRef, JSON.stringify(signalData), Date.now())
    .run();
}
```

## Right to Object Handler (Article 21)

When processing relies on legitimate interest, data subjects have an absolute right to object under Article 21 GDPR. An objection must immediately suspend processing for that purpose unless the controller demonstrates compelling legitimate grounds that override the individual's interests.

```typescript
// worker/lia-objection.ts
export async function handleObjection(
  db: D1Database,
  subjectRef: string,
  purposeCode: string,
  compellingGroundOverride: boolean,
): Promise<Response> {
  if (!compellingGroundOverride) {
    // Standard case: honour objection immediately (Art. 21(1))
    await db.batch([
      db.prepare(
        `INSERT INTO lia_objections (subject_ref, purpose_code, objected_at, status)
         VALUES (?, ?, ?, 'upheld')`,
      ).bind(subjectRef, purposeCode, Date.now()),
      db.prepare(
        `DELETE FROM fraud_signals WHERE subject_ref = ?`,
      ).bind(subjectRef),
    ]);
    return Response.json({ outcome: "objection_upheld", processingCeased: true });
  }

  // Exceptional case: document compelling ground and DPO approval before overriding
  await db
    .prepare(
      `INSERT INTO lia_objections (subject_ref, purpose_code, objected_at, status)
       VALUES (?, ?, ?, 'overridden_pending_dpo')`,
    )
    .bind(subjectRef, purposeCode, Date.now())
    .run();

  return Response.json({
    outcome: "override_pending",
    message: "Your objection is under review. Processing is suspended pending DPO sign-off.",
  }, { status: 202 });
}
```

## LIA Expiry Audit – Cron Trigger

LIA records must be periodically re-evaluated. A Cron Trigger fires daily to surface expiring or expired records to the compliance team via a queue message.

```typescript
// worker/lia-audit.ts
export async function auditLiaExpiries(
  db: D1Database,
  queue: Queue,
): Promise<void> {
  const warningWindow = Date.now() + 30 * 24 * 60 * 60 * 1000; // 30 days

  const { results } = await db
    .prepare(
      `SELECT purpose_code, expires_at, approved_by
         FROM lia_records
        WHERE expires_at < ? AND balancing_outcome = 'approved'`,
    )
    .bind(warningWindow)
    .all<{ purpose_code: string; expires_at: number; approved_by: string }>();

  if (results.length > 0) {
    await queue.send({
      type: "lia_expiry_warning",
      records: results.map((r) => ({
        purposeCode: r.purpose_code,
        expiresAt: new Date(r.expires_at).toISOString(),
        approvedBy: r.approved_by,
      })),
    });
  }
}
```

## Anti-patterns

- Using a single blanket LIA record for all "platform operations" rather than a per-purpose assessment; the EDPB and national DPAs uniformly reject catch-all legitimate interest claims.
- Processing under legitimate interest for purposes that could have been achieved with less invasive means (e.g., using full content analysis when only metadata would suffice for spam detection).
- Failing to maintain the objection register; if a data subject objects and processing continues without documented compelling grounds, the controller faces enforcement and data subject litigation risk.

## Gotchas

- The EDPB Guidelines 1/2024 clarify that legitimate interest cannot be used to justify processing that would "surprise" users—if example project users would reasonably not expect their pseudonymous identifiers to be shared with a third-party fraud consortium, legitimate interest is unlikely to survive a balancing test.
- LIA records stored in D1 count as part of the RoPA obligation under Article 30; they must include the categories of data subjects and recipients, not just the purpose code.

## Verification

```bash
# Check all LIA records and expiry status
wrangler d1 execute example project-prod \
  --command "SELECT purpose_code, balancing_outcome, datetime(expires_at/1000,'unixepoch') AS expires FROM lia_records;"

# Test the gate blocks processing with an expired record
wrangler d1 execute example project-prod \
  --command "UPDATE lia_records SET expires_at = 0 WHERE purpose_code = 'fraud_detection';"
curl -si -H "Authorization: Bearer $TEST_TOKEN" \
  https://example project.example.com/internal/fraud-check | jq .error

# Restore
wrangler d1 execute example project-prod \
  --command "UPDATE lia_records SET expires_at = $(date -d '+365 days' +%s)000 WHERE purpose_code = 'fraud_detection';"
```

## Related

- `compliance/gdpr-legitimate-interest-assessment.md`
- `compliance/gdpr-lawful-basis-workers-d1-consent.md`
- `compliance/gdpr-article-30-ropa-automation.md`

## Sources

- https://edpb.europa.eu/our-work-tools/documents/public-consultations/2024/guidelines-12024-legitimate-interest_en
- https://gdpr-info.eu/art-6-gdpr/
- https://gdpr-info.eu/art-21-gdpr/
