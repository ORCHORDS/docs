# Promotional Code Validation and Redemption with Workers + D1

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Marketing teams issue promotional codes for discounts, free trials, and partnership deals. Without a proper validation and redemption system you get codes used beyond their limits, the same user redeeming a "one-time" code multiple times, expired codes still applying, and no analytics on code performance.

## Context

Workers handles validation at checkout time with D1 storing the promo code catalogue and redemption ledger. The same Worker can expose a bulk code generation endpoint for marketing and a redemption analytics endpoint for the BI team. D1's SQLite dialect supports the transactions and constraints needed for safe concurrent redemption.

## Solution

### 1. D1 schema

```sql
-- migrations/002_promo_codes.sql

CREATE TABLE IF NOT EXISTS promo_codes (
  code              TEXT PRIMARY KEY,
  discount_type     TEXT NOT NULL CHECK(discount_type IN ('percent', 'fixed_amount', 'free_trial_days')),
  discount_value    REAL NOT NULL,          -- percent 0–100, cents for fixed, days for trial
  currency          TEXT,                   -- NULL means any currency (for percent / trial)
  max_redemptions   INTEGER,               -- NULL = unlimited
  redemption_count  INTEGER NOT NULL DEFAULT 0,
  per_user_limit    INTEGER NOT NULL DEFAULT 1, -- 0 = unlimited per user
  valid_from        TEXT NOT NULL,
  valid_until       TEXT,                   -- NULL = no expiry
  created_by        TEXT NOT NULL,
  created_at        TEXT NOT NULL,
  is_active         INTEGER NOT NULL DEFAULT 1  -- SQLite boolean
);

CREATE TABLE IF NOT EXISTS promo_redemptions (
  id          TEXT PRIMARY KEY,
  code        TEXT NOT NULL,
  user_id     TEXT NOT NULL,
  order_id    TEXT NOT NULL,
  discount_applied REAL NOT NULL,
  currency    TEXT NOT NULL,
  redeemed_at TEXT NOT NULL,
  FOREIGN KEY (code) REFERENCES promo_codes(code)
);

CREATE INDEX IF NOT EXISTS idx_redemptions_code ON promo_redemptions(code);
CREATE INDEX IF NOT EXISTS idx_redemptions_user ON promo_redemptions(user_id, code);
```

### 2. Validation endpoint

```typescript
// src/promo/validate.ts
export interface Env {
  DB: D1Database;
}

export interface ValidationRequest {
  code: string;
  user_id: string;
  currency: string;
  order_total_cents: number;
}

export interface ValidationResult {
  valid: boolean;
  discount_type?: string;
  discount_value?: number;
  discount_amount_cents?: number;
  error?: string;
}

export async function validatePromoCode(
  req: ValidationRequest,
  env: Env
): Promise<ValidationResult> {
  const now = new Date().toISOString();
  const code = req.code.trim().toUpperCase();

  const promo = await env.DB.prepare(
    `SELECT * FROM promo_codes
     WHERE code = ?
       AND is_active = 1
       AND valid_from <= ?
       AND (valid_until IS NULL OR valid_until >= ?)`
  )
    .bind(code, now, now)
    .first<any>();

  if (!promo) {
    return { valid: false, error: 'Code not found or expired' };
  }

  // Check global redemption cap
  if (promo.max_redemptions !== null && promo.redemption_count >= promo.max_redemptions) {
    return { valid: false, error: 'Code has reached its redemption limit' };
  }

  // Check per-user limit
  if (promo.per_user_limit > 0) {
    const userCount = await env.DB.prepare(
      'SELECT COUNT(*) AS cnt FROM promo_redemptions WHERE code = ? AND user_id = ?'
    )
      .bind(code, req.user_id)
      .first<{ cnt: number }>();

    if ((userCount?.cnt ?? 0) >= promo.per_user_limit) {
      return { valid: false, error: 'Code already used by this account' };
    }
  }

  // Currency check for fixed_amount discounts
  if (promo.discount_type === 'fixed_amount' && promo.currency !== req.currency.toLowerCase()) {
    return { valid: false, error: `Code only valid for ${promo.currency.toUpperCase()}` };
  }

  // Calculate discount amount in cents
  let discountAmountCents = 0;
  if (promo.discount_type === 'percent') {
    discountAmountCents = Math.round(req.order_total_cents * (promo.discount_value / 100));
  } else if (promo.discount_type === 'fixed_amount') {
    discountAmountCents = Math.min(promo.discount_value, req.order_total_cents);
  }

  return {
    valid: true,
    discount_type: promo.discount_type,
    discount_value: promo.discount_value,
    discount_amount_cents: discountAmountCents,
  };
}
```

### 3. Redemption recording (atomic with counter update)

```typescript
// src/promo/redeem.ts
import { nanoid } from 'nanoid';

export interface RedemptionRequest {
  code: string;
  user_id: string;
  order_id: string;
  discount_applied: number;  // cents
  currency: string;
}

export async function redeemPromoCode(
  req: RedemptionRequest,
  env: Env
): Promise<{ redemption_id: string }> {
  const code = req.code.trim().toUpperCase();
  const redemptionId = nanoid();
  const now = new Date().toISOString();

  // D1 batch executes both statements atomically
  const [insertResult, updateResult] = await env.DB.batch([
    env.DB.prepare(
      `INSERT INTO promo_redemptions (id, code, user_id, order_id, discount_applied, currency, redeemed_at)
       VALUES (?, ?, ?, ?, ?, ?, ?)`
    ).bind(redemptionId, code, req.user_id, req.order_id, req.discount_applied, req.currency, now),

    env.DB.prepare(
      `UPDATE promo_codes SET redemption_count = redemption_count + 1 WHERE code = ?`
    ).bind(code),
  ]);

  if (!insertResult.success || !updateResult.success) {
    throw new Error('Failed to record redemption');
  }

  return { redemption_id: redemptionId };
}
```

### 4. Bulk code generation

```typescript
// src/promo/generate.ts
import { nanoid } from 'nanoid';

export interface BulkGenerateRequest {
  prefix: string;            // e.g. 'SUMMER'
  count: number;             // max 1000
  discount_type: 'percent' | 'fixed_amount' | 'free_trial_days';
  discount_value: number;
  currency?: string;
  max_redemptions?: number;
  per_user_limit?: number;
  valid_from: string;
  valid_until?: string;
  created_by: string;
}

export async function bulkGenerateCodes(
  req: BulkGenerateRequest,
  env: Env
): Promise<string[]> {
  if (req.count > 1000) throw new Error('Maximum batch size is 1 000 codes');

  const now = new Date().toISOString();
  const codes = Array.from({ length: req.count }, () =>
    `${req.prefix}-${nanoid(8).toUpperCase()}`
  );

  const stmts = codes.map((code) =>
    env.DB.prepare(
      `INSERT INTO promo_codes
         (code, discount_type, discount_value, currency, max_redemptions, per_user_limit,
          valid_from, valid_until, created_by, created_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
    ).bind(
      code,
      req.discount_type,
      req.discount_value,
      req.currency ?? null,
      req.max_redemptions ?? null,
      req.per_user_limit ?? 1,
      req.valid_from,
      req.valid_until ?? null,
      req.created_by,
      now
    )
  );

  // D1 batch limit is 1 000 — matches our count cap
  await env.DB.batch(stmts);
  return codes;
}
```

### 5. Redemption analytics endpoint

```typescript
// src/promo/analytics.ts
export async function getRedemptionAnalytics(code: string, env: Env) {
  const summary = await env.DB.prepare(
    `SELECT
       p.code,
       p.discount_type,
       p.discount_value,
       p.max_redemptions,
       p.redemption_count,
       COALESCE(SUM(r.discount_applied), 0) AS total_discount_cents,
       COUNT(DISTINCT r.user_id)            AS unique_users,
       MIN(r.redeemed_at)                   AS first_used,
       MAX(r.redeemed_at)                   AS last_used
     FROM promo_codes p
     LEFT JOIN promo_redemptions r ON r.code = p.code
     WHERE p.code = ?
     GROUP BY p.code`
  )
    .bind(code.toUpperCase())
    .first();

  return summary;
}
```

## Implementation Details

- `redemption_count` is incremented atomically inside the same D1 `batch()` as the insert, preventing race conditions under concurrent checkouts.
- Validation is a read-only check; redemption is a write. Keep them as two separate calls so clients can validate before payment capture and redeem after.
- `nanoid(8)` generates 8-character alphanumeric codes; combined with a prefix, collision probability is negligible for batches under 10 000.
- `per_user_limit = 0` is treated as unlimited per user; `1` enforces one-time-per-user semantics.
- Codes are stored uppercased; always `trim().toUpperCase()` on input to handle copy-paste whitespace.

## Anti-patterns

- **Validating and redeeming in a single endpoint without idempotency** — if the payment fails after redemption is recorded, the user loses their code. Validate first, redeem only after payment succeeds.
- **No per-user limit check** — a user in two browser tabs can redeem the same "one-time" code twice within the same second without a per-user guard.
- **Storing discount amounts in the code itself and nowhere else** — always record `discount_applied` at redemption time for audits, even if the code value later changes.
- **Soft-deleting codes by checking redemption_count >= max in application code** — the `is_active` flag provides a hard on/off for marketing pulls.

## Gotchas

- D1 `batch()` is not a true SQL transaction on the current implementation; it executes statements serially on the same connection. Under very high concurrency, two simultaneous redemptions could both pass the `max_redemptions` check. Add a `CHECK(redemption_count <= max_redemptions)` constraint or use `WHERE redemption_count < max_redemptions` in the UPDATE for optimistic concurrency.
- `nanoid` must be bundled; it is an ESM-only package. Use `import { nanoid } from 'nanoid'` with `node_compat = true` in wrangler.toml, or substitute `crypto.randomUUID().slice(0,8)`.
- D1 `first()` returns `null` for no rows, not an empty object; always null-check.

## Verification

```bash
# Generate codes
curl -X POST https://<worker>/promo/generate \
  -H 'Content-Type: application/json' \
  -d '{"prefix":"TEST","count":3,"discount_type":"percent","discount_value":20,"valid_from":"2026-01-01","created_by":"ci"}'

# Validate
curl -X POST https://<worker>/promo/validate \
  -d '{"code":"TEST-ABCD1234","user_id":"usr_1","currency":"usd","order_total_cents":5000}'

# Verify analytics
curl "https://<worker>/promo/analytics?code=TEST-ABCD1234"
```

## Related

- `documentation/docs/policies/payments/workers-billing-usage-metering-d1.md`
- `documentation/docs/policies/payments/workers-revenue-recognition-d1.md`
- `documentation/docs/policies/payments/workers-subscription-dunning-workflow.md`

## Sources

- https://developers.cloudflare.com/d1/
- https://stripe.com/docs/billing/subscriptions/coupons
- https://www.npmjs.com/package/nanoid
