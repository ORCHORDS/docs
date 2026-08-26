# Automated Content Policy Rule Engine (Cloudflare Workers + D1)

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

example project's trust-and-safety team needs to define, test, and ship new content-moderation rules without engineering deployments. A rule might be: "if post contains ≥ 3 flagged-domain links AND author reputation < 0.4 AND post age < 60 s → quarantine". Hard-coding these in Worker code creates a deployment bottleneck and makes A/B testing impossible. A runtime rule engine stored in D1, evaluated in a Worker, solves both problems.

---

## Context

Rules are JSON documents stored in D1. Each rule has a unique slug, a priority (lower number = higher priority), a set of conditions (field, operator, value triples), an action (allow / warn / quarantine / remove), and an enabled flag. The evaluation Worker loads the active ruleset at startup (cached in memory for the Worker's lifetime, refreshed by a KV invalidation signal), evaluates rules in priority order, and returns the first matching action. Rules can be created and toggled by trust-and-safety staff via an internal API.

---

## 1. D1 Schema — Rule Store

```sql
-- migrations/0030_policy_rule_engine.sql
CREATE TABLE IF NOT EXISTS policy_rules (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  slug        TEXT    NOT NULL UNIQUE,
  priority    INTEGER NOT NULL DEFAULT 100,
  description TEXT,
  conditions  TEXT    NOT NULL,   -- JSON array of Condition objects
  action      TEXT    NOT NULL CHECK(action IN ('allow','warn','quarantine','remove')),
  enabled     INTEGER NOT NULL DEFAULT 1,
  created_at  INTEGER NOT NULL DEFAULT (unixepoch()),
  updated_at  INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX idx_pr_enabled_priority ON policy_rules(enabled, priority);

-- Audit log
CREATE TABLE IF NOT EXISTS policy_rule_audit (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  rule_slug  TEXT    NOT NULL,
  actor      TEXT    NOT NULL,
  change     TEXT    NOT NULL,   -- JSON diff
  changed_at INTEGER NOT NULL DEFAULT (unixepoch())
);
```

---

## 2. TypeScript Types — Conditions & Rules

```typescript
// src/types/policy-rules.ts
export type Operator =
  | 'eq' | 'neq'
  | 'gt' | 'gte' | 'lt' | 'lte'
  | 'contains' | 'not_contains'
  | 'in' | 'not_in'
  | 'matches_regex';

export interface Condition {
  field: string;        // e.g. "author.reputation_score", "post.link_count"
  operator: Operator;
  value: unknown;       // string | number | string[]
}

export interface PolicyRule {
  id: number;
  slug: string;
  priority: number;
  description: string | null;
  conditions: Condition[];
  action: 'allow' | 'warn' | 'quarantine' | 'remove';
  enabled: boolean;
}

export interface EvalContext {
  // flat dot-notation fields resolved by the caller
}

export interface EvalResult {
  action: PolicyRule['action'];
  matchedSlug: string;
  matchedPriority: number;
}
```

---

## 3. Rule Evaluator — Pure TypeScript

```typescript
// src/lib/rule-evaluator.ts
import { PolicyRule, Condition, EvalContext, EvalResult, Operator } from '../types/policy-rules';

function getField(ctx: EvalContext, field: string): unknown {
  // Support dot-notation: "author.reputation_score" → ctx["author.reputation_score"]
  return ctx[field] ?? ctx[field.split('.').reduce((obj: unknown, key) => {
    if (obj !== null && typeof obj === 'object') return (obj as Record<string, unknown>)[key];
    return undefined;
  }, ctx as unknown)];
}

function evaluateCondition(cond: Condition, ctx: EvalContext): boolean {
  const actual = getField(ctx, cond.field);
  const expected = cond.value;

  switch (cond.operator as Operator) {
    case 'eq':            return actual === expected;
    case 'neq':           return actual !== expected;
    case 'gt':            return typeof actual === 'number' && typeof expected === 'number' && actual > expected;
    case 'gte':           return typeof actual === 'number' && typeof expected === 'number' && actual >= expected;
    case 'lt':            return typeof actual === 'number' && typeof expected === 'number' && actual < expected;
    case 'lte':           return typeof actual === 'number' && typeof expected === 'number' && actual <= expected;
    case 'contains':      return typeof actual === 'string' && typeof expected === 'string' && actual.includes(expected);
    case 'not_contains':  return typeof actual === 'string' && typeof expected === 'string' && !actual.includes(expected);
    case 'in':            return Array.isArray(expected) && expected.includes(actual);
    case 'not_in':        return Array.isArray(expected) && !expected.includes(actual);
    case 'matches_regex': {
      if (typeof actual !== 'string' || typeof expected !== 'string') return false;
      try { return new RegExp(expected, 'i').test(actual); } catch { return false; }
    }
    default: return false;
  }
}

export function evaluateRules(rules: PolicyRule[], ctx: EvalContext): EvalResult | null {
  // Rules must be pre-sorted by priority ascending
  for (const rule of rules) {
    if (!rule.enabled) continue;
    const allMatch = rule.conditions.every(c => evaluateCondition(c, ctx));
    if (allMatch) {
      return { action: rule.action, matchedSlug: rule.slug, matchedPriority: rule.priority };
    }
  }
  return null;  // no match → caller decides default action
}
```

---

## 4. Rule Cache — KV-Invalidated In-Memory Store

```typescript
// src/lib/rule-cache.ts
import { Env } from '../types';
import { PolicyRule } from '../types/policy-rules';

let cachedRules: PolicyRule[] | null = null;
let cacheEtag: string | null = null;

export async function getActiveRules(env: Env): Promise<PolicyRule[]> {
  // Check KV for an invalidation token (written whenever rules change)
  const etag = await env.POLICY_KV.get('rules:etag');

  if (cachedRules && etag === cacheEtag) {
    return cachedRules;
  }

  // Reload from D1
  const { results } = await env.DB.prepare(
    `SELECT id, slug, priority, description, conditions, action, enabled
       FROM policy_rules
      WHERE enabled = 1
      ORDER BY priority ASC`
  ).all<{
    id: number; slug: string; priority: number; description: string | null;
    conditions: string; action: string; enabled: number;
  }>();

  cachedRules = results.map(r => ({
    id: r.id,
    slug: r.slug,
    priority: r.priority,
    description: r.description,
    conditions: JSON.parse(r.conditions),
    action: r.action as PolicyRule['action'],
    enabled: r.enabled === 1,
  }));

  cacheEtag = etag;
  return cachedRules;
}
```

---

## 5. Rule Management API — Create / Toggle / Audit

```typescript
// src/workers/policy-rule-admin.ts
import { Env } from '../types';
import { Condition } from '../types/policy-rules';
import { requireInternalAuth } from '../lib/auth';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (!requireInternalAuth(request, env)) return new Response('Unauthorized', { status: 401 });

    const url = new URL(request.url);
    const slug = url.pathname.split('/').pop() ?? '';

    if (request.method === 'POST') {
      const { slug: bodySlug, priority, description, conditions, action } = await request.json<{
        slug: string; priority?: number; description?: string;
        conditions: Condition[]; action: string;
      }>();

      await env.DB.prepare(
        `INSERT INTO policy_rules (slug, priority, description, conditions, action)
         VALUES (?, ?, ?, ?, ?)`
      )
        .bind(bodySlug, priority ?? 100, description ?? null, JSON.stringify(conditions), action)
        .run();

      await invalidateRuleCache(env, bodySlug, 'created', request);
      return new Response(JSON.stringify({ ok: true }), { status: 201 });
    }

    if (request.method === 'PATCH') {
      const patch = await request.json<{ enabled?: boolean; priority?: number; conditions?: Condition[] }>();
      const sets: string[] = ['updated_at = unixepoch()'];
      const binds: unknown[] = [];

      if (patch.enabled !== undefined) { sets.push('enabled = ?'); binds.push(patch.enabled ? 1 : 0); }
      if (patch.priority !== undefined) { sets.push('priority = ?'); binds.push(patch.priority); }
      if (patch.conditions !== undefined) { sets.push('conditions = ?'); binds.push(JSON.stringify(patch.conditions)); }

      binds.push(slug);
      await env.DB.prepare(`UPDATE policy_rules SET ${sets.join(', ')} WHERE slug = ?`)
        .bind(...binds).run();

      await invalidateRuleCache(env, slug, 'updated', request);
      return new Response(JSON.stringify({ ok: true }), { status: 200 });
    }

    return new Response('Method Not Allowed', { status: 405 });
  },
};

async function invalidateRuleCache(env: Env, slug: string, change: string, request: Request): Promise<void> {
  const etag = crypto.randomUUID();
  await env.POLICY_KV.put('rules:etag', etag);
  await env.DB.prepare(
    `INSERT INTO policy_rule_audit (rule_slug, actor, change) VALUES (?, ?, ?)`
  )
    .bind(slug, request.headers.get('X-Actor-Id') ?? 'unknown', JSON.stringify({ change }))
    .run();
}
```

---

## 6. Integration — Post-Submission Evaluation

```typescript
// src/workers/post-submit.ts (excerpt)
import { getActiveRules } from '../lib/rule-cache';
import { evaluateRules } from '../lib/rule-evaluator';
import { buildEvalContext } from '../lib/context-builder';
import { Env } from '../types';

export async function evaluatePostPolicy(postId: string, env: Env): Promise<string> {
  const rules = await getActiveRules(env);
  const ctx = await buildEvalContext(postId, env);  // resolves author reputation, link counts, etc.
  const result = evaluateRules(rules, ctx);

  const action = result?.action ?? 'allow';

  await env.DB.prepare(
    `INSERT INTO post_moderation_log (post_id, action, rule_slug, evaluated_at)
     VALUES (?, ?, ?, unixepoch())`
  )
    .bind(postId, action, result?.matchedSlug ?? null)
    .run();

  return action;
}
```

---

## Anti-patterns

- **Storing compiled RegExp in D1.** Always compile regex at evaluation time with a try/catch; malformed patterns in the DB must not crash the Worker.
- **Reloading rules on every request.** The KV etag pattern avoids D1 round-trips on every request while still propagating rule changes within one Worker lifecycle.
- **Allowing `matches_regex` on untrusted input without length limits.** Enforce a maximum regex length (e.g. 500 chars) in the admin API to prevent ReDoS.
- **Skipping audit logs on rule changes.** Every mutation must be written to `policy_rule_audit`; trust-and-safety teams rely on this for incident investigation.

---

## Gotchas

- Worker in-process module-level caches (`cachedRules`) are reset on every new isolate; on high-traffic Workers this means many isolates will cold-miss and hit D1 simultaneously on deploy. Add a short `Cache-Control` on the KV response to stagger reloads.
- D1's `JSON.parse` is JavaScript's native parser; floats stored as TEXT may lose precision — store numeric values as REAL columns, not inside JSON blobs.
- The `in` / `not_in` operators use `Array.includes` which is O(n); for large arrays (e.g. a blocklist of 1 000 domain hashes) use a `Set` at evaluation time.

---

## Verification

```typescript
// tests/rule-evaluator.test.ts
import { describe, it, expect } from 'vitest';
import { evaluateRules } from '../src/lib/rule-evaluator';
import { PolicyRule } from '../src/types/policy-rules';

const rules: PolicyRule[] = [
  {
    id: 1, slug: 'low-rep-spam', priority: 10, description: null, enabled: true,
    action: 'quarantine',
    conditions: [
      { field: 'author.reputation_score', operator: 'lt', value: 0.4 },
      { field: 'post.link_count', operator: 'gte', value: 3 },
    ],
  },
];

describe('evaluateRules', () => {
  it('quarantines low-rep posts with many links', () => {
    const ctx = { 'author.reputation_score': 0.2, 'post.link_count': 5 };
    expect(evaluateRules(rules, ctx)?.action).toBe('quarantine');
  });

  it('allows high-rep posts even with many links', () => {
    const ctx = { 'author.reputation_score': 0.9, 'post.link_count': 5 };
    expect(evaluateRules(rules, ctx)).toBeNull();
  });
});
```

---

## Related

- `cross-platform-content-policy-enforcement-workers.md`
- `real-time-toxic-content-scoring-workers-ai.md`
- `report-queue-prioritization-workers-queues-ai.md`
- `platform-audit-log-immutable-d1-workers.md`
- `shadow-banning-reach-limiting-d1-workers.md`

---

## Sources

- Cloudflare D1 Docs: https://developers.cloudflare.com/d1/
- Cloudflare Workers KV: https://developers.cloudflare.com/kv/
- OWASP — ReDoS: https://owasp.org/www-community/attacks/Regular_expression_Denial_of_Service_-_ReDoS
- DSA Article 16 — Notice and Action Mechanisms
