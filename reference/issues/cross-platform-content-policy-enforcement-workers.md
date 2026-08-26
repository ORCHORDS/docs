# Cross-Platform Content Policy Enforcement with Workers Middleware

- Date: 2026-08-22
- Author: example.com
- Status: production

## Jurisdiction-Aware Policy at the Edge

Operating a UGC platform across the EU, UK, and other jurisdictions means applying materially different content rules to the same underlying content. The EU Digital Services Act mandates transparency reporting and algorithmic accountability. The UK Online Safety Act introduces category thresholds that differ from DSA. Local laws in countries like Germany (NetzDG), France, and Australia add further obligations. A monolithic content policy applied globally either over-blocks in permissive jurisdictions or under-blocks where stricter rules apply.

Workers middleware intercepts every content-delivery request, resolves the user's jurisdiction from Cloudflare's built-in `cf.country` field, fetches the applicable rule set from KV, and enforces policy before any content payload reaches the client. This approach keeps policy logic at the edge — close to the user — without requiring backend changes per jurisdiction, and makes audit logging straightforward because every enforcement decision flows through the same middleware layer.

The architecture separates rule storage (KV), enforcement logic (Workers middleware), and audit persistence (D1) into independent concerns so that legal teams can update rules in KV without code deployments, and compliance engineers can query D1 for audit trails without touching production Workers.

## Context

- Runtime: Cloudflare Workers (fetch handler middleware)
- Rule storage: Cloudflare KV (per-jurisdiction JSON rule sets, ~1 KB each)
- Audit log: Cloudflare D1
- Geo signal: `request.cf.country` (ISO 3166-1 alpha-2)
- Frameworks: none — vanilla Workers fetch handler chain

## KV Rule Set Schema and Loading

Rules are stored as JSON in KV under `policy:COUNTRY_CODE`. Each rule set lists blocked categories, required age-gate categories, and mandatory takedown response SLAs. The middleware caches the fetched rule in the Worker's module-level `Map` to avoid a KV read on every request within the same isolate lifetime.

```ts
// lib/policy-loader.ts
export interface ContentRule {
  jurisdiction: string;
  blockedCategories: string[];
  ageGateCategories: string[];
  mandatoryTakedownSlaHours: number;
  requiresTransparencyReport: boolean;
  law: string; // e.g. "EU-DSA", "UK-OSA", "DE-NetzDG"
}

const ruleCache = new Map<string, { rule: ContentRule; cachedAt: number }>();
const CACHE_TTL_MS = 60_000; // re-fetch from KV every 60 s

export async function getContentRule(country: string, env: Env): Promise<ContentRule> {
  const cached = ruleCache.get(country);
  if (cached && Date.now() - cached.cachedAt < CACHE_TTL_MS) {
    return cached.rule;
  }

  const raw = await env.POLICY_KV.get(`policy:${country}`);
  const rule: ContentRule = raw
    ? JSON.parse(raw)
    : await env.POLICY_KV.get('policy:DEFAULT').then((d) => JSON.parse(d!));

  ruleCache.set(country, { rule, cachedAt: Date.now() });
  return rule;
}
```

## Enforcement Middleware

The middleware wraps the downstream fetch handler. It resolves the rule, checks the content's categories (embedded in a signed request header or fetched from a lightweight D1 lookup), and either blocks, age-gates, or passes the request through.

```ts
// middleware/policy-enforcement.ts
import { getContentRule, ContentRule } from '../lib/policy-loader';
import { logEnforcementAction } from '../lib/audit-logger';

export async function enforcePolicyMiddleware(
  request: Request,
  env: Env,
  ctx: ExecutionContext,
  next: () => Promise<Response>
): Promise<Response> {
  const country = (request as any).cf?.country ?? 'XX';
  const contentCategories: string[] = JSON.parse(
    request.headers.get('X-Content-Categories') ?? '[]'
  );
  const contentId = request.headers.get('X-Content-Id') ?? 'unknown';
  const userId = request.headers.get('X-User-Id') ?? 'anonymous';

  const rule = await getContentRule(country, env);

  // Check hard-blocked categories
  const blocked = contentCategories.filter((c) => rule.blockedCategories.includes(c));
  if (blocked.length > 0) {
    ctx.waitUntil(
      logEnforcementAction(env, {
        contentId,
        userId,
        country,
        action: 'block',
        reason: `category:${blocked.join(',')}`,
        law: rule.law,
        timestamp: Date.now(),
      })
    );
    return new Response(JSON.stringify({ error: 'Content unavailable in your region', code: 'POLICY_BLOCK' }), {
      status: 451,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  // Check age-gate categories
  const needsAgeGate = contentCategories.some((c) => rule.ageGateCategories.includes(c));
  if (needsAgeGate) {
    const ageVerified = request.headers.get('X-Age-Verified') === 'true';
    if (!ageVerified) {
      ctx.waitUntil(
        logEnforcementAction(env, {
          contentId, userId, country, action: 'age-gate', reason: 'unverified', law: rule.law, timestamp: Date.now(),
        })
      );
      return new Response(JSON.stringify({ error: 'Age verification required', code: 'AGE_GATE' }), {
        status: 403,
        headers: { 'Content-Type': 'application/json' },
      });
    }
  }

  return next();
}
```

## Audit Logging to D1

Every enforcement action writes a row to D1 asynchronously via `ctx.waitUntil` so it does not add to response latency. The table is append-only; a separate cron Worker aggregates rows for DSA transparency reports.

```ts
// lib/audit-logger.ts
export interface AuditEntry {
  contentId: string;
  userId: string;
  country: string;
  action: 'block' | 'age-gate' | 'pass';
  reason: string;
  law: string;
  timestamp: number;
}

export async function logEnforcementAction(env: Env, entry: AuditEntry): Promise<void> {
  await env.DB.prepare(
    `INSERT INTO content_enforcement_log
       (content_id, user_id, country, action, reason, law, ts)
     VALUES (?, ?, ?, ?, ?, ?, ?)`
  )
    .bind(entry.contentId, entry.userId, entry.country, entry.action, entry.reason, entry.law, entry.timestamp)
    .run();
}

// Schema (run once via D1 migration)
// CREATE TABLE content_enforcement_log (
//   id        INTEGER PRIMARY KEY AUTOINCREMENT,
//   content_id TEXT NOT NULL,
//   user_id   TEXT NOT NULL,
//   country   TEXT NOT NULL,
//   action    TEXT NOT NULL,
//   reason    TEXT NOT NULL,
//   law       TEXT NOT NULL,
//   ts        INTEGER NOT NULL
// );
// CREATE INDEX idx_cel_country_ts ON content_enforcement_log (country, ts);
```

## Anti-patterns

- Hardcoding jurisdiction rules in Worker source — rules must be editable without deploys
- Fetching rules from KV on every request without in-memory caching — cold KV reads add 20-50 ms
- Logging synchronously in the response path — always use `ctx.waitUntil`
- Trusting client-supplied `X-Content-Categories` without a signature — sign and verify this header
- Using a single `policy:GLOBAL` key for all countries — makes targeted updates impossible

## Gotchas

- `request.cf.country` returns `T1` for Tor exit nodes; add an explicit rule for `T1`
- KV consistency is eventually consistent; rule updates may lag up to 60 s in cached isolates
- D1 write throughput is limited to ~1000 writes/sec per database; batch audit rows under viral load
- HTTP 451 ("Unavailable For Legal Reasons") is the correct status for jurisdiction blocks per RFC 7725
- UK OSA and EU DSA have overlapping but non-identical category taxonomies; maintain separate rule sets

## Verification

```ts
// Verify that a DE-NetzDG blocked category returns 451
const req = new Request('https://api.example.com/content/123', {
  headers: {
    'X-Content-Categories': JSON.stringify(['hate-speech']),
    'X-Content-Id': '123',
    'X-User-Id': 'u_test',
    'CF-IPCountry': 'DE',
  },
});
const res = await enforcePolicyMiddleware(req, mockEnv, mockCtx, async () => new Response('ok'));
console.assert(res.status === 451, 'DE hate-speech must return 451');
```

## Related

- `documentation/categories/issues/dsa-risk-assessment.md`
- `documentation/categories/issues/eu-dsa-recommender-2026.md`
- `documentation/categories/issues/ai-bias-fairness-standards-2026.md`
- `documentation/categories/issues/automated-dispute-resolution-d1-appeals-workflow.md`

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
- https://developers.cloudflare.com/kv/
- https://developers.cloudflare.com/d1/
- https://www.rfc-editor.org/rfc/rfc7725
- https://digital-strategy.ec.europa.eu/en/policies/digital-services-act-package
