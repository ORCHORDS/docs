# New York SHIELD Act: Data Security Compliance in Workers + D1

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
You process personal data — including passwords, biometrics, or financial account numbers — belonging to New York State residents and must comply with the Stop Hacks and Improve Electronic Data Security (SHIELD) Act (NY Gen. Bus. Law §§ 899-aa, 899-bb), which mandates a reasonable data security program and expands breach notification obligations regardless of whether your company is incorporated in New York.

## Context
The SHIELD Act (signed 25 July 2019, security-program provisions effective 21 March 2020) expanded New York's breach notification law to cover a wider set of data elements and extended the data security obligation to any business that owns, licenses, or maintains computerised data including private information of any New York resident. "Private information" now includes biometric data, account credentials, and HIPAA-covered health data in addition to the legacy SSN/financial-account definitions. The NY AG enforces; there is no private right of action. Cloudflare Workers serve as the perimeter security layer, and D1 holds the security-program documentation and breach-event log.

## Reasonable Security Program: Administrative Controls

SHIELD Act §899-bb(2)(b)(i) requires administrative safeguards — designating a security coordinator, training employees, and reviewing the security program after a breach.

```typescript
// src/shield-admin.ts
interface Env {
  DB: D1Database;
}

interface SecurityProgram {
  coordinator_name: string;
  coordinator_email: string;
  program_version: string;
  effective_date: string;
  last_reviewed: string;
  training_frequency_days: number;
  vendor_assessment_frequency_days: number;
}

export async function upsertSecurityProgram(
  env: Env,
  program: SecurityProgram
): Promise<void> {
  await env.DB.prepare(`
    INSERT INTO shield_security_program
      (coordinator_name, coordinator_email, program_version,
       effective_date, last_reviewed, training_frequency_days,
       vendor_assessment_frequency_days, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT (program_version) DO UPDATE
      SET last_reviewed = excluded.last_reviewed,
          updated_at = excluded.updated_at
  `).bind(
    program.coordinator_name,
    program.coordinator_email,
    program.program_version,
    program.effective_date,
    program.last_reviewed,
    program.training_frequency_days,
    program.vendor_assessment_frequency_days,
    new Date().toISOString()
  ).run();
}

export async function logEmployeeTraining(
  env: Env,
  employeeId: string,
  moduleId: string,
  completedAt: string
): Promise<void> {
  await env.DB.prepare(`
    INSERT INTO shield_training_log
      (employee_id, module_id, completed_at)
    VALUES (?, ?, ?)
    ON CONFLICT (employee_id, module_id) DO UPDATE
      SET completed_at = excluded.completed_at
  `).bind(employeeId, moduleId, completedAt).run();
}
```

## Technical Safeguards: Encryption and Access Controls

SHIELD Act §899-bb(2)(b)(iii) requires technical safeguards including encryption of private information in transit and at rest, and access controls based on the principle of least privilege.

```typescript
// src/shield-technical.ts

/**
 * Workers middleware that enforces TLS-only access and
 * validates that private information fields are never returned
 * in cleartext outside of authenticated, encrypted channels.
 */
export function shieldTlsMiddleware(
  request: Request,
  next: () => Promise<Response>
): Promise<Response> | Response {
  // Cloudflare always terminates TLS, but enforce HSTS on responses
  if (request.url.startsWith('http://') && !request.headers.get('X-Forwarded-Proto')) {
    return Response.redirect(request.url.replace('http://', 'https://'), 301);
  }
  return next();
}

/**
 * Mask private information fields in API responses.
 * SHIELD "private information" includes: SSN, financial account,
 * credentials, biometrics, health data. Never emit these in cleartext.
 */
const SHIELD_SENSITIVE_FIELDS = new Set([
  'ssn',
  'social_security_number',
  'account_number',
  'routing_number',
  'credit_card',
  'debit_card',
  'password',
  'password_hash',
  'biometric_template',
  'health_record',
  'medical_record_number',
  'dob_plus_name', // combined DOB + name = private info under SHIELD
]);

export function maskShieldFields<T extends Record<string, unknown>>(
  obj: T
): Partial<T> {
  const safe: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(obj)) {
    const lcKey = key.toLowerCase().replace(/-/g, '_');
    safe[key] = SHIELD_SENSITIVE_FIELDS.has(lcKey) ? '[REDACTED]' : value;
  }
  return safe as Partial<T>;
}

export async function enforceColumnEncryption(
  env: Env,
  userId: string
): Promise<void> {
  // Verify that no private information is stored in plaintext columns
  const row = await env.DB.prepare(`
    SELECT
      CASE WHEN ssn IS NOT NULL AND ssn NOT LIKE 'enc:%' THEN 1 ELSE 0 END AS ssn_plaintext,
      CASE WHEN health_data IS NOT NULL AND health_data NOT LIKE 'enc:%' THEN 1 ELSE 0 END AS health_plaintext
    FROM users WHERE id = ?
  `).bind(userId).first<{ ssn_plaintext: number; health_plaintext: number }>();

  if (row?.ssn_plaintext || row?.health_plaintext) {
    throw new Error(
      'SHIELD Act §899-bb(2)(b)(iii): private information stored in plaintext — ' +
        'encrypt before writing to D1.'
    );
  }
}
```

## Breach Notification Orchestration

SHIELD Act §899-aa requires notification to affected NY residents "in the most expedient time possible" (no fixed statutory deadline, but AG guidance targets 30-60 days). Notification to the AG is also required when a breach affects more than 500 NY residents.

```typescript
// src/shield-breach.ts

type NotificationChannel = 'email' | 'mail' | 'telephone' | 'electronic_notice';

interface BreachEvent {
  incident_id: string;
  discovered_at: string;
  affected_ny_residents: number;
  data_elements_compromised: string[]; // from SHIELD §899-aa(1)(b) definitions
  root_cause: string;
  containment_actions: string;
  notification_channel: NotificationChannel;
}

export async function recordBreachEvent(
  env: Env,
  breach: BreachEvent
): Promise<void> {
  await env.DB.prepare(`
    INSERT INTO shield_breach_log
      (incident_id, discovered_at, affected_ny_residents,
       data_elements_json, root_cause, containment_actions,
       notification_channel, ag_notification_required, logged_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
  `).bind(
    breach.incident_id,
    breach.discovered_at,
    breach.affected_ny_residents,
    JSON.stringify(breach.data_elements_compromised),
    breach.root_cause,
    breach.containment_actions,
    breach.notification_channel,
    breach.affected_ny_residents >= 500 ? 1 : 0,
    new Date().toISOString()
  ).run();
}

export async function getBreachNotificationStatus(
  env: Env,
  incidentId: string
): Promise<{
  agRequired: boolean;
  agNotified: boolean;
  residentsNotified: boolean;
}> {
  const row = await env.DB.prepare(`
    SELECT ag_notification_required,
           ag_notified_at IS NOT NULL AS ag_notified,
           residents_notified_at IS NOT NULL AS residents_notified
    FROM shield_breach_log
    WHERE incident_id = ?
  `).bind(incidentId).first<{
    ag_notification_required: number;
    ag_notified: number;
    residents_notified: number;
  }>();

  return {
    agRequired: !!row?.ag_notification_required,
    agNotified: !!row?.ag_notified,
    residentsNotified: !!row?.residents_notified,
  };
}

export async function markResidentsNotified(
  env: Env,
  incidentId: string
): Promise<void> {
  await env.DB.prepare(`
    UPDATE shield_breach_log
    SET residents_notified_at = ?
    WHERE incident_id = ?
  `).bind(new Date().toISOString(), incidentId).run();
}
```

## Anti-patterns
- Storing SSNs, financial account numbers, or health data in plaintext D1 columns — §899-bb(2)(b)(iii)
- Limiting breach notification only to NY residents whose SSN was exposed — SHIELD added account credentials, biometrics, and health data to the trigger set
- Failing to notify affected individuals because the breach involved fewer than 500 records — the 500-threshold triggers AG notification, not individual notification
- Omitting vendor security assessments — SHIELD requires oversight of third-party service providers handling private information
- Treating the lack of private right of action as low risk — NY AG has pursued civil penalties and injunctive relief under GBL §349
- Using a single, undocumented "we take security seriously" statement in place of a documented security program

## Gotchas
- SHIELD applies to any entity that "owns, licenses, or maintains" data including NY private information — not limited to NY-based companies
- "Private information" under SHIELD now includes: username/email + password combinations, security questions/answers, biometric data, and HIPAA-covered health data
- There is no safe harbour for encrypted data only if the keys were also compromised — encryption must be properly key-managed to claim the encrypted-data exclusion
- The "small business" safe harbour (§899-bb(2)(c)) allows flexible compliance but does not eliminate the duty to implement *some* reasonable safeguards
- AG Letitia James has actively pursued SHIELD enforcement — settlements in the range of $200,000-$600,000 for failures to implement basic controls
- Credential-stuffing incidents that expose NY user accounts can trigger notification obligations even if your systems were not directly breached
- SHIELD breach notification must also go to credit bureaus when more than 5,000 NY residents are affected

## Verification

```sql
-- Check for plaintext private information columns (should return 0 rows)
SELECT id, email,
       CASE WHEN ssn NOT LIKE 'enc:%' THEN 'PLAINTEXT' ELSE 'ok' END AS ssn_status
FROM users
WHERE ssn IS NOT NULL AND ssn NOT LIKE 'enc:%'
LIMIT 10;

-- Breach events requiring AG notification but not yet notified
SELECT incident_id, discovered_at, affected_ny_residents,
       ag_notified_at
FROM shield_breach_log
WHERE ag_notification_required = 1
  AND ag_notified_at IS NULL;

-- Security program review schedule (should be reviewed at least annually)
SELECT program_version, last_reviewed,
       DATE(last_reviewed, '+365 days') AS next_review_due
FROM shield_security_program
ORDER BY last_reviewed DESC
LIMIT 5;

-- Employees overdue for security training
SELECT e.id, e.email, tl.completed_at,
       DATE(tl.completed_at, '+365 days') AS next_due
FROM employees e
LEFT JOIN shield_training_log tl ON e.id = tl.employee_id
WHERE tl.completed_at IS NULL
   OR DATE(tl.completed_at, '+365 days') < DATE('now');
```

## Related
- `ny-dfs-cybersecurity-regulation.md`
- `data-breach-notification-72h.md` (GDPR comparison)
- `gdpr-breach-notification-72h.md`
- `hipaa-breach-notification-workers.md`
- `iso-27001-compliance.md`
- `soc2-cc6-logical-access-controls.md`
- `audit-log-mandatory.md`

## Sources
- https://legislation.nysenate.gov/pdf/bills/2019/S5575B (SHIELD Act text)
- https://ag.ny.gov/data-security (NY AG Data Security)
- https://ag.ny.gov/sites/default/files/shield_act_guidance.pdf
- https://iapp.org/news/a/new-york-shield-act-what-you-need-to-know/
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers/
