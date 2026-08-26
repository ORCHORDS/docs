# ISO 27001 Continuous Monitoring Automation — Cloudflare Workers and D1

- Date: 2026-08-22
- Author: example.com
- Status: production

## Problem: Maintaining Annex A Evidence Without Manual Toil

ISO 27001:2022 requires that organisations continually monitor their information security controls (clauses 9.1 and 10.1) and retain objective evidence that controls remain effective. In practice, most teams rely on annual audits supplemented by quarterly manual checks — a pattern that leaves non-conformities undetected for months and forces last-minute evidence collection before external audits. Cloudflare Workers' scheduled cron triggers can run control checks on any cadence without additional infrastructure, writing machine-readable evidence directly to D1.

The monitoring architecture treats each Annex A control as a testable assertion. Workers poll internal APIs, inspect Cloudflare configuration (via the Cloudflare API), query D1 for data-integrity invariants, and compare results against expected baselines stored in a controls table. When a check fails the Worker inserts a non-conformity record and enqueues a notification. All control evidence rows are append-only — no update or delete on evidence tables — so the evidence trail is tamper-evident and satisfies clause 7.5 (documented information).

Logpush is configured to stream Worker invocation logs to an R2 bucket, which serves as the external audit trail required by clause 9.1. The bucket is write-only for the Logpush service account, satisfying A.8.3 (information backup) and A.5.33 (protection of records).

## Context

- Runtime: Cloudflare Workers (cron triggers + ES modules)
- Database: D1 (control evidence, non-conformity register)
- Storage: R2 (Logpush audit trail)
- External: Cloudflare API (zone/WAF/TLS configuration checks)
- Standard: ISO/IEC 27001:2022 Annex A, Clauses 9.1, 10.1

## Scheduled Control Scan Worker

Each cron invocation iterates the active controls list from D1 and dispatches the appropriate check function. Results are written as evidence rows. The `check_fn` column stores a key that maps to a registered check function.

```ts
// src/scheduled/control-scan.ts
import { Env } from '../types';

type ControlRow = { id: string; ref: string; check_fn: string; expected: string };

const checks: Record<string, (env: Env, expected: string) => Promise<boolean>> = {
  tls_min_version: async (env, expected) => {
    const res = await fetch(
      `https://api.cloudflare.com/client/v4/zones/${env.CF_ZONE_ID}/settings/min_tls_version`,
      { headers: { Authorization: `Bearer ${env.CF_API_TOKEN}` } }
    );
    const data = await res.json<{ result: { value: string } }>();
    return data.result.value >= expected; // e.g. "1.2"
  },

  waf_enabled: async (env, _expected) => {
    const res = await fetch(
      `https://api.cloudflare.com/client/v4/zones/${env.CF_ZONE_ID}/firewall/waf/packages`,
      { headers: { Authorization: `Bearer ${env.CF_API_TOKEN}` } }
    );
    const data = await res.json<{ result: Array<{ detection_mode: string }> }>();
    return data.result.some(p => p.detection_mode !== 'off');
  },

  mfa_required: async (env, _expected) => {
    const row = await env.DB.prepare(
      `SELECT COUNT(*) as cnt FROM users WHERE mfa_enabled = 0 AND role IN ('admin','owner')`
    ).first<{ cnt: number }>();
    return (row?.cnt ?? 1) === 0;
  },

  active_access_review: async (env, _expected) => {
    const row = await env.DB.prepare(
      `SELECT completed_at FROM access_reviews ORDER BY completed_at DESC LIMIT 1`
    ).first<{ completed_at: string }>();
    if (!row) return false;
    const daysSince = (Date.now() - new Date(row.completed_at).getTime()) / 86_400_000;
    return daysSince <= 90; // Annex A.8.2 — quarterly access review
  },
};

export async function runControlScan(env: Env): Promise<void> {
  const controls = await env.DB.prepare(
    `SELECT id, ref, check_fn, expected FROM controls WHERE active = 1`
  ).all<ControlRow>();

  const ts = new Date().toISOString();
  const stmts = [];

  for (const ctrl of controls.results) {
    const fn = checks[ctrl.check_fn];
    if (!fn) continue;
    let passed = false;
    let detail = '';
    try {
      passed = await fn(env, ctrl.expected);
    } catch (err) {
      detail = String(err);
    }

    stmts.push(env.DB.prepare(
      `INSERT INTO control_evidence (control_id, checked_at, passed, detail)
       VALUES (?, ?, ?, ?)`
    ).bind(ctrl.id, ts, passed ? 1 : 0, detail));

    if (!passed) {
      stmts.push(env.DB.prepare(
        `INSERT INTO nonconformities (control_id, ref, detected_at, status, detail)
         VALUES (?, ?, ?, 'open', ?)`
      ).bind(ctrl.id, ctrl.ref, ts, detail || 'Automated check failed'));
    }
  }
  await env.DB.batch(stmts);
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext) {
    ctx.waitUntil(runControlScan(env));
  },
};
```

## Non-Conformity Register API

The API exposes the non-conformity register for dashboard consumption and auditor access. Clause 10.1 requires that non-conformities be actioned and closed with evidence of corrective action; the `resolution` column captures this evidence inline.

```ts
// src/handlers/nonconformities.ts
export async function listNonconformities(req: Request, env: Env): Promise<Response> {
  const url = new URL(req.url);
  const status = url.searchParams.get('status') ?? 'open';

  const rows = await env.DB.prepare(
    `SELECT id, control_id, ref, detected_at, status, detail, resolved_at, resolution
     FROM nonconformities WHERE status = ? ORDER BY detected_at DESC LIMIT 200`
  ).bind(status).all();

  return Response.json({ items: rows.results, total: rows.results.length });
}

export async function resolveNonconformity(req: Request, env: Env): Promise<Response> {
  const { id, resolution } = await req.json<{ id: number; resolution: string }>();
  if (!resolution || resolution.length < 20) {
    return new Response('Resolution must describe corrective action taken', { status: 400 });
  }
  const now = new Date().toISOString();
  await env.DB.prepare(
    `UPDATE nonconformities SET status='closed', resolved_at=?, resolution=? WHERE id=?`
  ).bind(now, resolution, id).run();

  // Append immutable closure evidence
  await env.DB.prepare(
    `INSERT INTO control_evidence (control_id, checked_at, passed, detail)
     SELECT control_id, ?, 1, ? FROM nonconformities WHERE id=?`
  ).bind(now, `Closed: ${resolution}`, id).run();

  return Response.json({ closed: true, resolvedAt: now });
}
```

## D1 Schema and Logpush Audit Trail

```sql
-- D1 schema: iso27001_monitoring.sql
CREATE TABLE IF NOT EXISTS controls (
  id TEXT PRIMARY KEY,
  ref TEXT NOT NULL,           -- e.g. "A.8.5"
  title TEXT NOT NULL,
  check_fn TEXT NOT NULL,
  expected TEXT NOT NULL DEFAULT '',
  active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS control_evidence (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  control_id TEXT NOT NULL,
  checked_at TEXT NOT NULL,
  passed INTEGER NOT NULL,
  detail TEXT
  -- no UPDATE/DELETE permitted on this table (enforce via IAM)
);

CREATE TABLE IF NOT EXISTS nonconformities (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  control_id TEXT NOT NULL,
  ref TEXT NOT NULL,
  detected_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  detail TEXT,
  resolved_at TEXT,
  resolution TEXT
);

CREATE TABLE IF NOT EXISTS access_reviews (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  completed_at TEXT NOT NULL,
  reviewer TEXT NOT NULL,
  scope TEXT
);

-- Logpush config (wrangler.toml excerpt):
-- [logpush]
-- dataset = "workers_trace_events"
-- destination = "r2://iso27001-audit-trail/{date}"
-- fields = ["Event","Outcome","ScriptName","Timestamp"]
```

## Evidence Dashboard Query

A nightly summary query provides the clause 9.1 monitoring report: percentage of controls passing over the previous 30 days, grouped by Annex A domain.

```ts
// src/handlers/monitoring-report.ts
export async function getMonitoringReport(env: Env): Promise<Response> {
  const report = await env.DB.prepare(`
    SELECT
      substr(c.ref, 1, 2) AS domain,
      COUNT(DISTINCT c.id) AS total_controls,
      SUM(CASE WHEN ce.passed = 1 THEN 1 ELSE 0 END) AS passed,
      SUM(CASE WHEN ce.passed = 0 THEN 1 ELSE 0 END) AS failed,
      MAX(ce.checked_at) AS last_checked
    FROM controls c
    LEFT JOIN control_evidence ce
      ON ce.control_id = c.id
      AND ce.checked_at >= datetime('now', '-30 days')
    WHERE c.active = 1
    GROUP BY domain
    ORDER BY domain
  `).all();

  return Response.json({
    generatedAt: new Date().toISOString(),
    period: 'last_30_days',
    domains: report.results,
  });
}
```

## Anti-patterns

- Writing `UPDATE` statements on evidence rows to "correct" a false positive — this destroys the tamper-evident property; instead insert a new evidence row with a corrective note.
- Running checks only during the hours leading up to an audit — continuous means continuous; auditors will inspect the `checked_at` histogram.
- Storing expected baselines as hardcoded constants in Worker code — they must live in D1 so changes are logged via D1's built-in audit and cannot be silently deployed.
- Treating a passing check as evidence for multiple Annex A controls simultaneously without recording which controls were assessed.

## Gotchas

- D1 cron Workers and HTTP Workers share the same D1 binding but run in separate isolates — do not rely on in-memory caches between them.
- Cloudflare API rate limits apply to the zone-settings endpoints; stagger checks across multiple cron schedules (e.g., TLS checks hourly, WAF checks every 6 hours).
- ISO 27001:2022 clause 9.1 requires you to define what to monitor, when, and who analyses results — document these decisions in the controls table `title` column so the schema itself is part of your documented information.
- Logpush delivers logs asynchronously; there may be a lag of several minutes between a Worker invocation and log availability in R2.

## Verification

```ts
// tests/control-scan.spec.ts
import { expect, test, vi } from 'vitest';
import { runControlScan } from '../src/scheduled/control-scan';

test('failed check creates nonconformity row', async () => {
  const env = getMiniflareEnv(); // local D1 binding
  await env.DB.prepare(
    `INSERT INTO controls (id, ref, title, check_fn, expected, active)
     VALUES ('c1', 'A.8.5', 'MFA on admins', 'mfa_required', '', 1)`
  ).run();
  // Insert admin user without MFA
  await env.DB.prepare(
    `INSERT INTO users (id, role, mfa_enabled) VALUES ('u1', 'admin', 0)`
  ).run();

  await runControlScan(env);

  const nc = await env.DB.prepare(
    `SELECT * FROM nonconformities WHERE control_id = 'c1'`
  ).first();
  expect(nc).not.toBeNull();
  expect(nc?.status).toBe('open');
});
```

## Related

- [iso-27001-compliance.md](iso-27001-compliance.md)
- [iso-27001-internal-audit-process.md](iso-27001-internal-audit-process.md)
- [iso-27001-risk-assessment-methodology.md](iso-27001-risk-assessment-methodology.md)
- [audit-log-mandatory.md](audit-log-mandatory.md)
- [soc2-evidence-collection-automation.md](soc2-evidence-collection-automation.md)

## Sources

- ISO/IEC 27001:2022 — Clauses 9.1, 10.1, Annex A: https://www.iso.org/standard/27001
- ISO/IEC 27002:2022 — Implementation guidance: https://www.iso.org/standard/75652.html
- Cloudflare Logpush: https://developers.cloudflare.com/logs/logpush/
- Cloudflare Workers Cron Triggers: https://developers.cloudflare.com/workers/configuration/cron-triggers/
