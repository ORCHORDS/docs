# Stripe Issuing Card Spend Controls Workers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

You issue virtual or physical cards through Stripe Issuing and need to enforce
business-logic spend controls beyond what the Stripe Dashboard offers out of the
box: per-card monthly budgets, merchant category code (MCC) allowlists/blocklists,
time-of-day restrictions, geographic limits, and per-transaction approval logic
that consults your own data before authorizing.

Cloudflare Workers handles real-time authorization webhooks (Stripe's
`issuing_authorization.request` event) with sub-200ms response times required by
the network, while card-level spending rules are stored in Workers KV and D1.

## Context

Stripe Issuing's built-in spend controls support basic MCC category restrictions
and velocity limits configured at card or cardholder level via the API. For
richer logic — dynamic budget checks, merchant blocklists from your fraud DB,
employee role-based limits — you implement a real-time authorization endpoint.

Flow:
1. Cardholder swipes / taps card at merchant
2. Network → Stripe → your Workers endpoint within ~2 seconds
3. Worker reads rules from KV, checks D1 spend history, decides approve/decline
4. Returns `{"approved": true}` or `{"approved": false}` with an optional reason
5. Stripe approves or declines the transaction, fires `issuing_authorization.updated`

## Spend Rule Schema in KV and D1

```typescript
// Stored in KV as: `card-rules:{cardId}` → JSON
interface CardSpendRules {
  cardId: string;
  holderId: string;
  monthlyBudgetCents: number;
  dailyBudgetCents: number;
  allowedMccs: string[];           // empty = allow all
  blockedMccs: string[];
  blockedMerchantIds: string[];    // Stripe merchant_data.network_id
  allowedCountries: string[];      // ISO-3166-1 alpha-2, empty = allow all
  activeHours: { start: number; end: number } | null; // UTC hours 0-23
  maxTransactionCents: number;
  requireApprovalAboveCents: number; // require secondary approval if exceeded
}

// D1 table for spend history
// CREATE TABLE issuing_authorizations (
//   id              TEXT PRIMARY KEY,   -- Stripe authorization id
//   card_id         TEXT NOT NULL,
//   holder_id       TEXT NOT NULL,
//   amount_cents    INTEGER NOT NULL,
//   currency        TEXT NOT NULL,
//   merchant_name   TEXT,
//   mcc             TEXT,
//   country         TEXT,
//   approved        INTEGER NOT NULL,   -- 0 | 1
//   decline_reason  TEXT,
//   authorized_at   TEXT NOT NULL DEFAULT (datetime('now'))
// );
// CREATE INDEX idx_iss_auth_card ON issuing_authorizations(card_id, authorized_at);
```

## Real-time Authorization Worker

```typescript
// authorization-worker.ts
import { D1Database } from '@cloudflare/workers-types';

interface Env {
  DB: D1Database;
  CARD_RULES: KVNamespace;
  STRIPE_ISSUING_SIGNING_SECRET: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('Method not allowed', { status: 405 });

    // Stripe Issuing authorization webhooks have a 2-second total response window
    const body = await request.text();
    const sig = request.headers.get('stripe-signature') ?? '';

    const isValid = await verifyStripeWebhookSignature(
      body, sig, env.STRIPE_ISSUING_SIGNING_SECRET
    );
    if (!isValid) return new Response('Invalid signature', { status: 400 });

    const event = JSON.parse(body) as {
      type: string;
      data: { object: StripeIssuingAuthorization };
    };

    if (event.type !== 'issuing_authorization.request') {
      return Response.json({ approved: true }); // non-request events: ack only
    }

    const auth = event.data.object;
    const { approved, reason } = await evaluateAuthorization(env, auth);

    // Persist authorization attempt
    await env.DB.prepare(
      `INSERT OR IGNORE INTO issuing_authorizations
         (id, card_id, holder_id, amount_cents, currency,
          merchant_name, mcc, country, approved, decline_reason, authorized_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))`
    ).bind(
      auth.id,
      auth.card,
      auth.cardholder,
      auth.amount,
      auth.currency,
      auth.merchant_data?.name ?? null,
      auth.merchant_data?.category_code ?? null,
      auth.merchant_data?.country ?? null,
      approved ? 1 : 0,
      reason ?? null,
    ).run();

    return Response.json({ approved, ...(reason ? { reason } : {}) });
  },
};

interface StripeIssuingAuthorization {
  id: string;
  card: string;
  cardholder: string;
  amount: number;
  currency: string;
  merchant_data: {
    name: string;
    category_code: string;
    country: string;
    network_id: string;
  } | null;
}

async function evaluateAuthorization(
  env: Env,
  auth: StripeIssuingAuthorization
): Promise<{ approved: boolean; reason?: string }> {
  // Load card rules from KV (fast, cached at edge)
  const rulesJson = await env.CARD_RULES.get(`card-rules:${auth.card}`);
  if (!rulesJson) {
    // No rules configured → default allow
    return { approved: true };
  }

  const rules: CardSpendRules = JSON.parse(rulesJson);

  // 1. Per-transaction max
  if (auth.amount > rules.maxTransactionCents) {
    return { approved: false, reason: 'exceeds_max_transaction_amount' };
  }

  // 2. MCC blocklist
  const mcc = auth.merchant_data?.category_code ?? '';
  if (mcc && rules.blockedMccs.includes(mcc)) {
    return { approved: false, reason: 'blocked_merchant_category' };
  }

  // 3. MCC allowlist (if set, deny everything not on it)
  if (rules.allowedMccs.length > 0 && mcc && !rules.allowedMccs.includes(mcc)) {
    return { approved: false, reason: 'merchant_category_not_allowed' };
  }

  // 4. Blocked merchant network ID
  const networkId = auth.merchant_data?.network_id ?? '';
  if (networkId && rules.blockedMerchantIds.includes(networkId)) {
    return { approved: false, reason: 'blocked_merchant' };
  }

  // 5. Country restriction
  const country = auth.merchant_data?.country ?? '';
  if (rules.allowedCountries.length > 0 && country && !rules.allowedCountries.includes(country)) {
    return { approved: false, reason: 'country_not_allowed' };
  }

  // 6. Time-of-day restriction (UTC)
  if (rules.activeHours) {
    const hour = new Date().getUTCHours();
    if (hour < rules.activeHours.start || hour >= rules.activeHours.end) {
      return { approved: false, reason: 'outside_active_hours' };
    }
  }

  // 7. Daily spend budget (from D1)
  const { dailySpent } = await env.DB.prepare(
    `SELECT COALESCE(SUM(amount_cents), 0) AS dailySpent
     FROM issuing_authorizations
     WHERE card_id = ? AND approved = 1
       AND date(authorized_at) = date('now')`
  ).bind(auth.card).first() as { dailySpent: number };

  if (dailySpent + auth.amount > rules.dailyBudgetCents) {
    return { approved: false, reason: 'daily_budget_exceeded' };
  }

  // 8. Monthly spend budget (from D1)
  const { monthlySpent } = await env.DB.prepare(
    `SELECT COALESCE(SUM(amount_cents), 0) AS monthlySpent
     FROM issuing_authorizations
     WHERE card_id = ? AND approved = 1
       AND strftime('%Y-%m', authorized_at) = strftime('%Y-%m', 'now')`
  ).bind(auth.card).first() as { monthlySpent: number };

  if (monthlySpent + auth.amount > rules.monthlyBudgetCents) {
    return { approved: false, reason: 'monthly_budget_exceeded' };
  }

  return { approved: true };
}
```

## Rule Management API

```typescript
// rules-api.ts — separate Worker or route on the same Worker

export async function handleRuleUpsert(request: Request, env: Env): Promise<Response> {
  const cardId = new URL(request.url).pathname.split('/').pop()!;
  const rules: CardSpendRules = await request.json();

  // Validate MCC codes are 4 digits
  const mccRegex = /^\d{4}$/;
  const invalidMccs = [...rules.allowedMccs, ...rules.blockedMccs].filter(m => !mccRegex.test(m));
  if (invalidMccs.length > 0) {
    return Response.json({ error: `Invalid MCCs: ${invalidMccs.join(', ')}` }, { status: 422 });
  }

  await env.CARD_RULES.put(`card-rules:${cardId}`, JSON.stringify(rules), {
    metadata: { updatedAt: new Date().toISOString() },
  });

  // Also update Stripe's native controls for the card (as a fallback layer)
  await updateStripeCardControls(cardId, rules, env);

  return Response.json({ ok: true });
}

async function updateStripeCardControls(
  cardId: string,
  rules: CardSpendRules,
  env: Env
): Promise<void> {
  // Build Stripe spending_controls from our rules
  const params = new URLSearchParams();

  // Map our blockedMccs to Stripe's blocked_categories (best-effort)
  rules.blockedMccs.forEach(mcc => {
    params.append('spending_controls[blocked_categories][]', mccToStripeCategory(mcc));
  });

  // Set a monthly limit as a backstop
  params.append('spending_controls[spending_limits][0][amount]', String(rules.monthlyBudgetCents));
  params.append('spending_controls[spending_limits][0][interval]', 'monthly');

  await fetch(`https://api.stripe.com/v1/issuing/cards/${cardId}`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.STRIPE_SECRET_KEY}`,
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: params,
  });
}

function mccToStripeCategory(mcc: string): string {
  // Stripe uses named category strings; map known MCCs
  const map: Record<string, string> = {
    '5812': 'eating_places_restaurants',
    '5411': 'grocery_stores_supermarkets',
    '7011': 'hotels_motels_inns_resorts',
    '4111': 'transportation',
    '5541': 'service_stations',
  };
  return map[mcc] ?? mcc;
}
```

## Spend Reporting Query

```typescript
// Spending summary per cardholder for the current month
async function getCardholderMonthlySummary(
  env: Env,
  holderId: string
): Promise<{ cardId: string; approved: number; declined: number; totalCents: number }[]> {
  const rows = await env.DB.prepare(
    `SELECT card_id,
            SUM(CASE WHEN approved=1 THEN 1 ELSE 0 END) AS approved,
            SUM(CASE WHEN approved=0 THEN 1 ELSE 0 END) AS declined,
            COALESCE(SUM(CASE WHEN approved=1 THEN amount_cents ELSE 0 END), 0) AS totalCents
     FROM issuing_authorizations
     WHERE holder_id = ?
       AND strftime('%Y-%m', authorized_at) = strftime('%Y-%m', 'now')
     GROUP BY card_id`
  ).bind(holderId).all();

  return rows.results as { cardId: string; approved: number; declined: number; totalCents: number }[];
}
```

## Anti-patterns

- **Relying solely on Stripe's built-in controls**: Stripe's native spend controls
  cannot consult your business DB. For dynamic limits (e.g., per-user tier), you
  need the real-time authorization webhook.
- **Slow D1 queries in the hot path**: The authorization window is ~2 seconds
  end-to-end. Keep D1 queries to a maximum of 2-3 simple indexed lookups. Pre-aggregate
  daily/monthly totals with a cron rather than summing on every authorization.
- **Missing fallback approval**: If your Worker throws an unhandled exception,
  Stripe defaults to declining. Wrap the entire handler in try/catch and return
  `{ approved: true }` (or false per your policy) on error.
- **Storing full authorization history forever**: Issuing can generate thousands of
  micro-transactions. Implement a D1 cleanup job or use Cloudflare Analytics Engine
  for high-cardinality spend data.

## Gotchas

- `issuing_authorization.request` must be responded to within 2 seconds total
  (including Stripe's round-trip). Your Worker logic must complete in under 800ms
  to leave margin. Use KV for rules (fast) and limit D1 calls to 1-2 indexed reads.
- Stripe sends authorization events to the webhook endpoint configured under
  Issuing settings, not the standard webhook endpoint. Configure it separately
  in the Stripe Dashboard under Issuing → Authorization.
- Authorization amounts are in the card's billing currency (not necessarily USD).
  Convert amounts before comparing against budgets if you support multi-currency
  cardholders.
- When a card is frozen via the Stripe Dashboard or API, `issuing_authorization.request`
  is not called — Stripe declines before reaching your endpoint. Don't rely on
  your Worker as the only freeze mechanism.

## Verification

```bash
# Trigger a test authorization via Stripe CLI
stripe trigger issuing_authorization.request

# Check authorization history for a card
wrangler d1 execute <DB> --command \
  "SELECT date(authorized_at) AS day,
          COUNT(*) AS n,
          SUM(CASE WHEN approved=1 THEN amount_cents ELSE 0 END)/100.0 AS approved_usd,
          SUM(CASE WHEN approved=0 THEN 1 ELSE 0 END) AS declined
   FROM issuing_authorizations
   WHERE card_id='ic_xxx'
   GROUP BY day ORDER BY day DESC LIMIT 30;"

# Inspect a card's KV rules
wrangler kv:key get --binding=CARD_RULES "card-rules:ic_xxx"
```

## Related

- `stripe-issuing-real-time-authorization-webhooks.md` — Webhook delivery mechanics
- `velocity-fraud-checks.md` — General velocity rate limiting patterns
- `stripe-radar-fraud-rules.md` — Radar rules for card-present fraud
- `payment-fraud-detection-velocity-checks.md` — Velocity check implementation

## Sources

- Stripe Issuing spend controls: https://stripe.com/docs/issuing/controls/spending-controls
- Stripe real-time authorization: https://stripe.com/docs/issuing/controls/real-time-authorizations
- Cloudflare Workers KV: https://developers.cloudflare.com/kv/
- Stripe Issuing MCC categories: https://stripe.com/docs/issuing/categories
