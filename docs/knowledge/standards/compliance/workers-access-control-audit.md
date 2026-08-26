# Access Control Audit Logging in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need a complete, tamper-resistant record of every permission check in your system — who tried to access what, with which role, and whether it was allowed or denied. You also need to detect privilege escalation attempts in real time, generate quarterly access review reports for SOC 2 / ISO 27001, identify unused permissions to support the principle of least privilege, and maintain a full role assignment history in D1. All of this should run in Cloudflare Workers with no additional servers.

## Context

Access control audit logging is required by:
- **SOC 2 CC6.1 / CC6.2** — Logical access security, registration and de-registration
- **ISO 27001 A.9.2 / A.9.4** — User access management and access control to systems
- **GDPR Art. 32** — Security of processing, including access control
- **HIPAA § 164.312(b)** — Audit controls

Cloudflare Analytics Engine provides append-only, queryable event storage ideal for immutable audit logs. D1 stores the authoritative role assignment history and current permission grants.

## Solution

```typescript
import { AnalyticsEngineDataset } from '@cloudflare/workers-types';

export interface Env {
  DB: D1Database;
  ACCESS_AUDIT_AE: AnalyticsEngineDataset; // Analytics Engine dataset
  INTERNAL_API_SECRET: string;
}

// ─── Core types ───────────────────────────────────────────────────────────────

type AccessDecision = 'allow' | 'deny';
type AuditAction =
  | 'read' | 'write' | 'delete' | 'admin'
  | 'role_assign' | 'role_revoke' | 'permission_check';

interface AccessEvent {
  principal: string;      // userId or service account ID
  principalType: 'user' | 'service';
  resource: string;       // e.g. "orders:order_123", "admin:users"
  action: AuditAction;
  decision: AccessDecision;
  reason?: string;        // why denied, or rule that granted access
  roles: string[];        // roles the principal held at check time
  ip?: string;
  userAgent?: string;
  requestId: string;
  timestamp: string;
}

// ─── Analytics Engine logging ─────────────────────────────────────────────────

function logAccessEvent(env: Env, event: AccessEvent): void {
  // Analytics Engine uses writeDataPoint — fire-and-forget, no await needed
  env.ACCESS_AUDIT_AE.writeDataPoint({
    blobs: [
      event.principal,
      event.principalType,
      event.resource,
      event.action,
      event.decision,
      event.reason ?? '',
      event.roles.join(','),
      event.ip ?? '',
      event.userAgent ?? '',
      event.requestId,
    ],
    doubles: [
      event.decision === 'deny' ? 1 : 0,  // index 0: isDeny
      event.decision === 'allow' ? 1 : 0, // index 1: isAllow
      Date.now(),                          // index 2: epoch ms
    ],
    indexes: [event.principal],  // partition by principal for efficient queries
  });
}

// ─── Permission check middleware ──────────────────────────────────────────────

interface PermissionCheckResult {
  allowed: boolean;
  matchedRule?: string;
  principalRoles: string[];
}

async function checkPermission(
  env: Env,
  principal: string,
  resource: string,
  action: AuditAction,
  request: Request
): Promise<PermissionCheckResult> {
  // Fetch principal's current roles from D1
  const { results: roleRows } = await env.DB.prepare(
    `SELECT r.name FROM user_roles ur
     JOIN roles r ON ur.role_id = r.id
     WHERE ur.user_id = ? AND ur.revoked_at IS NULL`
  )
    .bind(principal)
    .all<{ name: string }>();
  const roles = roleRows.map((r) => r.name);

  // Fetch matching permission grants for these roles
  const placeholders = roles.map(() => '?').join(',');
  const permQuery = roles.length > 0
    ? await env.DB.prepare(
        `SELECT rp.action, rp.resource_pattern, rp.rule_name
         FROM role_permissions rp
         WHERE rp.role_name IN (${placeholders})
           AND rp.action = ?
           AND ? GLOB rp.resource_pattern`
      )
        .bind(...roles, action, resource)
        .first<{ action: string; resource_pattern: string; rule_name: string }>()
    : null;

  const allowed = !!permQuery;
  const event: AccessEvent = {
    principal,
    principalType: 'user',
    resource,
    action,
    decision: allowed ? 'allow' : 'deny',
    reason: allowed ? permQuery!.rule_name : 'no_matching_grant',
    roles,
    ip: request.headers.get('CF-Connecting-IP') ?? undefined,
    userAgent: request.headers.get('User-Agent') ?? undefined,
    requestId: request.headers.get('CF-Ray') ?? crypto.randomUUID(),
    timestamp: new Date().toISOString(),
  };

  logAccessEvent(env, event);

  return { allowed, matchedRule: permQuery?.rule_name, principalRoles: roles };
}

// ─── Privilege escalation detection ───────────────────────────────────────────

async function detectPrivilegeEscalation(
  env: Env,
  principal: string,
  newRole: string,
  grantedBy: string,
  request: Request
): Promise<{ escalationDetected: boolean; reason?: string }> {
  // Fetch current roles to compare privilege level
  const { results: currentRoles } = await env.DB.prepare(
    `SELECT r.name, r.privilege_level FROM user_roles ur
     JOIN roles r ON ur.role_id = r.id
     WHERE ur.user_id = ? AND ur.revoked_at IS NULL`
  )
    .bind(principal)
    .all<{ name: string; privilege_level: number }>();

  const newRoleRow = await env.DB.prepare(
    `SELECT privilege_level FROM roles WHERE name = ?`
  )
    .bind(newRole)
    .first<{ privilege_level: number }>();

  if (!newRoleRow) return { escalationDetected: false };

  const maxCurrentLevel = Math.max(0, ...currentRoles.map((r) => r.privilege_level));
  const escalationDetected = newRoleRow.privilege_level > maxCurrentLevel + 1;

  if (escalationDetected) {
    // Log escalation as a deny event
    logAccessEvent(env, {
      principal,
      principalType: 'user',
      resource: `role:${newRole}`,
      action: 'role_assign',
      decision: 'deny',
      reason: `privilege_escalation: level ${maxCurrentLevel} → ${newRoleRow.privilege_level} skipping levels`,
      roles: currentRoles.map((r) => r.name),
      ip: request.headers.get('CF-Connecting-IP') ?? undefined,
      requestId: request.headers.get('CF-Ray') ?? crypto.randomUUID(),
      timestamp: new Date().toISOString(),
    });
  }

  return {
    escalationDetected,
    reason: escalationDetected
      ? `Attempted jump from level ${maxCurrentLevel} to ${newRoleRow.privilege_level}`
      : undefined,
  };
}

// ─── Role assignment history ───────────────────────────────────────────────────

async function assignRole(
  env: Env,
  userId: string,
  roleName: string,
  grantedBy: string,
  reason: string,
  request: Request
): Promise<{ success: boolean; escalationBlocked?: boolean }> {
  const escalation = await detectPrivilegeEscalation(env, userId, roleName, grantedBy, request);
  if (escalation.escalationDetected) {
    return { success: false, escalationBlocked: true };
  }

  const roleRow = await env.DB.prepare(`SELECT id FROM roles WHERE name = ?`)
    .bind(roleName).first<{ id: string }>();
  if (!roleRow) return { success: false };

  const now = new Date().toISOString();
  await env.DB.prepare(
    `INSERT INTO user_roles (id, user_id, role_id, granted_by, granted_reason, granted_at)
     VALUES (?, ?, ?, ?, ?, ?)`
  )
    .bind(crypto.randomUUID(), userId, roleRow.id, grantedBy, reason, now)
    .run();

  logAccessEvent(env, {
    principal: userId,
    principalType: 'user',
    resource: `role:${roleName}`,
    action: 'role_assign',
    decision: 'allow',
    reason: `granted_by:${grantedBy} — ${reason}`,
    roles: [roleName],
    requestId: request.headers.get('CF-Ray') ?? crypto.randomUUID(),
    timestamp: now,
  });

  return { success: true };
}

// ─── Quarterly access review report ───────────────────────────────────────────

interface AccessReviewReport {
  generatedAt: string;
  periodStart: string;
  periodEnd: string;
  totalUsers: number;
  usersWithPrivilegedAccess: unknown[];
  unusedPermissions: unknown[];
  recentEscalationAttempts: unknown[];
  roleAssignmentChanges: unknown[];
}

async function generateQuarterlyReport(env: Env): Promise<AccessReviewReport> {
  const periodEnd = new Date();
  const periodStart = new Date();
  periodStart.setDate(periodStart.getDate() - 90);

  const [totalUsersRow, privilegedUsers, roleChanges, escalations, unusedPerms] = await Promise.all([
    env.DB.prepare(`SELECT COUNT(DISTINCT user_id) as cnt FROM user_roles WHERE revoked_at IS NULL`)
      .first<{ cnt: number }>(),

    env.DB.prepare(
      `SELECT u.id, u.email, GROUP_CONCAT(r.name) as roles, MAX(r.privilege_level) as max_level
       FROM user_roles ur
       JOIN users u ON ur.user_id = u.id
       JOIN roles r ON ur.role_id = r.id
       WHERE ur.revoked_at IS NULL AND r.privilege_level >= 5
       GROUP BY u.id, u.email
       ORDER BY max_level DESC
       LIMIT 100`
    ).all().then((r) => r.results),

    env.DB.prepare(
      `SELECT ur.user_id, r.name as role_name, ur.granted_by, ur.granted_at, ur.granted_reason
       FROM user_roles ur
       JOIN roles r ON ur.role_id = r.id
       WHERE ur.granted_at > ? OR ur.revoked_at > ?
       ORDER BY COALESCE(ur.revoked_at, ur.granted_at) DESC
       LIMIT 200`
    )
      .bind(periodStart.toISOString(), periodStart.toISOString())
      .all().then((r) => r.results),

    // Escalation attempts in the period — from D1 shadow log (Analytics Engine not directly queryable in Worker)
    env.DB.prepare(
      `SELECT * FROM access_audit_shadow
       WHERE action = 'role_assign' AND decision = 'deny'
         AND reason LIKE 'privilege_escalation%'
         AND timestamp > ?
       LIMIT 50`
    )
      .bind(periodStart.toISOString())
      .all().then((r) => r.results),

    env.DB.prepare(
      `SELECT rp.role_name, rp.action, rp.resource_pattern, rp.rule_name,
              COALESCE(MAX(al.timestamp), 'never') as last_used
       FROM role_permissions rp
       LEFT JOIN access_audit_shadow al
         ON al.decision = 'allow' AND al.reason = rp.rule_name
            AND al.timestamp > ?
       GROUP BY rp.rule_name
       HAVING last_used = 'never'
       LIMIT 100`
    )
      .bind(periodStart.toISOString())
      .all().then((r) => r.results),
  ]);

  return {
    generatedAt: new Date().toISOString(),
    periodStart: periodStart.toISOString(),
    periodEnd: periodEnd.toISOString(),
    totalUsers: totalUsersRow?.cnt ?? 0,
    usersWithPrivilegedAccess: privilegedUsers,
    unusedPermissions: unusedPerms,
    recentEscalationAttempts: escalations,
    roleAssignmentChanges: roleChanges,
  };
}

// ─── Main Worker ───────────────────────────────────────────────────────────────

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const auth = request.headers.get('Authorization');

    // Permission check hook — called by application middleware
    if (url.pathname === '/access/check' && request.method === 'POST') {
      // No auth required — this is called by trusted internal services
      const { principal, resource, action } =
        await request.json<{ principal: string; resource: string; action: AuditAction }>();
      const result = await checkPermission(env, principal, resource, action, request);
      return new Response(JSON.stringify(result), {
        headers: { 'Content-Type': 'application/json' },
      });
    }

    // All admin endpoints require internal secret
    if (auth !== `Bearer ${env.INTERNAL_API_SECRET}`) {
      return new Response('Unauthorized', { status: 401 });
    }

    if (url.pathname === '/access/assign-role' && request.method === 'POST') {
      const { userId, roleName, grantedBy, reason } =
        await request.json<{ userId: string; roleName: string; grantedBy: string; reason: string }>();
      const result = await assignRole(env, userId, roleName, grantedBy, reason, request);
      return new Response(JSON.stringify(result), {
        status: result.success ? 200 : 403,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    if (url.pathname === '/access/review-report') {
      const report = await generateQuarterlyReport(env);
      return new Response(JSON.stringify(report, null, 2), {
        headers: { 'Content-Type': 'application/json' },
      });
    }

    return new Response('Not found', { status: 404 });
  },
};
```

## Implementation Details

**Analytics Engine**: `writeDataPoint` is synchronous-interface, non-blocking — it does not await network I/O, making it safe to call in the hot path of every request without adding latency. Data is available for SQL queries via the Analytics Engine GraphQL/SQL API within ~1 minute.

**Triple logging (resource + action + principal)**: Every `AccessEvent` captures all three elements of the access control triple, plus `decision`, `reason`, `roles`, and `requestId`. This enables queries like "all deny events for resource X" or "all allow events by principal Y in role Z".

**D1 shadow log**: Analytics Engine is queryable externally but not from within a Worker. A lightweight `access_audit_shadow` D1 table mirrors critical events (escalation attempts, role changes) for use in the quarterly report query. Insert into it alongside the AE `writeDataPoint` call for audit trail completeness.

**D1 schema**:
```sql
CREATE TABLE roles (
  id TEXT PRIMARY KEY,
  name TEXT UNIQUE NOT NULL,
  privilege_level INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE user_roles (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  role_id TEXT NOT NULL,
  granted_by TEXT NOT NULL,
  granted_reason TEXT,
  granted_at TEXT NOT NULL,
  revoked_at TEXT,
  revoked_by TEXT
);
CREATE TABLE role_permissions (
  id TEXT PRIMARY KEY,
  role_name TEXT NOT NULL,
  action TEXT NOT NULL,
  resource_pattern TEXT NOT NULL,  -- SQLite GLOB pattern, e.g. "orders:*"
  rule_name TEXT NOT NULL UNIQUE
);
CREATE TABLE access_audit_shadow (
  id TEXT PRIMARY KEY,
  principal TEXT NOT NULL,
  resource TEXT NOT NULL,
  action TEXT NOT NULL,
  decision TEXT NOT NULL,
  reason TEXT,
  roles TEXT,
  timestamp TEXT NOT NULL
);
```

## Anti-patterns

- **Do not** perform permission checks without logging — silent access creates unauditable systems.
- **Do not** allow privilege escalation by skipping levels — an `operator` (level 3) should not jump directly to `superadmin` (level 8) in one assignment.
- **Do not** delete rows from `access_audit_shadow` or `user_roles` — mark them `revoked`; deletion destroys the historical record.
- **Do not** expose the `GET /access/review-report` endpoint publicly — it contains sensitive role and access information.
- **Do not** use GLOB patterns so broad (e.g., `*`) that they match unintended resources — tighten patterns to the minimum needed resource scope.

## Gotchas

- **Analytics Engine query lag**: AE data takes ~1 minute to become queryable. Do not use AE for real-time gating decisions; use D1 for synchronous permission checks.
- **GLOB patterns in SQLite**: SQLite's GLOB is case-sensitive and uses `*` (not `%`) as wildcard. `LIKE` with `%` is case-insensitive — pick one and document which.
- **Role many-to-many**: `user_roles` is a join table; the same `user_id` can have multiple rows with different `role_id`s. The permission check fetches all active roles and checks any match.
- **Privilege level gaps**: Define `privilege_level` values with gaps (1, 5, 10, 20) rather than 1, 2, 3 to allow future intermediate roles without renumbering.
- **CF-Ray uniqueness**: `CF-Ray` is unique per request at the edge and is a suitable `requestId` correlator. In local development (`wrangler dev`), it may be absent — fallback to `crypto.randomUUID()`.

## Verification

```bash
# 1. Check permission (should allow for an admin user)
curl -X POST https://api.example.com/access/check \
  -H 'Content-Type: application/json' \
  -d '{"principal":"user_admin_1","resource":"orders:order_123","action":"read"}'
# Expected: {"allowed":true,"matchedRule":"admin_read_orders",...}

# 2. Test privilege escalation blocking
curl -X POST https://api.example.com/access/assign-role \
  -H 'Authorization: Bearer <SECRET>' \
  -H 'Content-Type: application/json' \
  -d '{"userId":"user_1","roleName":"superadmin","grantedBy":"user_admin_1","reason":"test"}'
# Expected: {"success":false,"escalationBlocked":true}

# 3. Generate quarterly review
curl https://api.example.com/access/review-report \
  -H 'Authorization: Bearer <SECRET>' | jq '{
    totalUsers: .totalUsers,
    privilegedCount: (.usersWithPrivilegedAccess | length),
    unusedPermissionCount: (.unusedPermissions | length),
    escalationAttempts: (.recentEscalationAttempts | length)
  }'

# 4. Query Analytics Engine (external)
curl -X POST https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/analytics_engine/sql \
  -H 'Authorization: Bearer <CF_API_TOKEN>' \
  -d 'SELECT blob4 as action, blob5 as decision, COUNT() as cnt
      FROM ACCESS_AUDIT_AE
      WHERE timestamp > NOW() - INTERVAL 7 DAY
      GROUP BY action, decision
      ORDER BY cnt DESC'
```

## Related

- `documentation/docs/policies/compliance/soc2-audit-trail.md` — SOC 2 uses this access log as evidence
- `documentation/docs/policies/compliance/audit-log-immutable-r2.md` — immutable append-only log companion
- `documentation/docs/policies/compliance/workers-breach-notification-system.md` — access anomalies feed breach detection
- `documentation/docs/policies/compliance/hipaa-phi-encryption.md` — PHI access must be logged per HIPAA § 164.312(b)
- `documentation/docs/policies/compliance/workers-data-subject-access-request.md` — audit log included in DSAR exports

## Sources

- SOC 2 Trust Services Criteria CC6.1, CC6.2, CC6.3
- ISO/IEC 27001:2022 Annex A 9.2 (User access management), 9.4 (System and application access control)
- GDPR Article 32 — Security of processing
- HIPAA Security Rule § 164.312(b) — Audit controls
- Cloudflare Analytics Engine: https://developers.cloudflare.com/analytics/analytics-engine/
- Cloudflare D1: https://developers.cloudflare.com/d1/
- NIST SP 800-92 — Guide to Computer Security Log Management
