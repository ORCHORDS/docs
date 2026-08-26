# Penetration Test Scope Management with Workers + KV + D1

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Your security team runs periodic penetration tests and needs a lightweight system to: (a) publish the current pentest scope (in-scope URLs, IP ranges, testing windows) as a machine-readable API; (b) accept findings submissions from testers; (c) classify findings by severity; and (d) track remediation deadlines and generate summary reports — all inside Cloudflare Workers, with KV for scope data and D1 for structured findings.

## Context

Pentests without a formal scope document create legal and operational risk. A scope API solves several problems:

- Third-party testers can programmatically verify whether a target is in scope before probing it.
- Bug bounty platforms (HackerOne, Bugcrowd) can integrate via webhook for triage.
- The security team has a single source of truth for active test windows.
- Findings are stored in D1 for querying, reporting, and SLA tracking.

Cloudflare KV is appropriate for scope data because it is read-heavy (thousands of testers querying scope vs. one update per engagement), globally distributed, and low-latency. D1 is appropriate for findings because you need relational queries, JOINs, and SLA reporting.

## Solution

### 1. KV scope schema

```typescript
// KV namespace: PENTEST_SCOPE
// Key pattern: scope:<engagement_id>   → JSON string

export interface PentestScope {
  engagement_id: string;
  name: string;                   // e.g. "Q3-2026 External ASV Scan"
  status: 'planned' | 'active' | 'paused' | 'closed';
  start_window: string;           // ISO-8601 UTC
  end_window: string;
  in_scope_urls: string[];        // e.g. ["https://app.example.com", "https://api.example.com"]
  in_scope_ips: string[];         // CIDR notation allowed: ["203.0.113.0/24"]
  out_of_scope_urls: string[];    // explicit exclusions
  allowed_methods: string[];      // ['GET','POST'] or ['*']
  prohibited_actions: string[];   // ['dos','data-exfil','prod-db-write']
  point_of_contact: string;       // security team email
  rules_of_engagement_url: string;
  tester_token_hash: string;      // SHA-256 of the shared tester token
}
```

### 2. Scope management admin endpoints

```typescript
// src/routes/pentest-admin.ts
import { Hono }   from 'hono';
import { z }      from 'zod';
import { requireRole } from '../lib/auth';

type Env = { PENTEST_SCOPE: KVNamespace; DB: D1Database };
const app = new Hono<{ Bindings: Env }>();

const ScopeSchema = z.object({
  engagement_id:           z.string().min(3).max(64),
  name:                    z.string(),
  status:                  z.enum(['planned', 'active', 'paused', 'closed']),
  start_window:            z.string().datetime(),
  end_window:              z.string().datetime(),
  in_scope_urls:           z.array(z.string().url()),
  in_scope_ips:            z.array(z.string()),
  out_of_scope_urls:       z.array(z.string().url()).default([]),
  allowed_methods:         z.array(z.string()).default(['*']),
  prohibited_actions:      z.array(z.string()).default([]),
  point_of_contact:        z.string().email(),
  rules_of_engagement_url: z.string().url(),
  tester_token:            z.string().min(32), // raw token, hashed before storage
});

// PUT /pentest/scope/:id — create or update a scope
app.put('/pentest/scope/:id', requireRole('security-admin'), async (c) => {
  const body = ScopeSchema.safeParse(await c.req.json());
  if (!body.success) return c.json({ error: body.error.flatten() }, 400);

  const { tester_token, ...scopeData } = body.data;

  // Hash the tester token — never store raw secrets in KV
  const tokenHash = await hashToken(tester_token);
  const scope: PentestScope = { ...scopeData, tester_token_hash: tokenHash };

  await c.env.PENTEST_SCOPE.put(
    `scope:${scope.engagement_id}`,
    JSON.stringify(scope),
    { expirationTtl: 60 * 60 * 24 * 90 } // auto-expire after 90 days if not renewed
  );

  return c.json({ message: 'Scope published', engagement_id: scope.engagement_id });
});

// DELETE /pentest/scope/:id
app.delete('/pentest/scope/:id', requireRole('security-admin'), async (c) => {
  await c.env.PENTEST_SCOPE.delete(`scope:${c.req.param('id')}`);
  return c.json({ message: 'Scope deleted' });
});

async function hashToken(token: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(token));
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2,'0')).join('');
}

export default app;
```

### 3. Scope verification endpoint (public, token-gated)

```typescript
// src/routes/pentest-public.ts — testers call this to verify scope
app.get('/pentest/scope/:id', async (c) => {
  const raw = await c.env.PENTEST_SCOPE.get(`scope:${c.req.param('id')}`);
  if (!raw) return c.json({ error: 'Engagement not found' }, 404);

  const scope: PentestScope = JSON.parse(raw);

  // Verify tester token
  const token = c.req.header('X-Tester-Token') ?? '';
  const hash  = await hashToken(token);
  if (hash !== scope.tester_token_hash) {
    return c.json({ error: 'Invalid tester token' }, 403);
  }

  // Check active window
  const now = new Date().toISOString();
  const inWindow = now >= scope.start_window && now <= scope.end_window;

  // Return scope without the token hash
  const { tester_token_hash: _, ...publicScope } = scope;
  return c.json({ ...publicScope, currently_active: inWindow && scope.status === 'active' });
});

// POST /pentest/scope/:id/check-target — is a URL/IP in scope?
app.post('/pentest/scope/:id/check-target', async (c) => {
  const { target } = await c.req.json<{ target: string }>();
  const token = c.req.header('X-Tester-Token') ?? '';
  const raw   = await c.env.PENTEST_SCOPE.get(`scope:${c.req.param('id')}`);
  if (!raw) return c.json({ in_scope: false, reason: 'Engagement not found' });

  const scope: PentestScope = JSON.parse(raw);
  if ((await hashToken(token)) !== scope.tester_token_hash) {
    return c.json({ error: 'Unauthorized' }, 403);
  }

  const inScopeUrl = scope.in_scope_urls.some(u => target.startsWith(u));
  const outScope   = scope.out_of_scope_urls.some(u => target.startsWith(u));
  const inWindow   = new Date().toISOString() >= scope.start_window
                  && new Date().toISOString() <= scope.end_window;

  const in_scope = inScopeUrl && !outScope && inWindow && scope.status === 'active';
  const reasons: string[] = [];
  if (!inScopeUrl)    reasons.push('target not in in_scope_urls');
  if (outScope)       reasons.push('target is explicitly out-of-scope');
  if (!inWindow)      reasons.push('outside testing window');
  if (scope.status !== 'active') reasons.push(`engagement status=${scope.status}`);

  return c.json({ in_scope, reasons, prohibited_actions: scope.prohibited_actions });
});
```

### 4. D1 Findings schema

```sql
-- migrations/0003_pentest_findings.sql
CREATE TABLE IF NOT EXISTS pentest_findings (
  id                TEXT PRIMARY KEY,
  engagement_id     TEXT NOT NULL,
  title             TEXT NOT NULL,
  description       TEXT NOT NULL,
  severity          TEXT NOT NULL,  -- 'critical'|'high'|'medium'|'low'|'informational'
  cvss_score        REAL,
  cve_ids           TEXT,           -- JSON array
  affected_url      TEXT NOT NULL,
  affected_component TEXT,
  steps_to_reproduce TEXT NOT NULL,
  proof_of_concept  TEXT,
  impact            TEXT NOT NULL,
  recommendation    TEXT NOT NULL,
  status            TEXT NOT NULL DEFAULT 'open',
  -- status: open | triaged | in_remediation | remediated | accepted_risk | wont_fix
  submitted_at      TEXT NOT NULL,
  remediation_deadline TEXT NOT NULL,  -- based on severity SLA
  remediated_at     TEXT,
  remediation_notes TEXT,
  submitted_by      TEXT NOT NULL
);

CREATE INDEX idx_findings_engagement ON pentest_findings(engagement_id, severity);
CREATE INDEX idx_findings_deadline   ON pentest_findings(remediation_deadline) WHERE status NOT IN ('remediated','wont_fix');
```

### 5. Findings intake API

```typescript
// src/routes/pentest-findings.ts
const SEVERITY_SLA_DAYS: Record<string, number> = {
  critical:      7,
  high:          30,
  medium:        90,
  low:           180,
  informational: 365,
};

const FindingSchema = z.object({
  title:               z.string().min(5).max(255),
  description:         z.string().min(20),
  severity:            z.enum(['critical','high','medium','low','informational']),
  cvss_score:          z.number().min(0).max(10).optional(),
  cve_ids:             z.array(z.string()).optional(),
  affected_url:        z.string().url(),
  affected_component:  z.string().optional(),
  steps_to_reproduce:  z.string().min(20),
  proof_of_concept:    z.string().optional(),
  impact:              z.string().min(10),
  recommendation:      z.string().min(10),
});

// POST /pentest/scope/:engagement_id/findings
app.post('/pentest/scope/:engagement_id/findings', async (c) => {
  const engagement_id = c.req.param('engagement_id');
  const token = c.req.header('X-Tester-Token') ?? '';

  // Verify token against scope
  const raw = await c.env.PENTEST_SCOPE.get(`scope:${engagement_id}`);
  if (!raw) return c.json({ error: 'Engagement not found' }, 404);
  const scope: PentestScope = JSON.parse(raw);
  if ((await hashToken(token)) !== scope.tester_token_hash) {
    return c.json({ error: 'Unauthorized' }, 403);
  }

  const body = FindingSchema.safeParse(await c.req.json());
  if (!body.success) return c.json({ error: body.error.flatten() }, 400);

  const f     = body.data;
  const id    = uuidv7();
  const now   = new Date().toISOString();
  const deadline = addDays(now, SEVERITY_SLA_DAYS[f.severity]);

  await c.env.DB
    .prepare(`
      INSERT INTO pentest_findings
        (id, engagement_id, title, description, severity, cvss_score,
         cve_ids, affected_url, affected_component, steps_to_reproduce,
         proof_of_concept, impact, recommendation, submitted_at,
         remediation_deadline, submitted_by)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `)
    .bind(
      id, engagement_id, f.title, f.description, f.severity,
      f.cvss_score ?? null, f.cve_ids ? JSON.stringify(f.cve_ids) : null,
      f.affected_url, f.affected_component ?? null, f.steps_to_reproduce,
      f.proof_of_concept ?? null, f.impact, f.recommendation,
      now, deadline,
      scope.point_of_contact  // attribute to engagement contact for audit
    )
    .run();

  return c.json({ id, remediation_deadline: deadline, severity: f.severity }, 201);
});
```

### 6. Pentest report generation

```typescript
// GET /pentest/scope/:engagement_id/report  — security admin only
app.get('/pentest/scope/:engagement_id/report', requireRole('security-admin'), async (c) => {
  const eid = c.req.param('engagement_id');

  const raw = await c.env.PENTEST_SCOPE.get(`scope:${eid}`);
  if (!raw) return c.json({ error: 'Engagement not found' }, 404);
  const scope: PentestScope = JSON.parse(raw);

  const { results: findings } = await c.env.DB
    .prepare(`SELECT * FROM pentest_findings WHERE engagement_id = ? ORDER BY
      CASE severity WHEN 'critical' THEN 1 WHEN 'high' THEN 2
        WHEN 'medium' THEN 3 WHEN 'low' THEN 4 ELSE 5 END`)
    .bind(eid)
    .all();

  const summary = {
    critical:      findings.filter(f => f.severity === 'critical').length,
    high:          findings.filter(f => f.severity === 'high').length,
    medium:        findings.filter(f => f.severity === 'medium').length,
    low:           findings.filter(f => f.severity === 'low').length,
    informational: findings.filter(f => f.severity === 'informational').length,
    overdue:       findings.filter(f =>
      f.status !== 'remediated' && f.status !== 'wont_fix' &&
      (f.remediation_deadline as string) < new Date().toISOString()
    ).length,
  };

  const { tester_token_hash: _, ...publicScope } = scope;
  return c.json({ engagement: publicScope, summary, findings });
});
```

## Implementation Details

- **KV TTL**: Set `expirationTtl` on scope entries to 90 days to auto-expire stale engagements. Refresh the TTL on each status update.
- **CVSS scoring**: Store the raw CVSS score alongside severity label. The label can be overridden by the security team on triage; the score provides an objective baseline.
- **SLA enforcement**: The cron job (daily at 06:00 UTC) queries `pentest_findings WHERE status NOT IN ('remediated','wont_fix') AND remediation_deadline < now()` and fires Slack/email alerts.
- **Immutability of findings**: Unlike scope (which changes), findings should not be deleted — use `status=wont_fix` or `status=accepted_risk` with documented rationale.

## Anti-patterns

- **Storing the raw tester token in KV**: always store only the SHA-256 hash. The raw token in a KV read is a secret exposure.
- **Trusting the tester's severity classification without triage**: accept it as `submitted_severity` and record a separate `triaged_severity` set by your team.
- **Using KV for findings**: KV has no querying capability. Findings belong in D1 where you can GROUP BY severity, filter by deadline, and JOIN with engagement data.
- **Skipping the out-of-scope URL check**: testers may probe adjacent systems. An explicit exclusion list and a scope-check endpoint prevent accidental out-of-scope testing.

## Gotchas

- KV reads in Workers are served from the nearest PoP with up to 60-second eventual consistency. For scope changes (e.g., emergency pause), use `PENTEST_SCOPE.put(..., { expiration: ... })` and also push an "emergency stop" key (`scope:<id>:paused`) that is checked first — this key propagates faster due to being a fresh write.
- UUIDs generated in Workers use `crypto.randomUUID()` which is CSPRNG-based and safe for security contexts.
- The findings intake endpoint is semi-public (token-gated, not user-auth-gated). Apply rate limiting with Cloudflare Rate Limiting rules to prevent flooding.

## Verification

```bash
# 1. Publish a scope
curl -X PUT https://api.example.com/pentest/scope/q3-2026-ext \
  -H 'Authorization: Bearer $ADMIN_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"engagement_id":"q3-2026-ext","status":"active",...}'

# 2. Check if target is in scope
curl -X POST https://api.example.com/pentest/scope/q3-2026-ext/check-target \
  -H 'X-Tester-Token: <raw_token>' \
  -d '{"target":"https://api.example.com/users"}'

# 3. Submit a finding
curl -X POST https://api.example.com/pentest/scope/q3-2026-ext/findings \
  -H 'X-Tester-Token: <raw_token>' \
  -d '{"title":"SQL Injection in /search","severity":"critical",...}'

# 4. Generate report
curl https://api.example.com/pentest/scope/q3-2026-ext/report \
  -H 'Authorization: Bearer $ADMIN_TOKEN'

# 5. Check overdue findings
wrangler d1 execute APP_DB \
  --command "SELECT id, title, severity, remediation_deadline FROM pentest_findings WHERE status='open' AND remediation_deadline < datetime('now') ORDER BY severity"
```

## Related

- `documentation/docs/policies/compliance/workers-change-management-approval-d1.md`
- `documentation/docs/policies/compliance/workers-access-recertification-campaign-d1.md`
- `documentation/docs/policies/security/workers-rate-limiting-pattern.md`

## Sources

- NIST SP 800-115 — Technical Guide to Information Security Testing
- PCI DSS v4.0 Requirement 11.3 — Penetration Testing
- OWASP Testing Guide v4.2
- Cloudflare KV Docs: https://developers.cloudflare.com/kv/
- CVSS v3.1 Specification: https://www.first.org/cvss/specification-document
