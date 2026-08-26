# Stripe Issuing Virtual Card Lifecycle Management with Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You are building a spend-management or corporate card product on top of Stripe
Issuing. Your Workers API needs to:

- Create virtual cards on demand for employees or contractors.
- Activate, freeze (suspend), and cancel (terminate) cards programmatically.
- Surface card PAN + CVV for one-time display via a secure ephemeral endpoint.
- Log every lifecycle transition with an audit trail in D1.
- Enforce card creation limits per cardholder with KV rate limiting.

---

## Context

Stripe Issuing virtual cards follow this lifecycle:

```
created (inactive) ──► active ──► inactive (frozen) ──► active (unfrozen)
                                                         └──► canceled (terminal)
```

Key facts:
- A **Cardholder** must exist before any card can be issued.
- Cards start `inactive` by default; you activate them via `status: 'active'`.
- `canceled` is **permanent** — you cannot un-cancel a card.
- PAN and CVV are never returned in REST list/retrieve responses (they are empty
  strings). To display them, use a **Stripe Elements Ephemeral Key** flow.
- Real-time authorization decisions arrive via webhook
  `issuing_authorization.request` (see `stripe-issuing-real-time-authorization-webhooks.md`).

All Stripe Issuing API calls require the `stripe.issuing` beta header in older
SDK versions; in stripe-node v16+ it is included automatically.

---

## D1 Schema

```sql
-- migrations/0004_issuing_cards.sql
CREATE TABLE IF NOT EXISTS issuing_cardholders (
  id              TEXT PRIMARY KEY,    -- Stripe cardholder.id (ich_*)
  internal_ref    TEXT NOT NULL UNIQUE, -- your user/employee ID
  name            TEXT NOT NULL,
  email           TEXT NOT NULL,
  created_at      INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS issuing_cards (
  id              TEXT PRIMARY KEY,    -- Stripe card.id (ic_*)
  cardholder_id   TEXT NOT NULL REFERENCES issuing_cardholders(id),
  status          TEXT NOT NULL,       -- inactive | active | canceled
  currency        TEXT NOT NULL,
  spending_limit  INTEGER,             -- in minor units
  last4           TEXT NOT NULL,
  exp_month       INTEGER NOT NULL,
  exp_year        INTEGER NOT NULL,
  created_at      INTEGER NOT NULL,
  updated_at      INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS issuing_card_events (
  id              TEXT PRIMARY KEY,
  card_id         TEXT NOT NULL REFERENCES issuing_cards(id),
  event_type      TEXT NOT NULL,       -- created | activated | frozen | unfrozen | canceled
  actor           TEXT,                -- worker route or user_id that triggered it
  metadata        TEXT,                -- JSON blob of additional context
  occurred_at     INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cards_cardholder ON issuing_cards(cardholder_id);
CREATE INDEX IF NOT EXISTS idx_card_events_card ON issuing_card_events(card_id);
```

---

## Worker: Create Cardholder

```typescript
// src/issuing/create-cardholder.ts
import Stripe from 'stripe';
import { nanoid } from 'nanoid';

interface Env {
  STRIPE_SECRET_KEY: string;
  DB: D1Database;
}

interface CreateCardholderRequest {
  internalRef: string;
  name: string;
  email: string;
  phone?: string;
  billingAddress: {
    line1: string;
    city: string;
    state: string;
    postal_code: string;
    country: string;  // ISO 3166-1 alpha-2
  };
}

export async function createCardholder(
  data: CreateCardholderRequest,
  env: Env,
): Promise<Stripe.Issuing.Cardholder> {
  const stripe = new Stripe(env.STRIPE_SECRET_KEY);

  const cardholder = await stripe.issuing.cardholders.create({
    type: 'individual',
    name: data.name,
    email: data.email,
    phone_number: data.phone,
    billing: { address: data.billingAddress },
    metadata: { internal_ref: data.internalRef },
  });

  await env.DB.prepare(
    `INSERT INTO issuing_cardholders (id, internal_ref, name, email, created_at)
     VALUES (?, ?, ?, ?, ?)`,
  )
    .bind(cardholder.id, data.internalRef, data.name, data.email, Date.now())
    .run();

  return cardholder;
}
```

---

## Worker: Create Virtual Card

```typescript
// src/issuing/create-card.ts
import Stripe from 'stripe';
import { nanoid } from 'nanoid';

interface CreateCardRequest {
  cardholderId: string;     // ich_* Stripe ID
  currency?: string;        // default 'usd'
  spendingLimit?: {
    amount: number;         // minor units, e.g. 10000 = $100.00
    interval: 'daily' | 'weekly' | 'monthly' | 'per_authorization' | 'yearly' | 'all_time';
  };
  metadata?: Record<string, string>;
}

export async function createVirtualCard(
  data: CreateCardRequest,
  env: Env,
  actorId: string,
): Promise<Stripe.Issuing.Card> {
  // KV rate-limit: max 10 cards per cardholder
  const countKey = `card_count:${data.cardholderId}`;
  const CARD_LIMIT = 10;
  const KV_COUNTER_TTL = 60 * 60 * 24 * 365; // 1 year

  const currentStr = await env.ISSUING_KV.get(countKey);
  const current = parseInt(currentStr ?? '0', 10);
  if (current >= CARD_LIMIT) {
    throw new Error(`Card limit of ${CARD_LIMIT} reached for cardholder ${data.cardholderId}`);
  }

  const stripe = new Stripe(env.STRIPE_SECRET_KEY);

  const cardParams: Stripe.Issuing.CardCreateParams = {
    cardholder: data.cardholderId,
    currency: data.currency ?? 'usd',
    type: 'virtual',
    status: 'inactive',  // explicit; activate separately
    metadata: data.metadata,
  };

  if (data.spendingLimit) {
    cardParams.spending_controls = {
      spending_limits: [data.spendingLimit],
    };
  }

  const card = await stripe.issuing.cards.create(cardParams);
  const now = Date.now();

  await env.DB.batch([
    env.DB.prepare(
      `INSERT INTO issuing_cards
         (id, cardholder_id, status, currency, spending_limit, last4, exp_month, exp_year, created_at, updated_at)
       VALUES (?, ?, 'inactive', ?, ?, ?, ?, ?, ?, ?)`,
    ).bind(
      card.id,
      data.cardholderId,
      card.currency,
      data.spendingLimit?.amount ?? null,
      card.last4,
      card.exp_month,
      card.exp_year,
      now,
      now,
    ),
    env.DB.prepare(
      `INSERT INTO issuing_card_events (id, card_id, event_type, actor, occurred_at)
       VALUES (?, ?, 'created', ?, ?)`,
    ).bind(nanoid(), card.id, actorId, now),
  ]);

  // Increment KV counter
  await env.ISSUING_KV.put(countKey, String(current + 1), { expirationTtl: KV_COUNTER_TTL });

  return card;
}
```

---

## Worker: Activate, Freeze, Unfreeze, Cancel

```typescript
// src/issuing/card-status.ts
type CardAction = 'activate' | 'freeze' | 'unfreeze' | 'cancel';

const ACTION_TO_STATUS: Record<CardAction, Stripe.Issuing.CardUpdateParams['status']> = {
  activate:  'active',
  freeze:    'inactive',
  unfreeze:  'active',
  cancel:    'canceled',
};

const ACTION_TO_EVENT: Record<CardAction, string> = {
  activate:  'activated',
  freeze:    'frozen',
  unfreeze:  'unfrozen',
  cancel:    'canceled',
};

export async function updateCardStatus(
  cardId: string,
  action: CardAction,
  actorId: string,
  env: Env,
): Promise<Stripe.Issuing.Card> {
  // Validate transition
  const current = await env.DB.prepare(
    `SELECT status FROM issuing_cards WHERE id = ?`,
  ).bind(cardId).first<{ status: string }>();

  if (!current) throw new Error(`Card ${cardId} not found`);

  if (action === 'cancel' && current.status === 'canceled') {
    throw new Error('Card is already canceled');
  }
  if (action === 'activate' && current.status === 'canceled') {
    throw new Error('Cannot activate a canceled card');
  }

  const stripe = new Stripe(env.STRIPE_SECRET_KEY);
  const newStatus = ACTION_TO_STATUS[action];

  const card = await stripe.issuing.cards.update(cardId, { status: newStatus });
  const now = Date.now();

  await env.DB.batch([
    env.DB.prepare(
      `UPDATE issuing_cards SET status = ?, updated_at = ? WHERE id = ?`,
    ).bind(card.status, now, cardId),
    env.DB.prepare(
      `INSERT INTO issuing_card_events (id, card_id, event_type, actor, occurred_at)
       VALUES (?, ?, ?, ?, ?)`,
    ).bind(nanoid(), cardId, ACTION_TO_EVENT[action], actorId, now),
  ]);

  return card;
}
```

---

## Displaying PAN and CVV: Ephemeral Key Flow

The card number is never returned in the standard API. Use Stripe's Issuing
ephemeral key to let your frontend fetch the PAN directly from Stripe:

```typescript
// src/issuing/ephemeral-key.ts
export async function createEphemeralKey(
  cardId: string,
  stripeJsVersion: string,
  env: Env,
): Promise<{ ephemeralKeySecret: string; nonce: string }> {
  const stripe = new Stripe(env.STRIPE_SECRET_KEY);

  // Ephemeral key scoped to a single Issuing.Card
  const key = await stripe.ephemeralKeys.create(
    { issuing_card: cardId },
    { apiVersion: stripeJsVersion as any },  // must match client's Stripe.js version
  );

  const nonce = crypto.randomUUID();
  // Store nonce in KV for 30 s to prevent replay
  await env.ISSUING_KV.put(`ek_nonce:${nonce}`, cardId, { expirationTtl: 30 });

  return { ephemeralKeySecret: key.secret, nonce };
}
```

Frontend (Stripe.js):

```javascript
// client.js
const { ephemeralKeySecret, nonce } = await fetch('/issuing/ephemeral-key', {
  method: 'POST',
  body: JSON.stringify({ cardId: 'ic_xxx', stripeVersion: Stripe.version }),
}).then(r => r.json());

const cardElement = stripe.elements({ clientSecret: <redacted-secret> });
const issuingCard = cardElement.create('issuingCardNumberDisplay', { issuingCard: 'ic_xxx', nonce });
issuingCard.mount('#card-number');
```

---

## Anti-patterns

- **Storing or logging the full PAN** — Stripe never returns it in the API; do
  not attempt to proxy the ephemeral key endpoint through your backend storage.
  Display-only via Stripe Elements.
- **Using `status: 'canceled'` for temporary holds** — canceled is permanent.
  Use `status: 'inactive'` (freeze) for reversible blocks.
- **Creating cards without spending limits for untrusted users** — always set a
  `spending_limits` on cards issued to external parties.
- **Skipping audit log on status transitions** — regulators and compliance teams
  require a complete audit trail. The `issuing_card_events` table is mandatory,
  not optional.
- **Relying solely on D1 for card status** — Stripe is the source of truth. Your
  D1 status is a cache. On dispute or compliance queries, always re-fetch from
  Stripe.

---

## Gotchas

- **`inactive` means frozen, not pending activation** — Stripe uses `inactive`
  for both the initial pre-activation state and the frozen state. Use your D1
  `issuing_card_events` log to distinguish "never activated" from "temporarily
  frozen".
- **Ephemeral key `apiVersion` must exactly match the Stripe.js version** used
  on the client. A mismatch causes a 400 from Stripe.
- **Cards in `canceled` status are permanent** — Stripe's API returns 400 if you
  attempt to update a canceled card's status.
- **KV card count can drift** — if a card creation fails after KV increment, the
  counter is off by one. Cross-check with a D1 count query periodically.
- **Physical Issuing cards require a shipping address and have a longer lead time**
  — this article covers virtual cards only. Physical card activation uses a
  different endpoint (`stripe.issuing.cards.update` with `pin`).

---

## Verification

```bash
# 1. Create a test cardholder and card
curl -X POST https://your-worker.example.com/issuing/cardholders \
  -d '{"internalRef":"emp_001","name":"Jane Doe","email":"jane@example.com",...}'

curl -X POST https://your-worker.example.com/issuing/cards \
  -d '{"cardholderId":"ich_xxx","spendingLimit":{"amount":50000,"interval":"monthly"}}'

# 2. Activate the card
curl -X PATCH https://your-worker.example.com/issuing/cards/ic_xxx/status \
  -d '{"action":"activate"}'

# 3. Confirm in D1
wrangler d1 execute DB --command \
  "SELECT id, status, last4 FROM issuing_cards WHERE cardholder_id='ich_xxx';"

# 4. Audit trail
wrangler d1 execute DB --command \
  "SELECT event_type, actor, occurred_at FROM issuing_card_events WHERE card_id='ic_xxx' ORDER BY occurred_at;"

# 5. In Stripe test mode, simulate a purchase against the card
stripe issuing_authorizations create --amount=1000 --currency=usd --card=ic_xxx
```

---

## Related

- `stripe-issuing-card-spend-controls-workers.md`
- `stripe-issuing-real-time-authorization-webhooks.md`
- `marqeta-card-issuance-workers-d1.md`
- `stripe-connect-custom.md`
- `payment-audit-logging.md`

---

## Sources

- Stripe Issuing — Virtual Cards: https://docs.stripe.com/issuing/cards/virtual
- Stripe Issuing — Card Lifecycle: https://docs.stripe.com/issuing/cards
- Stripe Issuing — Display Card Numbers: https://docs.stripe.com/issuing/cards/digital-wallets#displaying-card-numbers
- Stripe Ephemeral Keys: https://docs.stripe.com/issuing/cards/digital-wallets
- Cloudflare D1 Batch: https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
