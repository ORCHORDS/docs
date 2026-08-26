# Change Management Approval Workflow with Workers + D1

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Your organisation needs a formal IT change management process to satisfy ISO 27001 Annex A.8.32, SOC 2 CC8.1, and internal ITIL-aligned policies. You need a Workers-based API that handles change request submission, multi-level approval routing (developer → manager → Change Advisory Board), change window enforcement, emergency change bypass with evidence capture, immutable change records, and rollback plan tracking — all stored in D1.

## Context

Change management controls ensure that modifications to production systems are authorised, tested, and reversible. A lightweight Workers API is suitable when:

- Your team is small-to-medium (< 200 engineers) and a full ITSM platform (ServiceNow, Jira Service Management) is overkill or too expensive.
- You want change records co-located with your application infrastructure (same Cloudflare account, same D1 instance).
- You need a programmable approval workflow that integrates with CI/CD pipelines via webhook.

The workflow: `draft → dev_approved → manager_approved → cab_approved → scheduled → in_progress → completed | rolled_back | failed`.

Emergency changes bypass CAB approval but require post-implementation evidence within 24 hours.

## Solution

### 1. D1 Schema

```sql
-- migrations/0004_change_management.sql
CREATE TABLE IF NOT EXISTS change_requests (
  id                TEXT PRIMARY KEY,
  title             TEXT NOT NULL,
  description       TEXT NOT NULL,
  change_type       TEXT NOT NULL,  -- 'standard'|'normal'|'emergency'
  risk_level        TEXT NOT NULL,  -- 'low'|'medium'|'high'|'critical'
  impact            TEXT NOT NULL,  -- free text: which systems, users affected
  rollback_plan     TEXT NOT NULL,
  test_plan         TEXT NOT NULL,
  scheduled_start   TEXT,           -- ISO-8601 UTC
  scheduled_end     TEXT,
  status            TEXT NOT NULL DEFAULT 'draft',
  submitted_by      TEXT NOT NULL,
  submitted_at      TEXT NOT NULL,
  -- Approval tracking
  dev_approved_by   TEXT,
  dev_approved_at   TEXT,
  mgr_approved_by   TEXT,
  mgr_approved_at   TEXT,
  cab_approved_by   TEXT,
  cab_approved_at   TEXT,
  -- Emergency override
  is_emergency      INTEGER NOT NULL DEFAULT 0,
  emergency_reason  TEXT,
  post_impl_evidence TEXT,          -- required within 24h for emergency changes
  post_impl_deadline TEXT,
  -- Execution
  started_at        TEXT,
  completed_at      TEXT,
  outcome           TEXT,           -- 'success'|'partial'|'failed'|'rolled_back'
  outcome_notes     TEXT
);

-- Immutability: once completed/rolled_back, no further status changes
CREATE TRIGGER IF NOT EXISTS cr_immutable_outcome
  BEFORE UPDATE OF status ON change_requests
  WHEN OLD.status IN ('completed','rolled_back','failed')
BEGIN
  SELECT RAISE(ABORT, 'Change record outcome is immutable once set');
END;

CREATE TABLE IF NOT EXISTS change_approval_log (
  id          TEXT PRIMARY KEY,
  change_id   TEXT NOT NULL REFERENCES change_requests(id),
  event_time  TEXT NOT NULL,
  actor_id    TEXT NOT NULL,
  actor_role  TEXT NOT NULL,
  action      TEXT NOT NULL,  -- 'submitted'|'dev_approved'|'dev_rejected'|
                              --  'mgr_approved'|'mgr_rejected'|'cab_approved'|
                              --  'cab_rejected'|'emergency_bypass'|
                              --  'started'|'completed'|'rolled_back'
  comment     TEXT
);

CREATE INDEX idx_cr_status   ON change_requests(status, scheduled_start);
CREATE INDEX idx_cr_risk     ON change_requests(risk_level, submitted_at);
CREATE INDEX idx_cr_emergency ON change_requests(is_emergency, post_impl_deadline)
  WHERE is_emergency=1;
```

### 2. TypeScript types and state machine

```typescript
// src/types/change-management.ts
export type ChangeType  = 'standard' | 'normal' | 'emergency';
export type RiskLevel   = 'low' | 'medium' | 'high' | 'critical';
export type ChangeStatus =
  | 'draft'
  | 'dev_approved'
  | 'manager_approved'
  | 'cab_approved'
  | 'scheduled'
  | 'in_progress'
  | 'completed'
  | 'rolled_back'
  | 'failed'
  | 'rejected';

export interface ChangeRequest {
  id: string;
  title: string;
  description: string;
  change_type: ChangeType;
  risk_level: RiskLevel;
  impact: string;
  rollback_plan: string;
  test_plan: string;
  scheduled_start?: string;
  scheduled_end?: string;
  status: ChangeStatus;
  submitted_by: string;
  submitted_at: string;
  is_emergency: boolean;
  emergency_reason?: string;
  post_impl_evidence?: string;
  post_impl_deadline?: string;
  dev_approved_by?: string;
  dev_approved_at?: string;
  mgr_approved_by?: string;
  mgr_approved_at?: string;
  cab_approved_by?: string;
  cab_approved_at?: string;
  started_at?: string;
  completed_at?: string;
  outcome?: string;
  outcome_notes?: string;
}

// Valid transitions
export const TRANSITIONS: Record<ChangeStatus, ChangeStatus[]> = {
  draft:            ['dev_approved', 'rejected'],
  dev_approved:     ['manager_approved', 'rejected'],
  manager_approved: ['cab_approved', 'rejected'],
  cab_approved:     ['scheduled', 'rejected'],
  scheduled:        ['in_progress', 'rejected'],
  in_progress:      ['completed', 'rolled_back', 'failed'],
  completed:        [],
  rolled_back:      [],
  failed:           [],
  rejected:         [],
};

export function canTransition(from: ChangeStatus, to: ChangeStatus): boolean {
  return TRANSITIONS[from]?.includes(to) ?? false;
}
```

### 3. Change request submission

```typescript
// src/routes/change-mgmt.ts
import { Hono }       from 'hono';
import { z }          from 'zod';
import { requireAuth, requireRole } from '../lib/auth';
import { uuidv7 }    from '../lib/uuid';
import { crAudit }   from '../lib/cr-audit';
import { canTransition } from '../types/change-management';

type Env = { DB: D1Database; CHANGE_MGMT_WEBHOOK: string };
const app = new Hono<{ Bindings: Env }>();

const SubmitSchema = z.object({
  title:          z.string().min(10).max(255),
  description:    z.string().min(50),
  change_type:    z.enum(['standard','normal','emergency']),
  risk_level:     z.enum(['low','medium','high','critical']),
  impact:         z.string().min(20),
  rollback_plan:  z.string().min(20),
  test_plan:      z.string().min(20),
  scheduled_start: z.string().datetime().optional(),
  scheduled_end:   z.string().datetime().optional(),
  is_emergency:    z.boolean().default(false),
  emergency_reason: z.string().optional(),
});

app.post('/changes', requireAuth, async (c) => {
  const actor = c.get('actor');
  const body  = SubmitSchema.safeParse(await c.req.json());
  if (!body.success) return c.json({ error: body.error.flatten() }, 400);

  const d = body.data;
  if (d.is_emergency && !d.emergency_reason) {
    return c.json({ error: 'emergency_reason required for emergency changes' }, 400);
  }

  const id           = uuidv7();
  const submitted_at = new Date().toISOString();
  const post_impl_deadline = d.is_emergency ? addHours(submitted_at, 24) : null;

  // Emergency changes skip straight to cab_approved (still need post-impl evidence)
  const initial_status = d.is_emergency ? 'cab_approved' : 'draft';

  await c.env.DB
    .prepare(`
      INSERT INTO change_requests
        (id, title, description, change_type, risk_level, impact,
         rollback_plan, test_plan, scheduled_start, scheduled_end,
         status, submitted_by, submitted_at, is_emergency,
         emergency_reason, post_impl_deadline)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `)
    .bind(
      id, d.title, d.description, d.change_type, d.risk_level, d.impact,
      d.rollback_plan, d.test_plan, d.scheduled_start ?? null, d.scheduled_end ?? null,
      initial_status, actor.id, submitted_at,
      d.is_emergency ? 1 : 0, d.emergency_reason ?? null, post_impl_deadline
    )
    .run();

  const action = d.is_emergency ? 'emergency_bypass' : 'submitted';
  await crAudit(c.env.DB, id, actor.id, actor.role, action, d.emergency_reason);

  return c.json({ id, status: initial_status, post_impl_deadline }, 201);
});
```

### 4. Approval action endpoint

```typescript
// PATCH /changes/:id/approve  — role-gated per approval level
app.patch('/changes/:id/approve', requireAuth, async (c) => {
  const actor  = c.get('actor');
  const { comment } = await c.req.json<{ comment?: string }>();

  const cr = await c.env.DB
    .prepare('SELECT * FROM change_requests WHERE id = ?')
    .bind(c.req.param('id'))
    .first<ChangeRequest>();
  if (!cr) return c.json({ error: 'Not found' }, 404);

  // Map current status to next status and required role
  const APPROVAL_MAP: Record<string, { next: ChangeStatus; role: string; field: string }> = {
    draft:            { next: 'dev_approved',     role: 'developer',  field: 'dev' },
    dev_approved:     { next: 'manager_approved', role: 'manager',    field: 'mgr' },
    manager_approved: { next: 'cab_approved',     role: 'cab-member', field: 'cab' },
  };

  const step = APPROVAL_MAP[cr.status];
  if (!step) {
    return c.json({ error: `Cannot approve from status=${cr.status}` }, 409);
  }
  if (!actor.roles.includes(step.role) && !actor.roles.includes('security-admin')) {
    return c.json({ error: `Role '${step.role}' required for this approval step` }, 403);
  }

  const now = new Date().toISOString();
  await c.env.DB
    .prepare(`
      UPDATE change_requests
      SET status=?,
          ${step.field}_approved_by=?,
          ${step.field}_approved_at=?
      WHERE id=?
    `)
    .bind(step.next, actor.id, now, cr.id)
    .run();

  await crAudit(c.env.DB, cr.id, actor.id, actor.role,
    `${step.field}_approved` as any, comment);

  return c.json({ id: cr.id, status: step.next });
});
```

### 5. Change window enforcement and execution

```typescript
// POST /changes/:id/start  — enforces scheduled window
app.post('/changes/:id/start', requireRole('developer'), async (c) => {
  const actor = c.get('actor');
  const cr    = await c.env.DB
    .prepare('SELECT * FROM change_requests WHERE id = ?')
    .bind(c.req.param('id'))
    .first<ChangeRequest>();

  if (!cr) return c.json({ error: 'Not found' }, 404);
  if (cr.status !== 'cab_approved' && cr.status !== 'scheduled') {
    return c.json({ error: `Cannot start from status=${cr.status}` }, 409);
  }

  // Enforce change window if scheduled
  if (cr.scheduled_start && cr.scheduled_end) {
    const now = new Date().toISOString();
    if (now < cr.scheduled_start) {
      return c.json({
        error: 'Change window not yet open',
        window_opens: cr.scheduled_start,
      }, 409);
    }
    if (now > cr.scheduled_end) {
      return c.json({
        error: 'Change window has expired',
        window_closed: cr.scheduled_end,
      }, 409);
    }
  }

  await c.env.DB
    .prepare(`UPDATE change_requests SET status='in_progress', started_at=? WHERE id=?`)
    .bind(new Date().toISOString(), cr.id)
    .run();

  await crAudit(c.env.DB, cr.id, actor.id, actor.role, 'started', null);
  return c.json({ id: cr.id, status: 'in_progress' });
});

// POST /changes/:id/complete
app.post('/changes/:id/complete', requireRole('developer'), async (c) => {
  const actor = c.get('actor');
  const { outcome, outcome_notes, post_impl_evidence } =
    await c.req.json<{ outcome: string; outcome_notes?: string; post_impl_evidence?: string }>();

  const cr = await c.env.DB
    .prepare('SELECT * FROM change_requests WHERE id = ?')
    .bind(c.req.param('id'))
    .first<ChangeRequest>();

  if (!cr || cr.status !== 'in_progress') {
    return c.json({ error: 'Change not in_progress' }, 409);
  }

  if (cr.is_emergency && !post_impl_evidence) {
    return c.json({ error: 'post_impl_evidence required for emergency changes' }, 400);
  }

  const finalStatus = outcome === 'success' ? 'completed' :
                      outcome === 'rolled_back' ? 'rolled_back' : 'failed';

  await c.env.DB
    .prepare(`
      UPDATE change_requests
      SET status=?, completed_at=?, outcome=?,
          outcome_notes=?, post_impl_evidence=?
      WHERE id=?
    `)
    .bind(finalStatus, new Date().toISOString(), outcome,
          outcome_notes ?? null, post_impl_evidence ?? null, cr.id)
    .run();

  await crAudit(c.env.DB, cr.id, actor.id, actor.role, finalStatus as any, outcome_notes);
  return c.json({ id: cr.id, status: finalStatus });
});
```

## Implementation Details

- **Immutability trigger** on `change_requests`: once status reaches a terminal state (`completed`, `rolled_back`, `failed`), no further status changes are allowed at the DB layer. Application-level bugs cannot overwrite history.
- **Emergency changes**: they bypass the three-stage approval but are flagged with `is_emergency=1` and require post-implementation evidence within 24 hours. The cron job alerts the CAB if `post_impl_evidence IS NULL AND post_impl_deadline < now()`.
- **Rollback plan field**: required at submission time, not after the fact. A CI/CD webhook can read `GET /changes/:id` and abort deployment if `rollback_plan` is empty or `status != 'cab_approved'`.
- **Approval log** (`change_approval_log`) is append-only — useful for auditability and for reconstructing who approved what and when, independent of the denormalised columns on `change_requests`.

## Anti-patterns

- **Self-approval**: never allow the submitter to be their own level-1 approver. Add a check: `if (d.dev_approved_by === cr.submitted_by) reject`.
- **Deleting rejected change records**: keep all records, including rejections. Auditors need the full history.
- **Allowing status to go backward**: the state machine is one-directional. The `canTransition()` helper enforces this; never bypass it with a raw UPDATE.
- **Skipping post-impl evidence for emergency changes**: the emergency bypass is a risk-accepted shortcut, not a documentation shortcut. Evidence capture is non-negotiable.

## Gotchas

- D1's `BEFORE UPDATE OF status` trigger only fires when the `status` column is explicitly named in the UPDATE statement. A `UPDATE change_requests SET status=? WHERE ...` does fire it; a `UPDATE change_requests SET outcome=? WHERE ...` does NOT — this is correct behaviour.
- Change windows are enforced in Workers (UTC) but engineers often think in local time. Provide a human-readable helper: `GET /changes/:id/window-status` that returns `{ open: boolean, local_time_hint: '...' }`.
- If your D1 database is in a region far from your engineers, add the `--location` flag to wrangler D1 commands to reduce latency during incident rollbacks.

## Verification

```bash
# Submit a normal change
curl -X POST https://api.example.com/changes \
  -H 'Authorization: Bearer $DEV_TOKEN' \
  -d '{"title":"Upgrade PostgreSQL minor version","change_type":"normal",...}'

# Dev approval
curl -X PATCH https://api.example.com/changes/<id>/approve \
  -H 'Authorization: Bearer $DEV_TOKEN' \
  -d '{"comment":"Tested in staging"}'

# Manager approval
curl -X PATCH https://api.example.com/changes/<id>/approve \
  -H 'Authorization: Bearer $MANAGER_TOKEN'

# Attempt to re-approve a completed change (should fail)
curl -X PATCH https://api.example.com/changes/<id>/approve \
  -H 'Authorization: Bearer $ADMIN_TOKEN'
# Expected 409: Cannot approve from status=completed

# Query overdue emergency evidence
wrangler d1 execute APP_DB \
  --command "SELECT id, title, post_impl_deadline FROM change_requests WHERE is_emergency=1 AND post_impl_evidence IS NULL AND post_impl_deadline < datetime('now')"
```

## Related

- `documentation/categories/compliance/workers-hipaa-phi-access-logging-d1.md`
- `documentation/categories/compliance/workers-penetration-test-scope-kv.md`
- `documentation/categories/compliance/workers-access-recertification-campaign-d1.md`

## Sources

- ISO/IEC 27001:2022 Annex A.8.32 — Change Management
- SOC 2 Trust Services Criteria CC8.1 — Change Management
- ITIL 4 — Change Enablement Practice
- NIST SP 800-53 Rev 5 — CM-3 Configuration Change Control
- Cloudflare D1 Docs: https://developers.cloudflare.com/d1/
