# Privacy-Preserving Analytics with Differential Privacy in Workers

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

You run a SaaS application on Cloudflare Workers and need to expose aggregate analytics — page view counts, feature adoption rates, error frequencies, funnel conversion ratios — to internal dashboards or to tenant-facing analytics endpoints. Two competing requirements collide:

1. **Privacy**: Raw event logs contain PII (user IDs, IP addresses, session tokens). GDPR Article 89 and CCPA require that analytics data not allow re-identification of individuals. Aggregation alone is insufficient when group sizes are small (the "aggregation fallacy").
2. **Utility**: The analytics must be accurate enough to drive product decisions.

Differential privacy (DP) provides a mathematical guarantee: adding or removing any single individual's data changes query results by at most a controlled amount, making re-identification statistically infeasible regardless of what auxiliary data an attacker possesses.

## Context

Differential privacy was formalised by Dwork et al. (2006). The key definition:

> A randomised algorithm M satisfies (ε, δ)-differential privacy if for all datasets D₁ and D₂ differing in a single record, and for all output sets S:
> Pr[M(D₁) ∈ S] ≤ e^ε · Pr[M(D₂) ∈ S] + δ

**ε (epsilon)** is the privacy budget. Smaller ε → stronger privacy guarantee → more noise added. Typical values:
- ε ≤ 0.1: very strong (census-grade)
- ε ≤ 1.0: strong (standard for product analytics)
- ε ≤ 10.0: weak (only useful with very large populations)

**δ (delta)** is a small failure probability, typically 10⁻⁵ to 10⁻⁷. For count queries with integer outputs, δ = 0 is achievable with the Laplace mechanism.

**Sensitivity** is the maximum amount a single individual's data can change a query result. For count queries, sensitivity = 1. For sum queries over bounded values [lo, hi], sensitivity = hi - lo.

Workers run this as **central differential privacy**: raw events are stored in D1 or KV, and noise is added at query time before the result leaves the Worker. This is simpler to implement than local DP but requires trusting the Workers infrastructure not to leak raw data — which Cloudflare's architecture supports through its isolate-per-request model and lack of persistent in-memory state.

## Laplace Mechanism Implementation

The Laplace mechanism adds noise drawn from a Laplace distribution with scale b = sensitivity / ε.

```typescript
// src/differential-privacy.ts

/**
 * Sample from the Laplace distribution with mean 0 and scale b.
 * Uses the inverse CDF method: if U ~ Uniform(-0.5, 0.5),
 * then X = -b * sign(U) * ln(1 - 2|U|) ~ Laplace(0, b).
 */
function laplaceSample(scale: number): number {
  // crypto.getRandomValues gives cryptographically secure uniform bytes
  const buf = new Uint32Array(1);
  crypto.getRandomValues(buf);
  // Map to (-0.5, 0.5) — exclude exactly 0 to avoid ln(1) = 0
  const u = (buf[0] / 0xffffffff) - 0.5;
  if (u === 0) return 0;
  return -scale * Math.sign(u) * Math.log(1 - 2 * Math.abs(u));
}

/**
 * Apply (ε, 0)-DP Laplace noise to a count query result.
 *
 * @param trueCount   The raw aggregate count from D1 or KV.
 * @param epsilon     Privacy budget (0 < ε ≤ 10 recommended).
 * @param sensitivity Query sensitivity (1 for counts).
 * @returns           Noisy integer count (clamped to ≥ 0).
 */
export function privatiseCount(
  trueCount: number,
  epsilon: number,
  sensitivity: number = 1
): number {
  const scale = sensitivity / epsilon;
  const noise = laplaceSample(scale);
  // Round and clamp: counts must be non-negative integers
  return Math.max(0, Math.round(trueCount + noise));
}

/**
 * Apply (ε, 0)-DP Laplace noise to a sum query over bounded values.
 *
 * @param trueSum   The raw aggregate sum.
 * @param epsilon   Privacy budget.
 * @param lo        Lower bound of individual values (for sensitivity calculation).
 * @param hi        Upper bound of individual values (for sensitivity calculation).
 */
export function privatiseSum(
  trueSum: number,
  epsilon: number,
  lo: number,
  hi: number
): number {
  const sensitivity = hi - lo;
  const scale = sensitivity / epsilon;
  const noise = laplaceSample(scale);
  return trueSum + noise;
}

/**
 * Apply DP to a histogram (array of counts, one per bucket).
 * Each bucket independently receives Laplace noise.
 *
 * Note: the epsilon here is PER BUCKET. If you query k buckets
 * simultaneously, the total epsilon consumed is k * epsilon_per_bucket
 * under basic composition. Use the advanced composition theorem
 * (or Rényi DP) for tighter bounds.
 */
export function privatiseHistogram(
  counts: Record<string, number>,
  epsilonPerBucket: number
): Record<string, number> {
  const result: Record<string, number> = {};
  for (const [key, count] of Object.entries(counts)) {
    result[key] = privatiseCount(count, epsilonPerBucket);
  }
  return result;
}
```

## Budget Tracking with Cloudflare D1

DP guarantees degrade when the same dataset is queried repeatedly. Each query "spends" epsilon. Track the cumulative budget per tenant to enforce limits.

```sql
-- migrations/0004_dp_budget.sql
CREATE TABLE dp_budget_ledger (
  tenant_id   TEXT    NOT NULL,
  date        TEXT    NOT NULL,  -- ISO 8601 date, reset daily
  epsilon_used REAL   NOT NULL DEFAULT 0.0,
  PRIMARY KEY (tenant_id, date)
);
```

```typescript
// src/budget.ts
export const DAILY_EPSILON_LIMIT = 10.0; // adjust to your threat model

export async function checkAndDeductBudget(
  db: D1Database,
  tenantId: string,
  epsilonRequested: number
): Promise<{ allowed: boolean; remaining: number }> {
  const today = new Date().toISOString().slice(0, 10);

  // Atomic upsert + read in a single D1 transaction
  const result = await db.batch([
    db.prepare(
      `INSERT INTO dp_budget_ledger (tenant_id, date, epsilon_used)
       VALUES (?, ?, 0)
       ON CONFLICT (tenant_id, date) DO NOTHING`
    ).bind(tenantId, today),
    db.prepare(
      `SELECT epsilon_used FROM dp_budget_ledger WHERE tenant_id = ? AND date = ?`
    ).bind(tenantId, today),
  ]);

  const used = (result[1].results[0] as any)?.epsilon_used ?? 0;
  const remaining = DAILY_EPSILON_LIMIT - used;

  if (epsilonRequested > remaining) {
    return { allowed: false, remaining };
  }

  await db.prepare(
    `UPDATE dp_budget_ledger
     SET epsilon_used = epsilon_used + ?
     WHERE tenant_id = ? AND date = ?`
  ).bind(epsilonRequested, tenantId, today).run();

  return { allowed: true, remaining: remaining - epsilonRequested };
}
```

## Analytics Query Handler

```typescript
// src/index.ts
import { privatiseCount, privatiseHistogram } from './differential-privacy';
import { checkAndDeductBudget, DAILY_EPSILON_LIMIT } from './budget';

interface Env {
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (!url.pathname.startsWith('/analytics/')) {
      return new Response('Not found', { status: 404 });
    }

    const tenantId = request.headers.get('X-Tenant-Id') ?? 'default';
    const EPSILON = 1.0; // per query

    const budget = await checkAndDeductBudget(env.DB, tenantId, EPSILON);
    if (!budget.allowed) {
      return Response.json(
        { error: 'Daily privacy budget exhausted', remaining: 0 },
        {
          status: 429,
          headers: {
            'X-DP-Budget-Remaining': '0',
            'X-DP-Budget-Daily-Limit': String(DAILY_EPSILON_LIMIT),
          },
        }
      );
    }

    if (url.pathname === '/analytics/page-views') {
      const row = await env.DB
        .prepare(`SELECT COUNT(*) as cnt FROM events WHERE type = 'page_view' AND tenant_id = ?`)
        .bind(tenantId)
        .first<{ cnt: number }>();

      const noisyCount = privatiseCount(row?.cnt ?? 0, EPSILON);

      return Response.json(
        { page_views: noisyCount },
        {
          headers: {
            'X-DP-Epsilon': String(EPSILON),
            'X-DP-Budget-Remaining': String(budget.remaining),
          },
        }
      );
    }

    if (url.pathname === '/analytics/feature-histogram') {
      const rows = await env.DB
        .prepare(
          `SELECT feature, COUNT(*) as cnt
           FROM events
           WHERE type = 'feature_use' AND tenant_id = ?
           GROUP BY feature`
        )
        .bind(tenantId)
        .all<{ feature: string; cnt: number }>();

      const rawHistogram: Record<string, number> = {};
      for (const row of rows.results) {
        rawHistogram[row.feature] = row.cnt;
      }

      // Composition: k buckets × ε_per_bucket consumed above
      const epsilonPerBucket = EPSILON / Object.keys(rawHistogram).length;
      const noisyHistogram = privatiseHistogram(rawHistogram, epsilonPerBucket);

      return Response.json({ features: noisyHistogram });
    }

    return new Response('Unknown analytics endpoint', { status: 404 });
  },
};
```

## Local DP for Client-Side Collection (Randomized Response)

For the highest privacy guarantees, apply noise on the client before data reaches your servers. Randomized response (the simplest local DP mechanism) lets each client independently report a boolean with noise:

```typescript
// Runs in the browser or mobile app — never on the server
function localDpBooleanReport(trueValue: boolean, epsilon: number): boolean {
  // Probability of reporting the true value
  const p = Math.exp(epsilon) / (1 + Math.exp(epsilon));
  const buf = new Uint8Array(1);
  crypto.getRandomValues(buf);
  const flip = buf[0] / 255 < p;
  return flip ? trueValue : !trueValue;
}

// Calibrate the aggregate on the server side:
// true_proportion ≈ (observed_proportion - (1-p)) / (2p - 1)
```

## Anti-patterns

**Do not reuse the same epsilon budget for exploratory analysis.** Ad-hoc SQL queries against the raw events table bypass DP entirely. Enforce that all analytical queries go through the `privatiseCount` / `privatiseHistogram` path by revoking direct D1 read access from the analytics API binding.

**Do not set ε > 10 and call it "private."** At ε = 10, the guarantee is near-meaningless for small cohorts. If utility requires low noise and populations are small, suppress results entirely for buckets with fewer than a configurable minimum group size (e.g., k-anonymity with k ≥ 5).

**Do not forget composition.** Querying 20 histogram buckets at ε = 1 each costs ε = 20 under basic composition. Use the Rényi DP advanced composition theorem or limit the number of buckets returned per request.

**Do not log raw event data in production if it contains direct identifiers.** Strip PII at ingestion time (hash user IDs with a server-side secret, truncate IPs to /24) before storing in D1.

## Gotchas

- **Integer rounding reveals information**: Rounding the noisy count to the nearest integer introduces a small bias. For small populations this is acceptable; for large ones it is negligible. Always document that returned counts are approximate.
- **Zero suppression is not DP-compliant**: If you suppress buckets where the noisy count ≤ 0 you leak information (the true count was small). Instead return 0 for all non-negative noisy counts including zero.
- **Budget resets must be time-zone-aware**: Use UTC dates for the D1 key to avoid a timezone boundary letting users double-spend at midnight.
- **D1 race condition on budget**: Two simultaneous requests from the same tenant can both pass the budget check before either deducts. Use a D1 transaction or a Durable Object as a serialised budget ledger for strict enforcement.

## Verification

```bash
# Verify the analytics endpoint returns noisy counts
curl -H "X-Tenant-Id: test-tenant" https://analytics.example.com/analytics/page-views

# Confirm budget headers are present
curl -si -H "X-Tenant-Id: test-tenant" https://analytics.example.com/analytics/page-views \
  | grep X-DP

# Exhaust the budget and confirm 429
for i in $(seq 1 15); do
  curl -s -H "X-Tenant-Id: test-tenant" https://analytics.example.com/analytics/page-views
done

# Statistical test: run the same query 1000 times and verify
# that the mean of returned values is close to the true count
# and the standard deviation is approximately sensitivity/epsilon = 1/1 = 1
```

## Related

- `multi-tenancy-isolation-workers-kv-d1.md` — isolating per-tenant event data
- `audit-log-security.md` — what to log (and not log) when collecting analytics events
- `sql-injection-prevention-d1-workers.md` — parameterised queries in D1
- `rate-limiting-per-user-d1-durable-objects.md` — rate-limiting analytics API calls
- `security-logging-what-to-log.md` — PII minimisation at collection time

## Sources

- Dwork, C. et al. — "Calibrating Noise to Sensitivity in Private Data Analysis" (TCC 2006)
- Apple — "Learning with Privacy at Scale" (2017) — local DP in practice
- NIST SP 800-188 — De-Identifying Government Data Sets
- GDPR Recital 26 and Article 89 — anonymisation and scientific research exemptions
- Cloudflare D1 Documentation — Batch and Transaction API
- The Algorithmic Foundations of Differential Privacy — Dwork & Roth (2014, freely available)
