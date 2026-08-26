# VCDPA Virginia Consumer Data Protection Act — Cloudflare Workers

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

Your service controls or processes personal data of Virginia residents and meets the VCDPA threshold: either (a) during a calendar year, process personal data of 100,000+ Virginia consumers, or (b) process personal data of 25,000+ consumers while deriving over 50 % of gross revenue from selling personal data. The Virginia Consumer Data Protection Act (VCDPA, Va. Code §§ 59.1-571 through 59.1-581, effective 1 January 2023) requires a consent mechanism for sensitive data, consumer rights fulfilment, privacy notices, data protection assessments, and sale opt-out signals — all enforced by the Virginia Attorney General with fines up to USD 7,500 per violation.

---

## Context

The VCDPA is an opt-in law for sensitive data and an opt-out law for targeted advertising / data sales. Key provisions:

- **Consumer rights** (§ 59.1-574): access, correction, deletion, portability, opt-out of sale/targeted advertising/profiling.
- **Sensitive data** (§ 59.1-571): race/ethnicity, religious beliefs, mental/physical health diagnosis, sexual orientation, citizenship/immigration status, genetic/biometric data, children's data, precise geolocation — requires **opt-in consent** before processing.
- **Sale opt-out** (§ 59.1-574(A)(4)): consumers may opt out of sale of personal data, targeted advertising, and profiling in furtherance of solely automated decisions with legal or similarly significant effects.
- **Universal Opt-Out Mechanisms (UOOM)** (§ 59.1-574(B)): controllers must recognise technically specified opt-out signals (GPC — Global Privacy Control) by 1 January 2025.
- **Data Protection Assessments (DPAs)** (§ 59.1-577): required before processing for targeted advertising, sale, profiling with significant effects, sensitive data, or any processing presenting a heightened risk.
- **Processor contracts** (§ 59.1-579): required; must specify processing instructions, permitted activities, confidentiality, sub-processor rules.
- **Response deadline**: 45 days, extendable by 45 days with notice.
- **No private right of action**: enforcement is exclusively by the Virginia AG after a 30-day cure opportunity.

---

## 1. Sensitive Data Opt-In Consent Gate

Sensitive data processing requires prior opt-in consent — an affirmative act, not default-on or pre-ticked.

```typescript
// workers/vcdpa-sensitive-consent.ts
import { Env } from './types';

const SENSITIVE_CATEGORIES = [
  'race_ethnicity', 'religious_belief', 'mental_health_diagnosis',
  'physical_health_diagnosis', 'sexual_orientation', 'citizenship_immigration',
  'genetic_data', 'biometric_data', 'childrens_data', 'precise_geolocation',
] as const;
type VcdpaSensitiveCategory = typeof SENSITIVE_CATEGORIES[number];

interface SensitiveConsentRecord {
  id: string;
  consumerId: string;
  categories: VcdpaSensitiveCategory[];
  purpose: string;
  consentText: string;
  grantedAt: string;
  revokedAt: string | null;
  collectionMethod: 'web_form' | 'api' | 'mobile';
  ipAddress: string;
}

export async function grantVcdpaSensitiveConsent(
  env: Env,
  consumerId: string,
  categories: VcdpaSensitiveCategory[],
  purpose: string,
  consentText: string,
  request: Request,
): Promise<string> {
  const id = crypto.randomUUID();

  await env.DB.prepare(
    `INSERT INTO vcdpa_sensitive_consent
     (id, consumer_id, categories, purpose, consent_text,
      granted_at, revoked_at, collection_method, ip_address)
     VALUES (?, ?, ?, ?, ?, datetime('now'), NULL, 'web_form', ?)`,
  ).bind(
    id, consumerId, JSON.stringify(categories),
    purpose, consentText,
    request.headers.get('CF-Connecting-IP') ?? 'unknown',
  ).run();

  return id;
}

export async function hasVcdpaSensitiveConsent(
  env: Env,
  consumerId: string,
  category: VcdpaSensitiveCategory,
): Promise<boolean> {
  const row = await env.DB.prepare(
    `SELECT 1 FROM vcdpa_sensitive_consent
     WHERE consumer_id = ? AND revoked_at IS NULL
       AND categories LIKE '%' || ? || '%'
     LIMIT 1`,
  ).bind(consumerId, category).first();

  return row !== null;
}
```

---

## 2. GPC / Universal Opt-Out Signal Detection

§ 59.1-574(B) requires recognition of the Global Privacy Control signal. Workers can detect it at the edge before the request reaches any downstream service.

```typescript
// workers/vcdpa-gpc-detection.ts
interface OptOutRecord {
  consumerId: string;
  signal: 'gpc' | 'manual' | 'api';
  scope: 'sale' | 'targeted_advertising' | 'profiling' | 'all';
  detectedAt: string;
  ipAddress: string;
  userAgent: string;
}

export function detectGPC(request: Request): boolean {
  // GPC sends Sec-GPC: 1 header per W3C spec
  return request.headers.get('Sec-GPC') === '1';
}

export async function processOptOut(
  env: Env,
  consumerId: string,
  scope: OptOutRecord['scope'],
  request: Request,
  signal: OptOutRecord['signal'] = 'gpc',
): Promise<void> {
  await env.DB.prepare(
    `INSERT OR REPLACE INTO vcdpa_opt_out
     (consumer_id, signal, scope, detected_at, ip_address, user_agent)
     VALUES (?, ?, ?, datetime('now'), ?, ?)`,
  ).bind(
    consumerId, signal, scope,
    request.headers.get('CF-Connecting-IP') ?? 'unknown',
    request.headers.get('User-Agent') ?? 'unknown',
  ).run();
}

export async function isOptedOut(
  env: Env,
  consumerId: string,
  scope: 'sale' | 'targeted_advertising' | 'profiling',
): Promise<boolean> {
  const row = await env.DB.prepare(
    `SELECT 1 FROM vcdpa_opt_out
     WHERE consumer_id = ? AND (scope = ? OR scope = 'all')
     LIMIT 1`,
  ).bind(consumerId, scope).first();

  return row !== null;
}

// Middleware: auto-detect GPC on every request
export async function gpcMiddleware(
  env: Env,
  request: Request,
  consumerId: string | null,
): Promise<void> {
  if (consumerId && detectGPC(request)) {
    await processOptOut(env, consumerId, 'all', request, 'gpc');
  }
}
```

---

## 3. Consumer Rights — 45-Day Response Clock

```typescript
// workers/vcdpa-consumer-rights.ts
type VcdpaRightType =
  | 'access' | 'correction' | 'deletion'
  | 'portability' | 'opt_out_sale' | 'opt_out_targeted_ads'
  | 'opt_out_profiling' | 'opt_in_consent_withdrawal';

interface VcdpaDSRTicket {
  id: string;
  consumerId: string;
  rightType: VcdpaRightType;
  receivedAt: string;
  deadlineAt: string;           // 45 days
  extendedDeadlineAt: string | null; // up to 90 days total with notice
  status: 'open' | 'extended' | 'completed' | 'denied';
  denialReason: string | null;
  appealDeadlineAt: string | null; // after denial
}

export async function openVcdpaRequest(
  env: Env,
  consumerId: string,
  rightType: VcdpaRightType,
): Promise<VcdpaDSRTicket> {
  const id = crypto.randomUUID();
  const now = new Date();
  const deadline = new Date(now);
  deadline.setDate(deadline.getDate() + 45);

  const ticket: VcdpaDSRTicket = {
    id, consumerId, rightType,
    receivedAt: now.toISOString(),
    deadlineAt: deadline.toISOString(),
    extendedDeadlineAt: null,
    status: 'open',
    denialReason: null,
    appealDeadlineAt: null,
  };

  await env.DB.prepare(
    `INSERT INTO vcdpa_dsr
     (id, consumer_id, right_type, received_at, deadline_at,
      extended_deadline_at, status, denial_reason, appeal_deadline_at)
     VALUES (?, ?, ?, ?, ?, NULL, 'open', NULL, NULL)`,
  ).bind(
    id, consumerId, rightType,
    ticket.receivedAt, ticket.deadlineAt,
  ).run();

  return ticket;
}

export async function denyVcdpaRequest(
  env: Env,
  ticketId: string,
  reason: string,
): Promise<void> {
  // After denial, controller must provide an appeal mechanism
  const appealDeadline = new Date(Date.now() + 45 * 24 * 60 * 60 * 1000).toISOString();

  await env.DB.prepare(
    `UPDATE vcdpa_dsr
     SET status = 'denied', denial_reason = ?, appeal_deadline_at = ?
     WHERE id = ?`,
  ).bind(reason, appealDeadline, ticketId).run();
}

export async function extendVcdpaRequest(env: Env, ticketId: string): Promise<void> {
  const row = await env.DB.prepare(
    `SELECT received_at FROM vcdpa_dsr WHERE id = ?`,
  ).bind(ticketId).first<{ received_at: string }>();

  if (!row) throw new Error('DSR ticket not found');

  const extended = new Date(row.received_at);
  extended.setDate(extended.getDate() + 90); // max 90 calendar days from receipt

  await env.DB.prepare(
    `UPDATE vcdpa_dsr SET status = 'extended', extended_deadline_at = ? WHERE id = ?`,
  ).bind(extended.toISOString(), ticketId).run();
}

// Cron: alert 5 days before deadline
export async function alertApproachingDeadlines(env: Env): Promise<void> {
  const threshold = new Date(Date.now() + 5 * 24 * 60 * 60 * 1000).toISOString();

  const { results } = await env.DB.prepare(
    `SELECT id, consumer_id, right_type,
            COALESCE(extended_deadline_at, deadline_at) AS effective_deadline
     FROM vcdpa_dsr
     WHERE status IN ('open','extended')
       AND COALESCE(extended_deadline_at, deadline_at) <= ?`,
  ).bind(threshold).all<{ id: string; consumer_id: string; right_type: string; effective_deadline: string }>();

  for (const r of results) {
    await env.ALERTS_QUEUE.send({ type: 'vcdpa_dsr_deadline_warning', ...r });
  }
}
```

---

## 4. Data Protection Assessment (DPA) Registry

§ 59.1-577 requires a completed DPA before starting any high-risk processing activity. The AG may request DPAs during an investigation.

```typescript
// workers/vcdpa-dpa-registry.ts
type DpaProcessingActivity =
  | 'targeted_advertising' | 'sale_of_personal_data'
  | 'profiling_significant_effects' | 'sensitive_data_processing'
  | 'other_high_risk';

interface DataProtectionAssessment {
  id: string;
  activityName: string;
  activityType: DpaProcessingActivity;
  purpose: string;
  legitimatePurpose: string;
  benefitsAssessed: string;
  risksIdentified: string;
  mitigationsApplied: string;
  netBenefitPositive: boolean;
  completedAt: string;
  approvedBy: string;   // name/title of approving officer
  nextReviewAt: string;
}

export async function registerDPA(
  env: Env,
  dpa: Omit<DataProtectionAssessment, 'id' | 'completedAt'>,
): Promise<string> {
  const id = crypto.randomUUID();

  await env.DB.prepare(
    `INSERT INTO vcdpa_dpa_registry
     (id, activity_name, activity_type, purpose, legitimate_purpose,
      benefits_assessed, risks_identified, mitigations_applied,
      net_benefit_positive, completed_at, approved_by, next_review_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?, ?)`,
  ).bind(
    id, dpa.activityName, dpa.activityType, dpa.purpose,
    dpa.legitimatePurpose, dpa.benefitsAssessed, dpa.risksIdentified,
    dpa.mitigationsApplied, dpa.netBenefitPositive ? 1 : 0,
    dpa.approvedBy, dpa.nextReviewAt,
  ).run();

  return id;
}

export async function auditDPACoverage(
  env: Env,
): Promise<{ uncoveredActivities: string[] }> {
  // List known high-risk activities and check DPA exists for each
  const REQUIRED_ACTIVITIES: DpaProcessingActivity[] = [
    'targeted_advertising', 'sale_of_personal_data',
    'profiling_significant_effects',
  ];

  const uncoveredActivities: string[] = [];

  for (const activity of REQUIRED_ACTIVITIES) {
    const row = await env.DB.prepare(
      `SELECT 1 FROM vcdpa_dpa_registry WHERE activity_type = ? LIMIT 1`,
    ).bind(activity).first();

    if (!row) uncoveredActivities.push(activity);
  }

  return { uncoveredActivities };
}
```

---

## 5. Processor Contract Checklist Enforcement

§ 59.1-579 mandates specific contractual provisions for data processors. A D1-backed registry tracks whether contracts are on file and complete.

```typescript
// workers/vcdpa-processor-contracts.ts
interface ProcessorContract {
  id: string;
  processorName: string;
  serviceDescription: string;
  hasProcessingInstructions: boolean;
  hasPermittedActivities: boolean;
  hasConfidentialityObligation: boolean;
  hasSubprocessorRules: boolean;
  hasDeletionOrReturnClause: boolean;
  hasAuditRights: boolean;
  signedAt: string;
  expiresAt: string | null;
  compliant: boolean;
}

export async function registerProcessorContract(
  env: Env,
  contract: Omit<ProcessorContract, 'id' | 'compliant'>,
): Promise<{ id: string; compliant: boolean }> {
  const id = crypto.randomUUID();
  const compliant = (
    contract.hasProcessingInstructions &&
    contract.hasPermittedActivities &&
    contract.hasConfidentialityObligation &&
    contract.hasSubprocessorRules &&
    contract.hasDeletionOrReturnClause &&
    contract.hasAuditRights
  );

  await env.DB.prepare(
    `INSERT INTO vcdpa_processor_contracts
     (id, processor_name, service_description,
      has_processing_instructions, has_permitted_activities,
      has_confidentiality_obligation, has_subprocessor_rules,
      has_deletion_or_return_clause, has_audit_rights,
      signed_at, expires_at, compliant)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
  ).bind(
    id, contract.processorName, contract.serviceDescription,
    contract.hasProcessingInstructions ? 1 : 0,
    contract.hasPermittedActivities ? 1 : 0,
    contract.hasConfidentialityObligation ? 1 : 0,
    contract.hasSubprocessorRules ? 1 : 0,
    contract.hasDeletionOrReturnClause ? 1 : 0,
    contract.hasAuditRights ? 1 : 0,
    contract.signedAt, contract.expiresAt,
    compliant ? 1 : 0,
  ).run();

  return { id, compliant };
}
```

---

## Anti-patterns

- **Treating GPC as optional.** § 59.1-574(B) mandates recognition of technically specified opt-out signals as of 1 January 2025; failure is a per-consumer violation.
- **Forgetting the appeal right.** When denying a consumer request, VCDPA requires the controller to provide an internal appeal process — not just a denial notice.
- **Skipping DPAs for existing activities.** DPAs are required before commencing **or continuing** a processing activity when a material change occurs.
- **Using the same consent mechanism for targeted advertising and sensitive data.** Targeted advertising uses an opt-out model; sensitive data requires opt-in — conflating them creates gaps in both directions.

---

## Gotchas

- The VCDPA applies to consumers acting in a **personal or household** context; employees and B2B contacts are excluded (until 1 January 2025 the exemption was explicit; check the current statute for any sunset).
- "Sale" under VCDPA includes exchange for monetary **or other valuable consideration** — bartering data for services or access counts.
- The AG must provide a **30-day cure notice** before bringing a civil action; this cure window is not guaranteed to remain after the legislature's periodic review.
- Precise geolocation is sensitive data — a radius of less than 1,750 feet (approximately 533 metres) triggers the opt-in requirement.
- VCDPA does **not** require a privacy notice to list all categories of data collected (unlike CCPA) — but the notice must be reasonably accessible, clear, and meaningful.
- Virginia has no data-residency mandate; Cloudflare's default PoP routing is acceptable.

---

## Verification

```bash
# 1. Consumers with GPC signal and active targeted-ad processing
wrangler d1 execute DB --command \
  "SELECT consumer_id, detected_at FROM vcdpa_opt_out
   WHERE (scope = 'targeted_advertising' OR scope = 'all')
   ORDER BY detected_at DESC LIMIT 20;"

# 2. Open DSR tickets near or past 45-day deadline
wrangler d1 execute DB --command \
  "SELECT id, right_type, deadline_at FROM vcdpa_dsr
   WHERE status IN ('open','extended')
   AND COALESCE(extended_deadline_at, deadline_at) < datetime('now', '+5 days');"

# 3. High-risk activities missing a DPA
wrangler d1 execute DB --command \
  "SELECT activity_type, COUNT(*) FROM vcdpa_dpa_registry GROUP BY activity_type;"

# 4. Non-compliant processor contracts
wrangler d1 execute DB --command \
  "SELECT processor_name, service_description FROM vcdpa_processor_contracts WHERE compliant = 0;"

# 5. Sensitive consent coverage check
wrangler d1 execute DB --command \
  "SELECT consumer_id, categories FROM vcdpa_sensitive_consent WHERE revoked_at IS NULL;"
```

---

## Related

- `ccpa-cpra-consumer-rights-operations.md`
- `ccpa-opt-out.md`
- `us-state-privacy-laws-2026-multi-state-compliance.md`
- `colorado-cpa-consent-management.md`
- `cookie-consent-management-platform.md`

---

## Sources

- Virginia Consumer Data Protection Act (Va. Code §§ 59.1-571 through 59.1-581): https://law.lis.virginia.gov/vacodefull/title59.1/chapter53/
- Virginia AG VCDPA FAQ: https://www.oag.state.va.us/consumer-protection/index.php/privacy
- IAPP VCDPA Overview: https://iapp.org/resources/article/virginia-consumer-data-protection-act/
- W3C Global Privacy Control specification: https://globalprivacycontrol.github.io/gpc-spec/
- Cloudflare Workers Documentation: https://developers.cloudflare.com/workers/
