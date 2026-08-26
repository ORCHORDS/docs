# NIST 800-53 AC Family Access Control Implementation with Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

**Symptom / Use-case**

FedRAMP Moderate / High authorisations and FISMA compliance require demonstrable implementation of NIST SP 800-53r5 Access Control (AC) family controls. Platform teams deploying APIs and microservices on Cloudflare Workers must map Workers primitives to AC controls and produce artefact evidence. This article covers AC-2 (Account Management), AC-3 (Access Enforcement), AC-4 (Information Flow Enforcement), AC-6 (Least Privilege), and AC-17 (Remote Access) with TypeScript Workers code that generates verifiable audit evidence in D1.

**Context**

NIST 800-53r5 AC family has 25 controls. Workers deployments most commonly satisfy: AC-2 (managing service accounts and API keys as system accounts), AC-3 (enforcing RBAC on API endpoints), AC-4 (controlling data flows between Workers and downstream services), AC-6 (limiting Worker bindings to the minimum required), and AC-17 (ensuring remote API access runs over mTLS or signed tokens). Evidence must show *what* control is implemented, *how* it operates, and *how* violations are detected and logged.

---

## AC-2: Account Management — API Key Lifecycle in D1

```typescript
// AC-2: Automated account (API key) provisioning, review, and disabling
export interface Env {
  ACCESS_DB: D1Database;
  AUDIT_LOG: D1Database;
}

export interface ServiceAccount {
  id: string;
  name: string;
  role: string;
  key_hash: string;       // SHA-256 of the raw API key — never store plaintext
  created_at: string;
  last_used_at: string | null;
  expires_at: string;
  status: 'active' | 'disabled' | 'expired';
  created_by: string;
}

// AC-2(3): Disable accounts after inactivity period (90 days)
export async function reviewDormantAccounts(db: D1Database): Promise<void> {
  await db.prepare(`
    UPDATE service_accounts
    SET status = 'disabled', disabled_reason = 'AC-2(3): 90-day inactivity'
    WHERE status = 'active'
      AND (
        last_used_at IS NULL AND created_at < datetime('now', '-90 days')
        OR last_used_at < datetime('now', '-90 days')
      )
  `).run();
}

// AC-2(2): Automatically disable temporary accounts at expiry
export async function expireTemporaryAccounts(db: D1Database): Promise<void> {
  await db.prepare(`
    UPDATE service_accounts
    SET status = 'expired'
    WHERE status = 'active' AND expires_at < datetime('now')
  `).run();
}

// AC-2(12): Account monitoring — log all key usage
export async function logAccountUsage(
  auditDb: D1Database,
  accountId: string,
  endpoint: string,
  outcome: 'allowed' | 'denied'
): Promise<void> {
  await auditDb.prepare(`
    INSERT INTO ac_audit_log (account_id, endpoint, outcome, ts)
    VALUES (?1, ?2, ?3, datetime('now'))
  `).bind(accountId, endpoint, outcome).run();
}
```

## AC-3: Access Enforcement — RBAC Middleware

```typescript
// AC-3: Enforce role-based access decisions on every request
type Role = 'reader' | 'writer' | 'admin';
type Permission = 'data:read' | 'data:write' | 'admin:*';

const ROLE_PERMISSIONS: Record<Role, Permission[]> = {
  reader: ['data:read'],
  writer: ['data:read', 'data:write'],
  admin:  ['data:read', 'data:write', 'admin:*'],
};

function hasPermission(role: Role, required: Permission): boolean {
  return ROLE_PERMISSIONS[role]?.some(
    p => p === required || p === 'admin:*'
  ) ?? false;
}

export async function enforceAC3(
  req: Request,
  env: Env,
  requiredPermission: Permission
): Promise<Response | null> {
  const token = req.headers.get('Authorization')?.replace('Bearer ', '');
  if (!token) {
    return Response.json(
      { error: 'AC-3: Missing authorization token', control: 'NIST-800-53r5-AC-3' },
      { status: 401 }
    );
  }

  // Verify token and retrieve role from D1
  const tokenHash = await hashToken(token);
  const account = await env.ACCESS_DB.prepare(
    `SELECT id, role, status FROM service_accounts WHERE key_hash = ?1`
  ).bind(tokenHash).first<{ id: string; role: Role; status: string }>();

  if (!account || account.status !== 'active') {
    await logAccountUsage(env.AUDIT_LOG, account?.id ?? 'unknown', req.url, 'denied');
    return Response.json(
      { error: 'AC-3: Access denied', control: 'NIST-800-53r5-AC-3' },
      { status: 403 }
    );
  }

  if (!hasPermission(account.role, requiredPermission)) {
    await logAccountUsage(env.AUDIT_LOG, account.id, req.url, 'denied');
    return Response.json(
      { error: `AC-3: Role '${account.role}' lacks '${requiredPermission}'` },
      { status: 403 }
    );
  }

  await logAccountUsage(env.AUDIT_LOG, account.id, req.url, 'allowed');
  return null; // Access granted — continue to handler
}

async function hashToken(token: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(token));
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('');
}
```

## AC-4: Information Flow Enforcement — Outbound Allow-list

```typescript
// AC-4: Restrict information flows to approved destinations only
const APPROVED_EGRESS: string[] = [
  'https://api.internal.example.com',
  'https://storage.example.com',
];

export async function enforcedFetch(
  url: string,
  init?: RequestInit
): Promise<Response> {
  const origin = new URL(url).origin;
  if (!APPROVED_EGRESS.some(allowed => url.startsWith(allowed))) {
    throw new Error(
      `AC-4 violation: outbound request to '${origin}' not in approved egress list`
    );
  }
  return fetch(url, init);
}
```

## AC-6: Least Privilege — Binding Scope Validation

```typescript
// AC-6: Verify Worker bindings at startup; refuse to start with excess permissions
// wrangler.toml — document each binding's business justification
// [[d1_databases]]
//   binding = "USER_DB"       # AC-6 justification: read/write user records for auth
// [[r2_buckets]]
//   binding = "UPLOADS"       # AC-6 justification: write user-uploaded files only

// Runtime assertion — document which bindings exist; alert if unexpected ones appear
export function assertMinimalBindings(env: Record<string, unknown>): void {
  const EXPECTED_BINDINGS = new Set(['USER_DB', 'AUDIT_LOG', 'UPLOADS', 'CACHE']);
  const actual = new Set(Object.keys(env).filter(k => typeof env[k] === 'object'));

  for (const b of actual) {
    if (!EXPECTED_BINDINGS.has(b)) {
      // This fires in staging; in production log to SIEM and page on-call
      console.error(`AC-6 alert: unexpected binding '${b}' — review least-privilege configuration`);
    }
  }
}
```

## AC-17: Remote Access — mTLS Enforcement

```typescript
// AC-17: All remote access (API calls from external systems) must use mTLS
// Cloudflare mTLS is enforced at the edge via Mutual TLS certificate rules;
// the Worker validates the client certificate identity at application layer.
export default {
  async fetch(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // CF-Client-Cert-Verified is set by Cloudflare's mTLS termination
    const certVerified = req.headers.get('CF-Client-Cert-Verified');
    const certSerial   = req.headers.get('CF-Client-Cert-Serial');

    if (certVerified !== 'SUCCESS' || !certSerial) {
      return Response.json(
        { error: 'AC-17: Valid client certificate required for remote access' },
        { status: 401 }
      );
    }

    // Check revocation list in D1
    const revoked = await env.ACCESS_DB.prepare(
      `SELECT 1 FROM revoked_certs WHERE serial = ?1`
    ).bind(certSerial).first();

    if (revoked) {
      return Response.json({ error: 'AC-17: Client certificate revoked' }, { status: 401 });
    }

    // Log remote access session (AC-17(1): Automated monitoring)
    await env.AUDIT_LOG.prepare(
      `INSERT INTO remote_access_log (cert_serial, url, ts) VALUES (?1, ?2, datetime('now'))`
    ).bind(certSerial, req.url).run();

    return handleRequest(req, env, ctx);
  }
} satisfies ExportedHandler<Env>;

declare function handleRequest(r: Request, e: Env, c: ExecutionContext): Promise<Response>;
```

## Evidence Export for FedRAMP Assessors

```typescript
// Produce AC control evidence package as JSON for the SAR
export async function exportACEvidence(env: Env): Promise<Record<string, unknown>> {
  const [accounts, auditSample, remoteSample] = await Promise.all([
    env.ACCESS_DB.prepare(
      `SELECT role, status, COUNT(*) AS n FROM service_accounts GROUP BY role, status`
    ).all(),
    env.AUDIT_LOG.prepare(
      `SELECT outcome, COUNT(*) AS n FROM ac_audit_log
       WHERE ts > datetime('now', '-30 days') GROUP BY outcome`
    ).all(),
    env.AUDIT_LOG.prepare(
      `SELECT COUNT(*) AS n FROM remote_access_log WHERE ts > datetime('now', '-30 days')`
    ).first<{ n: number }>(),
  ]);

  return {
    generated_at: new Date().toISOString(),
    control_family: 'AC',
    framework: 'NIST-800-53r5',
    ac2_account_summary: accounts.results,
    ac3_access_decisions_30d: auditSample.results,
    ac17_remote_sessions_30d: remoteSample?.n ?? 0,
  };
}
```

**Anti-patterns**

- Embedding role checks inline per handler instead of a shared `enforceAC3` middleware — divergence means some endpoints miss the control, which is an AC-3 finding.
- Using KV for the account store — KV offers no transactional updates; concurrent disablement and usage can produce stale reads. D1 with WAL mode ensures consistency.
- Logging only denied decisions — AC-2(12) requires monitoring of *all* account usage, including successful access, to detect anomalous patterns.
- Hard-coding the egress allow-list in source code without a migration path — store it in D1 so it can be updated without a code deployment (which itself requires change management evidence).

**Gotchas**

- `CF-Client-Cert-Verified` is only present when Cloudflare mTLS rules are active for the zone; test in staging with a real certificate, not a self-signed one rejected by Cloudflare's CA validation.
- NIST 800-53r5 AC-3(7) (Role-Based Access Control) is an enhancement that requires explicit evidence of role definitions — keep the `ROLE_PERMISSIONS` map versioned in D1, not only in code.
- AC-2(9) (Shared Account Restriction) requires that service-to-service Workers use distinct accounts per integration, not a shared `internal` key — enforce this in the provisioning workflow.
- The 90-day inactivity window for AC-2(3) is an FedRAMP baseline requirement; FISMA Low systems may accept 180 days — confirm with your AO before hardcoding.

**Verification**

```bash
# Confirm dormant accounts were disabled
wrangler d1 execute ACCESS_DB --command \
  "SELECT COUNT(*) FROM service_accounts WHERE status='disabled' AND disabled_reason LIKE 'AC-2(3)%';"

# Confirm AC-3 denial rate (should flag anomalies if > 5%)
wrangler d1 execute AUDIT_LOG --command \
  "SELECT outcome, COUNT(*) FROM ac_audit_log WHERE ts > datetime('now','-7 days') GROUP BY outcome;"
```

**Related**

- `nist-800-53-control-families.md`
- `nist-800-53r5-tailoring-decision-record.md`
- `fedramp-compliance.md`
- `fisma-compliance-controls-workers.md`
- `soc2-cc6-logical-access-controls.md`
- `audit-log-mandatory.md`

**Sources**

- NIST SP 800-53 Rev. 5 — Security and Privacy Controls for Information Systems and Organizations, AC Family
- NIST SP 800-53A Rev. 5 — Assessing Security Controls (assessment procedures for AC)
- FedRAMP Baseline Controls (Moderate), AC family requirements
- Cloudflare Docs — Mutual TLS (mTLS) for Workers
