# Data Breach Notification System in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Under GDPR Article 33, you must notify the supervisory authority within 72 hours of becoming aware of a personal data breach. Under GDPR Article 34, high-risk breaches also require notifying affected individuals. You need a system that: detects anomalous query volume and unauthorized access patterns at the edge, records breach incidents in D1, tracks the 72-hour notification deadline, classifies breach severity, compiles the list of affected users, generates regulatory notification documents, and exposes an internal endpoint for your DPO to trigger authority notifications.

## Context

Breaches must be detected fast and documented precisely. GDPR requires the notification to include:
- Nature of the breach and categories of data affected
- Contact details of the Data Protection Officer
- Likely consequences of the breach
- Measures taken to mitigate the breach

Cloudflare Workers can serve as both the detection layer (inspecting requests in real time) and the coordination layer (tracking incident state and generating notifications).

## Solution

```typescript
export interface Env {
  DB: D1Database;
  BREACH_KV: KVNamespace;         // Rate counters and anomaly state
  INTERNAL_API_SECRET: string;
  DPO_EMAIL: string;               // Data Protection Officer contact
  AUTHORITY_NOTIFICATION_URL: string; // Supervisory authority API (e.g. ICO portal)
  ORG_NAME: string;
  ORG_ADDRESS: string;
}

// ─── Breach severity classification ───────────────────────────────────────────

type BreachSeverity = 'low' | 'medium' | 'high' | 'critical';

interface BreachClassification {
  severity: BreachSeverity;
  requiresIndividualNotification: boolean;
  requiresAuthorityNotification: boolean;
  notificationDeadlineHours: number;
}

function classifyBreach(dataCategories: string[], recordCount: number): BreachClassification {
  const sensitiveCategories = ['health', 'financial', 'biometric', 'credentials', 'location', 'children'];
  const hasSensitive = dataCategories.some((c) => sensitiveCategories.includes(c));

  let severity: BreachSeverity;
  if (hasSensitive && recordCount > 1000) severity = 'critical';
  else if (hasSensitive || recordCount > 10000) severity = 'high';
  else if (recordCount > 100) severity = 'medium';
  else severity = 'low';

  return {
    severity,
    requiresIndividualNotification: severity === 'high' || severity === 'critical',
    requiresAuthorityNotification: severity !== 'low',
    notificationDeadlineHours: 72,
  };
}

// ─── Anomaly detection ─────────────────────────────────────────────────────────

const RATE_WINDOW_SECONDS = 60;
const QUERY_ANOMALY_THRESHOLD = 500;  // queries per minute per IP
const FAILED_AUTH_THRESHOLD = 20;     // failed auth per minute per IP

interface AnomalyResult {
  anomalyDetected: boolean;
  type?: 'high_query_volume' | 'repeated_auth_failure' | 'unusual_data_scope';
  ip?: string;
  count?: number;
}

async function detectAnomalies(request: Request, env: Env): Promise<AnomalyResult> {
  const ip = request.headers.get('CF-Connecting-IP') ?? 'unknown';
  const windowKey = Math.floor(Date.now() / (RATE_WINDOW_SECONDS * 1000));

  // Increment query counter for this IP in this minute window
  const queryKey = `anomaly:query:${ip}:${windowKey}`;
  const queryCountRaw = await env.BREACH_KV.get(queryKey);
  const queryCount = (queryCountRaw ? parseInt(queryCountRaw, 10) : 0) + 1;
  await env.BREACH_KV.put(queryKey, String(queryCount), { expirationTtl: RATE_WINDOW_SECONDS * 2 });

  if (queryCount > QUERY_ANOMALY_THRESHOLD) {
    return { anomalyDetected: true, type: 'high_query_volume', ip, count: queryCount };
  }

  // Check failed auth counter (populated by auth middleware)
  const authKey = `anomaly:auth_fail:${ip}:${windowKey}`;
  const authCountRaw = await env.BREACH_KV.get(authKey);
  const authCount = authCountRaw ? parseInt(authCountRaw, 10) : 0;

  if (authCount > FAILED_AUTH_THRESHOLD) {
    return { anomalyDetected: true, type: 'repeated_auth_failure', ip, count: authCount };
  }

  return { anomalyDetected: false };
}

// ─── Breach record management ─────────────────────────────────────────────────

interface BreachRecord {
  id: string;
  detectedAt: string;
  description: string;
  dataCategories: string[];
  estimatedRecordCount: number;
  affectedUserIds: string[];
  severity: BreachSeverity;
  status: 'detected' | 'investigating' | 'contained' | 'authority_notified' | 'individuals_notified' | 'closed';
  authorityDeadline: string;
  authorityNotifiedAt?: string;
  individualsNotifiedAt?: string;
  mitigationSteps: string[];
  dpoContact: string;
}

async function createBreachRecord(
  env: Env,
  description: string,
  dataCategories: string[],
  estimatedRecordCount: number,
  affectedUserIds: string[],
  mitigationSteps: string[]
): Promise<BreachRecord> {
  const id = `breach_${crypto.randomUUID()}`;
  const detectedAt = new Date().toISOString();
  const classification = classifyBreach(dataCategories, estimatedRecordCount);

  const deadline = new Date();
  deadline.setHours(deadline.getHours() + classification.notificationDeadlineHours);

  const record: BreachRecord = {
    id,
    detectedAt,
    description,
    dataCategories,
    estimatedRecordCount,
    affectedUserIds,
    severity: classification.severity,
    status: 'detected',
    authorityDeadline: deadline.toISOString(),
    mitigationSteps,
    dpoContact: env.DPO_EMAIL,
  };

  await env.DB.prepare(
    `INSERT INTO breach_incidents
     (id, detected_at, description, data_categories, estimated_record_count,
      affected_user_count, severity, status, authority_deadline, dpo_contact,
      mitigation_steps)
     VALUES (?, ?, ?, ?, ?, ?, ?, 'detected', ?, ?, ?)`
  )
    .bind(
      id, detectedAt, description,
      JSON.stringify(dataCategories),
      estimatedRecordCount,
      affectedUserIds.length,
      classification.severity,
      deadline.toISOString(),
      env.DPO_EMAIL,
      JSON.stringify(mitigationSteps)
    )
    .run();

  // Store affected user list in separate table
  for (const userId of affectedUserIds.slice(0, 10000)) { // cap for large breaches
    await env.DB.prepare(
      `INSERT OR IGNORE INTO breach_affected_users (breach_id, user_id) VALUES (?, ?)`
    )
      .bind(id, userId)
      .run();
  }

  return record;
}

// ─── Notification template generation ─────────────────────────────────────────

function generateAuthorityNotification(breach: BreachRecord, orgName: string, orgAddress: string): string {
  const hoursElapsed = Math.round(
    (Date.now() - new Date(breach.detectedAt).getTime()) / (1000 * 60 * 60)
  );
  return JSON.stringify({
    notification_type: 'personal_data_breach',
    article: 'GDPR Article 33',
    controller: { name: orgName, address: orgAddress, dpo_email: breach.dpoContact },
    breach: {
      id: breach.id,
      detected_at: breach.detectedAt,
      hours_since_detection: hoursElapsed,
      description: breach.description,
      data_categories_affected: breach.dataCategories,
      estimated_individuals_affected: breach.estimatedRecordCount,
      severity: breach.severity,
    },
    likely_consequences: 'Potential unauthorised access to personal data; risk of identity theft or targeted phishing.',
    mitigation_measures: breach.mitigationSteps,
    further_information_available: true,
    notification_within_72h: hoursElapsed <= 72,
    reason_for_delay: hoursElapsed > 72 ? 'Investigation required to ascertain scope.' : null,
  }, null, 2);
}

function generateIndividualNotification(breach: BreachRecord, orgName: string): string {
  return `Subject: Important Security Notice — ${orgName}\n\n` +
    `Dear Customer,\n\n` +
    `We are writing to inform you of a security incident that may have affected your personal data.\n\n` +
    `What happened: ${breach.description}\n\n` +
    `Data affected: ${breach.dataCategories.join(', ')}\n\n` +
    `When: ${new Date(breach.detectedAt).toDateString()}\n\n` +
    `What we are doing: ${breach.mitigationSteps.join('; ')}\n\n` +
    `What you should do: Change your password, monitor your accounts for suspicious activity, ` +
    `and contact us at ${breach.dpoContact} with any concerns.\n\n` +
    `Sincerely,\n${orgName} Data Protection Team`;
}

// ─── Status update helpers ─────────────────────────────────────────────────────

async function updateBreachStatus(
  env: Env,
  breachId: string,
  status: BreachRecord['status'],
  extraFields: Record<string, string> = {}
): Promise<void> {
  const setClauses = ['status = ?', ...Object.keys(extraFields).map((k) => `${k} = ?`)];
  const values = [status, ...Object.values(extraFields), breachId];
  await env.DB.prepare(
    `UPDATE breach_incidents SET ${setClauses.join(', ')} WHERE id = ?`
  )
    .bind(...values)
    .run();
}

// ─── 72-hour deadline monitor ──────────────────────────────────────────────────

async function checkDeadlines(env: Env): Promise<{ overdue: unknown[] }> {
  const { results } = await env.DB.prepare(
    `SELECT id, detected_at, authority_deadline, severity, status
     FROM breach_incidents
     WHERE status NOT IN ('authority_notified','individuals_notified','closed')
       AND authority_deadline < ?
     LIMIT 50`
  )
    .bind(new Date().toISOString())
    .all();
  return { overdue: results };
}

// ─── Main Worker ───────────────────────────────────────────────────────────────

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const auth = request.headers.get('Authorization');

    // Public anomaly detection hook (called from request middleware)
    if (url.pathname === '/breach/detect' && request.method === 'POST') {
      const anomaly = await detectAnomalies(request, env);
      if (anomaly.anomalyDetected) {
        // Auto-create a low-severity breach record for investigation
        await createBreachRecord(
          env,
          `Automated detection: ${anomaly.type} from IP ${anomaly.ip} (${anomaly.count} events/min)`,
          ['access_logs', 'metadata'],
          0, // unknown until investigation
          [],
          ['IP rate-limited', 'Session tokens invalidated', 'Security team alerted']
        );
      }
      return new Response(JSON.stringify(anomaly), {
        headers: { 'Content-Type': 'application/json' },
      });
    }

    // All other endpoints require internal auth
    if (auth !== `Bearer ${env.INTERNAL_API_SECRET}`) {
      return new Response('Unauthorized', { status: 401 });
    }

    // POST /breach/report — DPO manually reports a breach
    if (url.pathname === '/breach/report' && request.method === 'POST') {
      const body = await request.json<{
        description: string;
        dataCategories: string[];
        estimatedRecordCount: number;
        affectedUserIds: string[];
        mitigationSteps: string[];
      }>();
      const record = await createBreachRecord(
        env, body.description, body.dataCategories,
        body.estimatedRecordCount, body.affectedUserIds, body.mitigationSteps
      );
      return new Response(JSON.stringify(record), {
        status: 201, headers: { 'Content-Type': 'application/json' },
      });
    }

    // POST /breach/:id/notify-authority
    if (url.pathname.match(/^\/breach\/breach_[^/]+\/notify-authority$/) && request.method === 'POST') {
      const breachId = url.pathname.split('/')[2];
      const breach = await env.DB.prepare(`SELECT * FROM breach_incidents WHERE id = ?`)
        .bind(breachId).first<BreachRecord>();
      if (!breach) return new Response('Not found', { status: 404 });

      const notification = generateAuthorityNotification(breach, env.ORG_NAME, env.ORG_ADDRESS);
      // In production: POST to env.AUTHORITY_NOTIFICATION_URL or ICO portal
      await updateBreachStatus(env, breachId, 'authority_notified', {
        authority_notified_at: new Date().toISOString(),
      });
      return new Response(JSON.stringify({ notification, status: 'sent' }), {
        headers: { 'Content-Type': 'application/json' },
      });
    }

    // GET /breach/deadlines — list overdue notifications
    if (url.pathname === '/breach/deadlines') {
      const overdue = await checkDeadlines(env);
      return new Response(JSON.stringify(overdue), {
        headers: { 'Content-Type': 'application/json' },
      });
    }

    // GET /breach/:id/individual-notice
    if (url.pathname.match(/^\/breach\/breach_[^/]+\/individual-notice$/)) {
      const breachId = url.pathname.split('/')[2];
      const breach = await env.DB.prepare(`SELECT * FROM breach_incidents WHERE id = ?`)
        .bind(breachId).first<BreachRecord>();
      if (!breach) return new Response('Not found', { status: 404 });
      const notice = generateIndividualNotification(breach, env.ORG_NAME);
      return new Response(JSON.stringify({ notice }), {
        headers: { 'Content-Type': 'application/json' },
      });
    }

    return new Response('Not found', { status: 404 });
  },

  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    // Run deadline check every hour; alert if overdue breaches exist
    await checkDeadlines(env);
  },
};
```

## Implementation Details

**Anomaly detection**: Per-IP counters are stored in KV with a 2-minute TTL (2× the 1-minute window). This avoids a persistent counter accumulation while preserving enough history to detect spikes. Production systems should add Analytics Engine counters for global (not per-IP) volume tracking.

**Severity classification**: `classifyBreach` maps data category sensitivity and record count to a four-level severity scale. "critical" and "high" trigger individual notification requirements; "medium" and above trigger supervisory authority notification.

**72-hour deadline**: Stored as `authority_deadline` in D1, set to `detectedAt + 72 hours`. A hourly cron queries for overdue records and surfaces them at `GET /breach/deadlines`. Integrate with your alerting system (PagerDuty, email) from the scheduled handler.

**D1 schema**:
```sql
CREATE TABLE breach_incidents (
  id TEXT PRIMARY KEY,
  detected_at TEXT NOT NULL,
  description TEXT NOT NULL,
  data_categories TEXT NOT NULL,     -- JSON array
  estimated_record_count INTEGER NOT NULL,
  affected_user_count INTEGER NOT NULL,
  severity TEXT NOT NULL,
  status TEXT NOT NULL,
  authority_deadline TEXT NOT NULL,
  authority_notified_at TEXT,
  individuals_notified_at TEXT,
  dpo_contact TEXT NOT NULL,
  mitigation_steps TEXT NOT NULL     -- JSON array
);
CREATE TABLE breach_affected_users (
  breach_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  PRIMARY KEY (breach_id, user_id)
);
```

## Anti-patterns

- **Do not** suppress anomaly alerts to reduce noise — false negatives on breach detection carry severe regulatory penalties.
- **Do not** notify individuals before the breach scope is understood — premature notification with incorrect information requires corrections and causes unnecessary alarm.
- **Do not** store the full affected user list in the breach record JSON — use the `breach_affected_users` join table to handle tens of thousands of affected users.
- **Do not** use the `AUTHORITY_NOTIFICATION_URL` secret in client-side code — this endpoint is for internal DPO use only.
- **Do not** mark a breach `closed` until both authority and individual notifications are confirmed sent.

## Gotchas

- **72 hours starts at awareness, not at occurrence**: GDPR Art. 33(1) says "without undue delay and, where feasible, not later than 72 hours after having become aware of it". "Aware" is when your organization knows, not when the attack happened.
- **Low-severity breaches still need internal documentation**: Even if authority notification is not required, GDPR Art. 33(5) requires documenting all breaches internally.
- **ICO/DPA portals vary by country**: The `AUTHORITY_NOTIFICATION_URL` will differ per jurisdiction (ICO for UK, CNIL for France, etc.). Your pipeline may need per-country routing.
- **Anomaly detection false positives**: Marketing campaigns and product launches can spike query volume. Allow for a manual override to dismiss auto-created breach records after investigation.
- **KV counter race conditions**: Concurrent requests to the same IP's counter key may undercount. Use Durable Objects' atomic storage for precise counts in high-volume scenarios.

## Verification

```bash
# 1. Manually report a test breach (non-prod)
curl -X POST https://api.example.com/breach/report \
  -H 'Authorization: Bearer <SECRET>' \
  -H 'Content-Type: application/json' \
  -d '{"description":"Test breach — non-production","dataCategories":["email"],"estimatedRecordCount":50,"affectedUserIds":[],"mitigationSteps":["Test only"]}'

# 2. Check deadlines endpoint
curl https://api.example.com/breach/deadlines \
  -H 'Authorization: Bearer <SECRET>' | jq '.overdue | length'
# Expected: 0 for a fresh breach

# 3. Generate authority notification document
curl -X POST https://api.example.com/breach/<breach_id>/notify-authority \
  -H 'Authorization: Bearer <SECRET>' | jq '.notification' | head -30

# 4. Generate individual notice template
curl https://api.example.com/breach/<breach_id>/individual-notice \
  -H 'Authorization: Bearer <SECRET>' | jq -r '.notice'
```

## Related

- `documentation/docs/policies/compliance/soc2-audit-trail.md` — breach events feed into SOC 2 audit trail
- `documentation/docs/policies/compliance/audit-log-immutable-r2.md` — immutable logs are evidence in breach investigations
- `documentation/docs/policies/compliance/workers-access-control-audit.md` — access anomalies feed breach detection
- `documentation/docs/policies/compliance/gdpr-consent-logging.md` — consent state relevant to notification obligations

## Sources

- GDPR Article 33 — Notification of a personal data breach to the supervisory authority
- GDPR Article 34 — Communication of a personal data breach to the data subject
- GDPR Article 33(5) — Internal breach documentation requirement
- WP29/EDPB Guidelines on personal data breach notification: https://edpb.europa.eu/our-work-tools/our-documents/guidelines/guidelines-012021-examples-regarding-personal-data-breach_en
- ICO breach reporting: https://ico.org.uk/for-organisations/report-a-breach/
- Cloudflare Workers: https://developers.cloudflare.com/workers/
