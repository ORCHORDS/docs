# HIPAA Breach Notification Workflow on Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Your platform stores or transmits Protected Health Information (PHI) and experiences an incident that may constitute a HIPAA breach. You need automated detection, risk assessment queuing, and breach-notification dispatch workflows implemented on Cloudflare Workers within the 60-day statutory clock.

## Context

The HIPAA Breach Notification Rule (45 C.F.R. §§ 164.400–414) requires Covered Entities (CEs) and Business Associates (BAs) to notify affected individuals within 60 days of *discovering* a breach, notify HHS, and notify media outlets when ≥ 500 individuals in a state are affected. A breach is presumed unless a four-factor risk assessment demonstrates low probability of PHI compromise. Workers Queues, D1, and Cron Triggers provide the scaffolding for this workflow.

---

## 1. Breach Detection — PHI Exposure Sentinel

Detect anomalous PHI access patterns (e.g., bulk exports, unauthenticated reads) at the edge and enqueue a breach candidate event.

```typescript
// src/phi-sentinel.ts
interface BreachCandidate {
  candidateId: string;
  detectedAt: string;
  description: string;
  affectedRecordCount: number;
  dataElements: string[];  // e.g. ['SSN', 'diagnosis', 'DOB']
  requestIp: string;
  userId: string | null;
}

export async function detectPhiExposure(
  request: Request,
  queue: Queue,
  recordCount: number,
  elements: string[]
): Promise<void> {
  if (recordCount < 1) return;
  const candidate: BreachCandidate = {
    candidateId: crypto.randomUUID(),
    detectedAt: new Date().toISOString(),
    description: 'Anomalous PHI bulk access detected',
    affectedRecordCount: recordCount,
    dataElements: elements,
    requestIp: request.headers.get('CF-Connecting-IP') ?? 'unknown',
    userId: request.headers.get('X-User-ID'),
  };
  await queue.send(candidate);
}
```

---

## 2. Four-Factor Risk Assessment Queue Consumer

HIPAA § 164.402 requires assessing: (1) nature and extent of PHI, (2) who accessed it, (3) whether PHI was acquired/viewed, (4) mitigation extent. Record the assessment to D1.

```typescript
// src/risk-assessment-consumer.ts
interface RiskAssessment {
  candidateId: string;
  factor1_phiNature: 'limited' | 'extensive';
  factor2_recipientType: 'internal' | 'external_known' | 'external_unknown';
  factor3_acquired: boolean;
  factor4_mitigated: boolean;
  lowProbability: boolean;   // true => not a breach
  assessedAt: string;
  assessorId: string;
}

export async function recordRiskAssessment(
  db: D1Database,
  assessment: RiskAssessment
): Promise<void> {
  await db.prepare(`
    INSERT INTO hipaa_risk_assessments
      (candidate_id, factor1, factor2, factor3, factor4,
       low_probability, assessed_at, assessor_id)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
  `).bind(
    assessment.candidateId,
    assessment.factor1_phiNature,
    assessment.factor2_recipientType,
    assessment.factor3_acquired ? 1 : 0,
    assessment.factor4_mitigated ? 1 : 0,
    assessment.lowProbability ? 1 : 0,
    assessment.assessedAt,
    assessment.assessorId
  ).run();
}
```

---

## 3. 60-Day Clock Tracking with Cron Trigger

Workers Cron fires daily to identify breach candidates approaching the notification deadline and escalate via email queue.

```typescript
// src/breach-clock-cron.ts
// wrangler.toml: crons = ["0 8 * * *"]
export async function checkBreachClocks(
  db: D1Database,
  notifyQueue: Queue
): Promise<void> {
  const deadline = new Date(Date.now() - 53 * 86400_000).toISOString(); // 53 days = 7-day warning
  const { results } = await db.prepare(`
    SELECT bc.candidate_id, bc.detected_at, bc.affected_record_count
    FROM   breach_candidates bc
    LEFT JOIN hipaa_notifications hn ON bc.candidate_id = hn.candidate_id
    WHERE  bc.detected_at <= ?
      AND  hn.candidate_id IS NULL
      AND  bc.is_breach = 1
  `).bind(deadline).all<{
    candidate_id: string; detected_at: string; affected_record_count: number;
  }>();

  for (const row of results) {
    await notifyQueue.send({
      type: 'HIPAA_DEADLINE_WARNING',
      candidateId: row.candidate_id,
      detectedAt: row.detected_at,
      affectedCount: row.affected_record_count,
      daysRemaining: 60 - Math.floor(
        (Date.now() - new Date(row.detected_at).getTime()) / 86400_000
      ),
    });
  }
}
```

---

## 4. Individual Notification Dispatch

Notifications to individuals must include: description of breach, types of PHI, steps individuals should take, steps CE is taking, contact information (§ 164.404(c)).

```typescript
// src/individual-notification.ts
interface NotificationPayload {
  candidateId: string;
  recipientEmail: string;
  breachDate: string;
  phiTypes: string[];
  recommendedSteps: string[];
  contactPhone: string;
  contactEmail: string;
}

export async function dispatchIndividualNotification(
  payload: NotificationPayload,
  emailQueue: Queue
): Promise<void> {
  const body = `
Dear Individual,

[Breach Description Paragraph]

Types of information involved: ${payload.phiTypes.join(', ')}.

Steps you should take: ${payload.recommendedSteps.join(' ')}.

Steps we are taking: [Description of investigation and remediation].

Contact us: ${payload.contactPhone} | ${payload.contactEmail}
  `.trim();

  await emailQueue.send({
    to: payload.recipientEmail,
    subject: 'Important Notice Regarding Your Health Information',
    body,
    metadata: {
      hipaaControl: '45CFR164.404',
      candidateId: payload.candidateId,
      sentAt: new Date().toISOString(),
    }
  });
}
```

---

## 5. HHS Reporting — Web Notice Trigger (≥ 500 Individuals)

When ≥ 500 individuals in a state are affected, CE must also notify prominent media outlets and submit to HHS within 60 days.

```typescript
// src/hhs-report.ts
interface HhsReport {
  coveredEntityName: string;
  coveredEntityType: 'health_plan' | 'healthcare_provider' | 'clearinghouse';
  breachDate: string;
  breachDiscoveryDate: string;
  stateAffected: string;
  individualsAffected: number;
  typeOfBreach: string;
  locationOfPhiInvolved: string;
  safeguardInPlace: string;
  description: string;
}

export async function storeHhsReportDraft(
  kv: KVNamespace,
  report: HhsReport
): Promise<void> {
  const key = `hhs-report:${report.breachDiscoveryDate}:${crypto.randomUUID()}`;
  await kv.put(key, JSON.stringify(report), {
    metadata: { status: 'draft', submittedToHhs: 'false' }
  });
  // Actual HHS submission via HHS web portal or their API — export this draft for that step
}
```

---

## 6. Notification Audit Trail

```typescript
// src/notification-audit.ts
export async function recordNotificationSent(
  db: D1Database,
  candidateId: string,
  notificationType: 'individual' | 'hhs' | 'media',
  sentAt: string,
  recipientCount: number
): Promise<void> {
  await db.prepare(`
    INSERT INTO hipaa_notifications
      (candidate_id, notification_type, sent_at, recipient_count)
    VALUES (?, ?, ?, ?)
  `).bind(candidateId, notificationType, sentAt, recipientCount).run();
}
```

---

## Anti-patterns

- **Starting the 60-day clock at containment, not discovery** — HIPAA § 164.404 starts at the date the CE/BA *knows* or reasonably should have known; detection is day zero.
- **Using only email for individual notification** — if contact information is insufficient, substitute notice (web posting, media) is required.
- **Omitting Business Associate agreements** — Workers providers must sign BAAs before PHI flows through them; Cloudflare offers a BAA for Business plans and above.
- **Failing to notify when only the BA discovers a breach** — BAs must notify CEs without unreasonable delay and within 60 days of discovery.

---

## Gotchas

- The 60-day clock does not reset if additional individuals are later identified — calendar from the original discovery date.
- Breaches affecting < 500 individuals must still be reported to HHS, but can be aggregated in an annual log submitted by 60 days after year-end.
- Workers Queues guarantee at-least-once delivery; implement idempotency keys on notification inserts to prevent duplicate dispatches.
- Unsecured PHI definition: PHI that has not been rendered unusable by 45 C.F.R. § 164.312(a)(2)(iv) encryption or destruction.

---

## Verification

```bash
# Count open breach candidates past 53 days without notification
wrangler d1 execute HIPAA_DB --command \
  "SELECT COUNT(*) FROM breach_candidates WHERE is_breach=1
   AND detected_at <= datetime('now','-53 days')
   AND candidate_id NOT IN (SELECT candidate_id FROM hipaa_notifications)"

# Inspect HHS report drafts
wrangler kv key list --binding KV_NAMESPACE --prefix "hhs-report:"

# Confirm Queue delivery
wrangler queues consumer list NOTIFY_QUEUE
```

---

## Related

- `hipaa-compliance.md`
- `hipaa-technical-safeguards-web-api.md`
- `hipaa-administrative-safeguards.md`
- `hipaa-audit-controls.md`
- `gdpr-data-breach-notification.md`

---

## Sources

- HIPAA Breach Notification Rule — 45 C.F.R. §§ 164.400–164.414 — https://www.hhs.gov/hipaa/for-professionals/breach-notification/index.html
- HHS Breach Reporting Tool — https://ocrportal.hhs.gov/ocr/breach/wizard_reporting.jsf
- Cloudflare BAA — https://developers.cloudflare.com/workers/platform/privacy/
- Cloudflare Queues — https://developers.cloudflare.com/queues/
