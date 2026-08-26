# South Korea PIPA Compliance on Cloudflare Workers

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

example project reaches South Korean users whose personal information is governed by the Personal Information Protection Act (PIPA, 개인정보 보호법), enforced by the Personal Information Protection Commission (PIPC). Non-compliance risks fines of up to 3% of related revenue and criminal liability. South Korea's PIPA underwent significant amendments in 2023 aligning it closer to GDPR while adding stricter pseudonymisation and mobile identifier rules.

## Context

South Korean PIPA is one of Asia's most comprehensive privacy laws. It requires explicit prior consent for most personal information (PI) collection, a mandatory privacy notice in Korean, a designated Privacy Officer (개인정보 보호책임자), and domestic processing or PIPC-authorised cross-border transfers. The 2023 amendments introduced mobile-application specific rules, tightened pseudonymisation standards, and created a new statutory damage framework of KRW 3 million to 300 million per incident. For example project, critical obligations include consent lifecycle management, pseudonymisation of user data, and real-time breach notification within 72 hours to the PIPC and affected users.

## Consent Collection and Lifecycle

Article 15 of PIPA requires separate, granular consent for each processing purpose. Consent must be freely given, specific, and informed. The Workers consent handler stores each consent item individually with timestamps and purpose codes.

```typescript
// worker/pipa-consent.ts
export interface PipaConsentItem {
  subjectRef: string;
  purposeCode: string;     // e.g. "platform_operation", "analytics", "marketing"
  consentGiven: boolean;
  consentedAt: number | null;
  withdrawnAt: number | null;
  ipHash: string;
  userAgent: string;
}

export async function recordPipaConsent(
  db: D1Database,
  items: PipaConsentItem[],
): Promise<void> {
  const stmt = db.prepare(
    `INSERT INTO pipa_consents
       (subject_ref, purpose_code, consent_given, consented_at, withdrawn_at, ip_hash, user_agent)
     VALUES (?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT (subject_ref, purpose_code)
     DO UPDATE SET
       consent_given = excluded.consent_given,
       consented_at  = excluded.consented_at,
       withdrawn_at  = excluded.withdrawn_at`,
  );

  await db.batch(
    items.map((i) =>
      stmt.bind(
        i.subjectRef,
        i.purposeCode,
        i.consentGiven ? 1 : 0,
        i.consentedAt,
        i.withdrawnAt,
        i.ipHash,
        i.userAgent,
      ),
    ),
  );
}

export async function hasActiveConsent(
  db: D1Database,
  subjectRef: string,
  purposeCode: string,
): Promise<boolean> {
  const row = await db
    .prepare(
      `SELECT consent_given FROM pipa_consents
        WHERE subject_ref = ? AND purpose_code = ?
          AND withdrawn_at IS NULL`,
    )
    .bind(subjectRef, purposeCode)
    .first<{ consent_given: number }>();
  return row?.consent_given === 1;
}
```

## Pseudonymisation Requirements

Article 28-2 of PIPA (2023 amendment) allows processing of pseudonymised information for statistical, scientific research, and public-interest purposes without consent, provided re-identification is technically infeasible. example project generates HMAC-SHA256 pseudonyms for all analytics pipelines.

```typescript
// worker/pipa-pseudonym.ts
export async function derivePseudonym(
  hmacKeyB64: string,
  userId: string,
): Promise<string> {
  const rawKey = Uint8Array.from(atob(hmacKeyB64), (c) => c.charCodeAt(0));
  const cryptoKey = await crypto.subtle.importKey(
    "raw",
    rawKey,
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = await crypto.subtle.sign(
    "HMAC",
    cryptoKey,
    new TextEncoder().encode(userId),
  );
  return btoa(String.fromCharCode(...new Uint8Array(sig)))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

// Insert into analytics without direct user ID
export async function insertAnalyticsEvent(
  db: D1Database,
  pseudonym: string,
  eventType: string,
  metadata: Record<string, unknown>,
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO analytics_events (pseudonym, event_type, metadata, recorded_at)
       VALUES (?, ?, ?, ?)`,
    )
    .bind(pseudonym, eventType, JSON.stringify(metadata), Date.now())
    .run();
}
```

## Cross-Border Transfer Controls

Article 28-8 (2023 amendment) requires PIPC notification or standard contractual clause (SCC) execution before transferring PI outside South Korea. A transfer manifest is maintained in D1 and surfaced to the PIPC on request.

```typescript
// worker/pipa-transfer.ts
export type PipaTransferBasis =
  | "data_subject_consent"
  | "pipc_standard_clauses"
  | "adequacy_decision"
  | "international_treaty";

export async function logPipaTransfer(
  db: D1Database,
  opts: {
    subjectRef: string;
    recipientCountry: string;
    recipientName: string;
    basis: PipaTransferBasis;
    purposeCode: string;
  },
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO pipa_transfer_log
         (subject_ref, recipient_country, recipient_name, basis, purpose_code, transferred_at)
       VALUES (?, ?, ?, ?, ?, ?)`,
    )
    .bind(
      opts.subjectRef,
      opts.recipientCountry,
      opts.recipientName,
      opts.basis,
      opts.purposeCode,
      Date.now(),
    )
    .run();
}
```

## Breach Notification – 72-Hour PIPC Report

Article 34 of PIPA requires notification to the PIPC within 72 hours of discovering a breach affecting 1,000 or more data subjects, and notification to affected data subjects without unreasonable delay. The Workers breach handler creates a timestamped incident record and queues notifications.

```typescript
// worker/pipa-breach.ts
export async function openBreachIncident(
  db: D1Database,
  queue: Queue,
  opts: {
    description: string;
    estimatedAffectedCount: number;
    piiCategories: string[];
    discoveredAt: number;
  },
): Promise<string> {
  const incidentId = crypto.randomUUID();
  const pipcDeadlineMs = opts.discoveredAt + 72 * 60 * 60 * 1000;

  await db
    .prepare(
      `INSERT INTO breach_incidents
         (id, description, affected_count, pii_categories,
          discovered_at, pipc_deadline_ms, status)
       VALUES (?, ?, ?, ?, ?, ?, 'open')`,
    )
    .bind(
      incidentId,
      opts.description,
      opts.estimatedAffectedCount,
      JSON.stringify(opts.piiiCategories ?? opts.piiiCategories),
      opts.discoveredAt,
      pipcDeadlineMs,
    )
    .run();

  await queue.send({
    type: "pipa_breach_alert",
    incidentId,
    pipcDeadlineMs,
    estimatedAffectedCount: opts.estimatedAffectedCount,
  });

  return incidentId;
}
```

## Anti-patterns

- Collecting a single omnibus consent checkbox for all purposes fails Article 15's requirement for separate consent per purpose; Korean regulators specifically test for this.
- Using plain sequential numeric user IDs in analytics exports—even without names—can constitute PI under PIPA's broad definition if they enable re-identification via join with other data.
- Delaying breach notification beyond 72 hours because internal investigation is incomplete; PIPA requires notification based on reasonable belief of breach, not confirmed root cause.

## Gotchas

- The 2023 PIPA amendments introduced a right to explanation for automated decisions (Article 37-2) similar to GDPR Article 22; if example project uses algorithmic content ranking, this triggers explanation obligations for Korean users.
- The Privacy Officer (개인정보 보호책임자) must be registered with the PIPC for operators of online information services with over KRW 10 billion revenue or over 1 million daily unique users. Failure to designate is a separate penalty item.

## Verification

```bash
# Check consent records for a test subject
wrangler d1 execute example project-prod \
  --command "SELECT purpose_code, consent_given, consented_at FROM pipa_consents WHERE subject_ref = 'test-kr-001';"

# Check breach incident status and PIPC deadline
wrangler d1 execute example project-prod \
  --command "SELECT id, affected_count, pipc_deadline_ms, status FROM breach_incidents ORDER BY discovered_at DESC LIMIT 5;"

# Verify pseudonym is deterministic for same input
node -e "
const { derivePseudonym } = require('./dist/pipa-pseudonym');
derivePseudonym(process.env.HMAC_KEY_B64, 'user-123').then(console.log);
"
```

## Related

- `compliance/appi-japan-compliance.md`
- `compliance/pdpa-thailand-compliance.md`
- `compliance/gdpr-breach-notification-72h.md`

## Sources

- https://www.pipc.go.kr/eng/
- https://www.law.go.kr/lsInfoP.do?lsiSeq=254489 (PIPA 2023 amended text)
- https://www.dlapiperdataprotection.com/index.html?t=law&c=KR
