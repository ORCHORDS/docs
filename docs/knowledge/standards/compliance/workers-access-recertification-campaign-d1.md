# Periodic Access Recertification Campaigns with Workers + D1

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Your organisation must demonstrate that user access entitlements are periodically reviewed and certified by accountable owners — a control required by SOC 2 CC6.3, ISO 27001 Annex A.8.2, HIPAA §164.308(a)(3), and PCI DSS Req 7. You need a Workers-based system that: schedules recertification campaigns via cron, snapshots current entitlements, assigns reviewers, records certify/revoke decisions, auto-revokes access on reviewer non-response after deadline, and produces an immutable audit trail — all in D1.

## Context

Access recertification (also called access review or entitlement review) closes the "role drift" gap — accounts accumulate permissions over time through promotions, project reassignments, and exception grants that are never cleaned up. Periodic review forces accountable owners (managers, system owners) to explicitly certify or revoke each entitlement.

Key requirements:
1. **Campaign scheduling**: quarterly by default, configurable per system.
2. **Entitlement snapshot**: capture the state of access at campaign start (not live, to prevent gaming).
3. **Reviewer assignment**: route entitlements to the user's direct manager or the system owner.
4. **Certify/revoke actions**: reviewers record decisions; system integrations act on revocations.
5. **Auto-revoke on silence**: if a reviewer does not respond by deadline, access is automatically revoked (fail-secure).
6. **Audit trail**: every decision is immutable and attributable.

## Solution

### 1. D1 Schema

```sql
-- migrations/0005_access_recertification.sql
CREATE TABLE IF NOT EXISTS recert_campaigns (
  id              TEXT PRIMARY KEY,
  name            TEXT NOT NULL,
  system_id       TEXT NOT NULL,     -- which system's access is being reviewed
  campaign_type   TEXT NOT NULL,     -- 'quarterly'|'annual'|'ad_hoc'
  status          TEXT NOT NULL DEFAULT 'scheduled',
  -- status: scheduled | active | completed | cancelled
  start_date      TEXT NOT NULL,
  deadline        TEXT NOT NULL,     -- reviewers must act by this date
  completed_at    TEXT,
  total_items     INTEGER DEFAULT 0,
  certified_count INTEGER DEFAULT 0,
  revoked_count   INTEGER DEFAULT 0,
  auto_revoked_count INTEGER DEFAULT 0,
  created_by      TEXT NOT NULL,
  created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recert_items (
  id              TEXT PRIMARY KEY,
  campaign_id     TEXT NOT NULL REFERENCES rebert_campaigns(id),
  user_id         TEXT NOT NULL,
  user_email      TEXT NOT NULL,
  user_name       TEXT NOT NULL,
  system_id       TEXT NOT NULL,
  role_id         TEXT NOT NULL,
  role_name       TEXT NOT NULL,
  permission_set  TEXT,              -- JSON array of specific permissions
  granted_at      TEXT NOT NULL,     -- when was this access originally granted
  granted_by      TEXT,
  reviewer_id     TEXT NOT NULL,     -- manager or system owner
  reviewer_email  TEXT NOT NULL,
  decision        TEXT,              -- NULL | 'certified' | 'revoked' | 'auto_revoked'
  decision_at     TEXT,
  decision_by     TEXT,              -- who made the decision (reviewer_id or 'system')
  decision_comment TEXT,
  revocation_executed INTEGER DEFAULT 0, -- 1 when the downstream revocation API was called
  revocation_error TEXT,
  snapshot_at     TEXT NOT NULL      -- time the entitlement was captured (campaign start)
);

CREATE INDEX idx_ri_campaign    ON rebert_items(campaign_id, decision);
CREATE INDEX idx_ri_reviewer    ON rebert_items(reviewer_id, campaign_id) WHERE decision IS NULL;
CREATE INDEX idx_ri_user        ON rebert_items(user_id, system_id);
CREATE INDEX idx_ri_undecided   ON rebert_items(campaign_id, reviewer_id)
  WHERE decision IS NULL;

CREATE TABLE IF NOT EXISTS rebert_audit_log (
  id          TEXT PRIMARY KEY,
  campaign_id TEXT NOT NULL,
  item_id     TEXT,
  event_time  TEXT NOT NULL,
  actor       TEXT NOT NULL,
  action      TEXT NOT NULL,
  detail      TEXT
);

-- Prevent backfilling decisions after campaign closes
CREATE TRIGGER IF NOT EXISTS rebert_no_decision_after_close
  BEFORE UPDATE OF decision ON rebert_items
  WHEN (SELECT status FROM rebert_campaigns WHERE id = NEW.campaign_id) = 'completed'
BEGIN
  SELECT RAISE(ABORT, 'Cannot change decision after campaign is completed');
END;
```

### 2. TypeScript types

```typescript
// src/types/recertification.ts
export type CampaignStatus = 'scheduled' | 'active' | 'completed' | 'cancelled';
export type RevertDecision = 'certified' | 'revoked' | 'auto_revoked';

export interface RevertCampaign {
  id: string;
  name: string;
  system_id: string;
  campaign_type: 'quarterly' | 'annual' | 'ad_hoc';
  status: CampaignStatus;
  start_date: string;
  deadline: string;
  completed_at?: string;
  total_items: number;
  certified_count: number;
  revoked_count: number;
  auto_revoked_count: number;
  created_by: string;
  created_at: string;
}

export interface RevertItem {
  id: string;
  campaign_id: string;
  user_id: string;
  user_email: string;
  user_name: string;
  system_id: string;
  role_id: string;
  role_name: string;
  permission_set?: string[];
  granted_at: string;
  granted_by?: string;
  reviewer_id: string;
  reviewer_email: string;
  decision?: RevertDecision;
  decision_at?: string;
  decision_by?: string;
  decision_comment?: string;
  revocation_executed: boolean;
  snapshot_at: string;
}
```

### 3. Campaign launch cron (Cloudflare Workers cron trigger)

```typescript
// src/cron/rebert-scheduler.ts
import type { D1Database } from '@cloudflare/workers-types';
import { uuidv7 } from '../lib/uuid';
import { snapshotEntitlements } from '../lib/entitlement-snapshot';
import { assignReviewers } from '../lib/reviewer-assignment';
import { sendReviewerNotifications } from '../lib/mailer';

// Triggered by cron: "0 6 1 1,4,7,10 *"  (quarterly: Jan/Apr/Jul/Oct 1st at 06:00 UTC)
export async function launchQuarterlyCampaign(
  db: D1Database,
  systemId: string,
  createdBy: string,
): Promise<string> {
  const id         = uuidv7();
  const start_date = new Date().toISOString();
  const deadline   = addDays(start_date, 14); // 14-day review window
  const name       = `Quarterly Access Review ${new Date().toISOString().slice(0, 7)}`;

  await db
    .prepare(`
      INSERT INTO rebert_campaigns
        (id, name, system_id, campaign_type, status, start_date, deadline, created_by, created_at)
      VALUES (?, ?, ?, 'quarterly', 'active', ?, ?, ?, ?)
    `)
    .bind(id, name, systemId, start_date, deadline, createdBy, start_date)
    .run();

  // Snapshot current entitlements (point-in-time, not live)
  const entitlements = await snapshotEntitlements(db, systemId, start_date);
  const withReviewers = await assignReviewers(db, entitlements);

  if (withReviewers.length === 0) {
    await db
      .prepare(`UPDATE rebert_campaigns SET status='completed', completed_at=?, total_items=0 WHERE id=?`)
      .bind(new Date().toISOString(), id)
      .run();
    return id;
  }

  // Insert all items in a single batch
  const inserts = withReviewers.map(item =>
    db.prepare(`
      INSERT INTO rebert_items
        (id, campaign_id, user_id, user_email, user_name, system_id,
         role_id, role_name, permission_set, granted_at, granted_by,
         reviewer_id, reviewer_email, snapshot_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `).bind(
      uuidv7(), id, item.user_id, item.user_email, item.user_name,
      systemId, item.role_id, item.role_name,
      item.permissions ? JSON.stringify(item.permissions) : null,
      item.granted_at, item.granted_by ?? null,
      item.reviewer_id, item.reviewer_email, start_date
    )
  );

  await db.batch(inserts);

  await db
    .prepare(`UPDATE rebert_campaigns SET total_items=? WHERE id=?`)
    .bind(withReviewers.length, id)
    .run();

  await sendReviewerNotifications(withReviewers, deadline, id);
  return id;
}
```

### 4. Entitlement snapshot helper

```typescript
// src/lib/entitlement-snapshot.ts
export interface Entitlement {
  user_id: string;
  user_email: string;
  user_name: string;
  role_id: string;
  role_name: string;
  permissions?: string[];
  granted_at: string;
  granted_by?: string;
}

export async function snapshotEntitlements(
  db: D1Database,
  systemId: string,
  snapshotAt: string
): Promise<Entitlement[]> {
  // Read from the access control table at the moment of campaign start.
  // This query must be idempotent — campaign re-runs should not double-snapshot.
  const { results } = await db
    .prepare(`
      SELECT
        u.id         AS user_id,
        u.email      AS user_email,
        u.name       AS user_name,
        r.id         AS role_id,
        r.name       AS role_name,
        ur.granted_at,
        ur.granted_by,
        r.permissions
      FROM user_roles ur
      JOIN users u ON u.id = ur.user_id
      JOIN roles r ON r.id = ur.role_id
      WHERE ur.system_id = ?
        AND ur.revoked_at IS NULL
      ORDER BY u.name, r.name
    `)
    .bind(systemId)
    .all<Entitlement>();

  return results;
}
```

### 5. Reviewer decision endpoint

```typescript
// src/routes/rebert.ts
const DecisionSchema = z.object({
  decision: z.enum(['certified', 'revoked']),
  comment:  z.string().optional(),
});

// PATCH /rebert/items/:item_id  — authenticated reviewer only
app.patch('/rebert/items/:item_id', requireAuth, async (c) => {
  const actor = c.get('actor');
  const body  = DecisionSchema.safeParse(await c.req.json());
  if (!body.success) return c.json({ error: body.error.flatten() }, 400);

  const item = await c.env.DB
    .prepare('SELECT * FROM rebert_items WHERE id = ?')
    .bind(c.req.param('item_id'))
    .first<RevertItem>();

  if (!item) return c.json({ error: 'Not found' }, 404);
  if (item.reviewer_id !== actor.id) {
    return c.json({ error: 'You are not the assigned reviewer for this item' }, 403);
  }
  if (item.decision) {
    return c.json({ error: `Decision already recorded: ${item.decision}` }, 409);
  }

  // Check campaign is still active
  const campaign = await c.env.DB
    .prepare('SELECT status, deadline FROM rebert_campaigns WHERE id = ?')
    .bind(item.campaign_id)
    .first<{ status: string; deadline: string }>();

  if (!campaign || campaign.status !== 'active') {
    return c.json({ error: 'Campaign is not active' }, 409);
  }
  if (new Date().toISOString() > campaign.deadline) {
    return c.json({ error: 'Campaign deadline has passed' }, 409);
  }

  const now = new Date().toISOString();
  const { decision, comment } = body.data;

  await c.env.DB
    .prepare(`
      UPDATE rebert_items
      SET decision=?, decision_at=?, decision_by=?, decision_comment=?
      WHERE id=?
    `)
    .bind(decision, now, actor.id, comment ?? null, item.id)
    .run();

  // If revoked, queue downstream revocation (executed by cron to ensure reliability)
  // The cron picks up revoked items where revocation_executed=0

  // Update campaign counters
  const countField = decision === 'certified' ? 'certified_count' : 'revoked_count';
  await c.env.DB
    .prepare(`UPDATE rebert_campaigns SET ${countField}=${countField}+1 WHERE id=?`)
    .bind(item.campaign_id)
    .run();

  await rebertAudit(c.env.DB, item.campaign_id, item.id, actor.id,
    decision === 'certified' ? 'CERTIFIED' : 'REVOKED', comment);

  return c.json({ id: item.id, decision, decision_at: now });
});
```

### 6. Auto-revoke cron (runs daily)

```typescript
// src/cron/auto-revoke.ts
export async function autoRevokeExpired(
  db: D1Database,
  revokeAccess: (userId: string, systemId: string, roleId: string) => Promise<void>
): Promise<number> {
  const now = new Date().toISOString();

  // Find all campaigns past deadline with undecided items
  const { results: overdue } = await db
    .prepare(`
      SELECT ri.*
      FROM rebert_items ri
      JOIN rebert_campaigns rc ON rc.id = ri.campaign_id
      WHERE rc.status = 'active'
        AND rc.deadline < ?
        AND ri.decision IS NULL
    `)
    .bind(now)
    .all<RevertItem>();

  let autoRevokedCount = 0;

  for (const item of overdue) {
    try {
      await revokeAccess(item.user_id, item.system_id, item.role_id);

      await db
        .prepare(`
          UPDATE rebert_items
          SET decision='auto_revoked', decision_at=?, decision_by='system',
              decision_comment='Auto-revoked: reviewer did not respond before deadline',
              revocation_executed=1
          WHERE id=?
        `)
        .bind(now, item.id)
        .run();

      await db
        .prepare(`
          UPDATE rebert_campaigns
          SET auto_revoked_count=auto_revoked_count+1
          WHERE id=?
        `)
        .bind(item.campaign_id)
        .run();

      await rebertAudit(db, item.campaign_id, item.id, 'system',
        'AUTO_REVOKED', `reviewer=${item.reviewer_email} did not respond`);

      autoRevokedCount++;
    } catch (err) {
      await db
        .prepare(`UPDATE rebert_items SET revocation_error=? WHERE id=?`)
        .bind(String(err), item.id)
        .run();
    }
  }

  // Close campaigns where all items are decided
  await db
    .prepare(`
      UPDATE rebert_campaigns
      SET status='completed', completed_at=?
      WHERE status='active'
        AND deadline < ?
        AND id NOT IN (
          SELECT DISTINCT campaign_id FROM rebert_items WHERE decision IS NULL
        )
    `)
    .bind(now, now)
    .run();

  return autoRevokedCount;
}
```

### 7. Campaign progress endpoint

```typescript
// GET /rebert/campaigns/:id/progress — compliance team view
app.get('/rebert/campaigns/:id/progress', requireRole('compliance-officer'), async (c) => {
  const campaign = await c.env.DB
    .prepare('SELECT * FROM rebert_campaigns WHERE id = ?')
    .bind(c.req.param('id'))
    .first<RevertCampaign>();
  if (!campaign) return c.json({ error: 'Not found' }, 404);

  const { results: undecided } = await c.env.DB
    .prepare(`
      SELECT reviewer_email, COUNT(*) AS pending
      FROM rebert_items
      WHERE campaign_id = ? AND decision IS NULL
      GROUP BY reviewer_email
      ORDER BY pending DESC
    `)
    .bind(campaign.id)
    .all<{ reviewer_email: string; pending: number }>();

  const completion_pct = campaign.total_items > 0
    ? Math.round(
        ((campaign.certified_count + campaign.revoked_count + campaign.auto_revoked_count)
          / campaign.total_items) * 100
      )
    : 100;

  return c.json({
    campaign,
    completion_pct,
    days_remaining: Math.max(0, Math.ceil(
      (new Date(campaign.deadline).getTime() - Date.now()) / 86_400_000
    )),
    reviewers_with_pending_items: undecided,
  });
});
```

## Implementation Details

- **Point-in-time snapshot**: entitlements are captured at campaign `start_date`. Reviewers see the state of access as it was when the campaign launched, not live data. This prevents gaming (revoking access moments before review to avoid scrutiny).
- **Fail-secure auto-revoke**: silence = revoke. This is the industry standard for access review. Documenting this policy in your ISMS before rollout avoids stakeholder surprise.
- **Batch INSERT**: using `db.batch()` for item creation ensures the campaign either has all its items or none — no partial state on failure.
- **Downstream revocation**: the `revokeAccess` callback is dependency-injected, making it easy to wire to your IAM system (Okta, Azure AD, custom roles table) without coupling the recertification logic to the access system.
- **Cron schedule**: `"0 6 1 1,4,7,10 *"` launches quarterly campaigns on the 1st of January, April, July, and October at 06:00 UTC. Adjust per regulatory requirement.

## Anti-patterns

- **Auto-certify on silence**: never approve access by default on non-response. Fail-secure means revoke.
- **Allowing reviewers to certify their own access**: the `reviewer_id !== actor.id` check for the item's `user_id` must also be enforced — a manager cannot certify their own entitlements.
- **Live entitlement queries during review**: reviewers might see access that changed after snapshot. Always work from the snapshot, not live joins.
- **Skipping the audit log for auto-revocations**: auto-revocations are regulatory events. Each one must appear in `rebert_audit_log` with `actor='system'` and the reason.

## Gotchas

- D1 does not support stored procedures. The auto-revoke cron runs in Workers — ensure the cron's CPU time budget (50 ms free plan, 30 s paid) is sufficient for the volume of items. For large campaigns (>10,000 items), batch the processing across multiple cron runs using a cursor.
- The `BEFORE UPDATE` trigger referencing a subquery on another table (`rebert_campaigns`) works in SQLite but is blocked in some D1 migration contexts. Test the trigger in a staging D1 instance before applying to production.
- Email notifications for reviewer reminders should include a direct link with a pre-signed token (not the reviewer's session cookie) so reviewers can click-to-decide without going through the full auth flow.

## Verification

```bash
# Launch a campaign manually (admin)
curl -X POST https://api.example.com/rebert/campaigns \
  -H 'Authorization: Bearer $ADMIN_TOKEN' \
  -d '{"system_id":"app-prod","campaign_type":"quarterly"}'

# Reviewer checks their pending items
curl https://api.example.com/rebert/my-items?campaign_id=<id> \
  -H 'Authorization: Bearer $REVIEWER_TOKEN'

# Submit a decision
curl -X PATCH https://api.example.com/rebert/items/<item_id> \
  -H 'Authorization: Bearer $REVIEWER_TOKEN' \
  -d '{"decision":"certified","comment":"User still needs this role"}'

# Check campaign progress
curl https://api.example.com/rebert/campaigns/<id>/progress \
  -H 'Authorization: Bearer $COMPLIANCE_TOKEN'

# Verify auto-revoke audit trail
wrangler d1 execute APP_DB \
  --command "SELECT * FROM rebert_audit_log WHERE action='AUTO_REVOKED' ORDER BY event_time DESC LIMIT 20"

# Check revocation errors
wrangler d1 execute APP_DB \
  --command "SELECT id, user_email, role_name, revocation_error FROM rebert_items WHERE revocation_error IS NOT NULL"
```

## Related

- `documentation/docs/policies/compliance/workers-hipaa-phi-access-logging-d1.md`
- `documentation/docs/policies/compliance/workers-gdpr-data-subject-rights-api.md`
- `documentation/docs/policies/compliance/workers-change-management-approval-d1.md`

## Sources

- SOC 2 Trust Services Criteria CC6.3 — Access Recertification
- ISO/IEC 27001:2022 Annex A.8.2 — Privileged Access Rights
- HIPAA Security Rule §164.308(a)(3) — Workforce Access Management
- PCI DSS v4.0 Requirement 7.2 — Access Control Systems and Processes
- NIST SP 800-53 Rev 5 — AC-2 Account Management
- Cloudflare D1 Docs: https://developers.cloudflare.com/d1/
- Cloudflare Workers Cron Triggers: https://developers.cloudflare.com/workers/configuration/cron-triggers/
