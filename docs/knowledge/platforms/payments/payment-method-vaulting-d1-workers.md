# Payment Method Vaulting in D1 via Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
You need to store tokenized payment methods (Stripe `pm_*`, Braintree nonces, Adyen tokens)
linked to your internal user records so returning customers can checkout without re-entering
card details — without any raw card data ever touching your server.

## Context
Vaulting in this pattern means persisting the processor's opaque token (which carries zero PCI
scope) in D1 alongside customer metadata. Workers handle the vault CRUD layer: create a vault
entry after successful `PaymentMethod.attach`, retrieve it at checkout time, soft-delete on
expiry or customer request, and enforce one-active-per-type constraints. All sensitive lookups
are scoped to the authenticated user's internal ID — the vault never exposes tokens in API
responses, only resolves them for server-side charge calls.

---

## D1 Schema and Vault Entry Creation

```sql
-- migrations/0001_payment_vault.sql
CREATE TABLE IF NOT EXISTS payment_vault (
  id            TEXT PRIMARY KEY,          -- internal UUID
  user_id       TEXT NOT NULL,
  processor     TEXT NOT NULL,             -- 'stripe' | 'braintree' | 'adyen'
  processor_id  TEXT NOT NULL,             -- pm_xxx / token / shopper reference
  type          TEXT NOT NULL,             -- 'card' | 'bank_account' | 'wallet'
  brand         TEXT,                      -- 'visa' | 'mastercard' etc
  last4         TEXT,
  exp_month     INTEGER,
  exp_year      INTEGER,
  is_default    INTEGER NOT NULL DEFAULT 0,
  created_at    INTEGER NOT NULL,
  deleted_at    INTEGER
);

CREATE INDEX IF NOT EXISTS idx_vault_user ON payment_vault(user_id, deleted_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_vault_processor ON payment_vault(processor, processor_id);
```

```typescript
// src/vault.ts
import { nanoid } from 'nanoid'; // bundled via npm

export interface Env {
  DB: D1Database;
  STRIPE_SECRET_KEY: string;
}

export interface VaultEntry {
  id: string;
  userId: string;
  processor: string;
  processorId: string;
  type: string;
  brand: string | null;
  last4: string | null;
  expMonth: number | null;
  expYear: number | null;
  isDefault: boolean;
}

export async function vaultPaymentMethod(
  userId: string,
  paymentMethodId: string, // e.g. pm_xxx from Stripe Elements
  makeDefault: boolean,
  env: Env
): Promise<VaultEntry> {
  // 1. Attach pm to Stripe customer (idempotent)
  const customerRes = await fetch(
    `https://api.stripe.com/v1/payment_methods/${paymentMethodId}/attach`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${env.STRIPE_SECRET_KEY}`,
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: new URLSearchParams({ customer: await getStripeCustomerId(userId, env) }),
    }
  );
  if (!customerRes.ok) {
    const err = await customerRes.json<{ error: { message: string } }>();
    throw new Error(`Attach failed: ${err.error.message}`);
  }
  const pm = await customerRes.json<{
    id: string;
    type: string;
    card?: { brand: string; last4: string; exp_month: number; exp_year: number };
  }>();

  const id = nanoid();
  const now = Math.floor(Date.now() / 1000);

  // 2. If making default, clear existing defaults
  if (makeDefault) {
    await env.DB.prepare(
      `UPDATE payment_vault SET is_default = 0
       WHERE user_id = ? AND processor = 'stripe' AND deleted_at IS NULL`
    )
      .bind(userId)
      .run();
  }

  // 3. Insert vault entry
  await env.DB.prepare(
    `INSERT OR IGNORE INTO payment_vault
       (id, user_id, processor, processor_id, type, brand, last4, exp_month, exp_year, is_default, created_at)
     VALUES (?, ?, 'stripe', ?, ?, ?, ?, ?, ?, ?, ?)`
  )
    .bind(
      id,
      userId,
      pm.id,
      pm.type,
      pm.card?.brand ?? null,
      pm.card?.last4 ?? null,
      pm.card?.exp_month ?? null,
      pm.card?.exp_year ?? null,
      makeDefault ? 1 : 0,
      now
    )
    .run();

  return {
    id,
    userId,
    processor: 'stripe',
    processorId: pm.id,
    type: pm.type,
    brand: pm.card?.brand ?? null,
    last4: pm.card?.last4 ?? null,
    expMonth: pm.card?.exp_month ?? null,
    expYear: pm.card?.exp_year ?? null,
    isDefault: makeDefault,
  };
}

async function getStripeCustomerId(userId: string, env: Env): Promise<string> {
  const row = await env.DB.prepare(
    `SELECT stripe_customer_id FROM users WHERE id = ?`
  )
    .bind(userId)
    .first<{ stripe_customer_id: string }>();
  if (!row?.stripe_customer_id) throw new Error(`No Stripe customer for user ${userId}`);
  return row.stripe_customer_id;
}
```

## Listing and Resolving Vault Entries at Checkout

The vault API returns safe display metadata only — never the raw `processor_id` to the
client. The server resolves the vault ID to a `processor_id` internally when creating a
PaymentIntent.

```typescript
// src/vault-read.ts
export async function listVaultEntries(
  userId: string,
  env: Env
): Promise<Omit<VaultEntry, 'processorId'>[]> {
  const { results } = await env.DB.prepare(
    `SELECT id, user_id AS userId, processor, type, brand, last4,
            exp_month AS expMonth, exp_year AS expYear, is_default AS isDefault
     FROM payment_vault
     WHERE user_id = ? AND deleted_at IS NULL
     ORDER BY is_default DESC, created_at DESC`
  )
    .bind(userId)
    .all<Omit<VaultEntry, 'processorId'>>();
  return results;
}

export async function resolveVaultEntry(
  userId: string,
  vaultId: string,
  env: Env
): Promise<string> {
  // Returns processor_id only for server-side use
  const row = await env.DB.prepare(
    `SELECT processor_id FROM payment_vault
     WHERE id = ? AND user_id = ? AND deleted_at IS NULL`
  )
    .bind(vaultId, userId)
    .first<{ processor_id: string }>();
  if (!row) throw new Error('Vault entry not found or not owned by user');
  return row.processor_id;
}

export async function softDeleteVaultEntry(
  userId: string,
  vaultId: string,
  env: Env
): Promise<void> {
  const processorId = await resolveVaultEntry(userId, vaultId, env);

  // Detach from Stripe so it can't be charged
  await fetch(
    `https://api.stripe.com/v1/payment_methods/${processorId}/detach`,
    {
      method: 'POST',
      headers: { Authorization: `Bearer ${env.STRIPE_SECRET_KEY}` },
    }
  );

  await env.DB.prepare(
    `UPDATE payment_vault SET deleted_at = unixepoch(), is_default = 0
     WHERE id = ? AND user_id = ?`
  )
    .bind(vaultId, userId)
    .run();
}
```

## Anti-patterns
- Returning `processor_id` in list API responses — a leaked `pm_xxx` can be reused in a
  server-side charge by anyone who can impersonate the customer ID.
- Hard-deleting vault rows — losing the row means you cannot reconcile historical charges
  against the token; use `deleted_at` soft deletes.
- Storing last4 and brand from the client — always fetch card metadata from Stripe's
  PaymentMethod object after attach, never trust client-supplied display data.
- Skipping the `UNIQUE INDEX` on `(processor, processor_id)` — concurrent vault calls can
  produce duplicate rows and double-bill.

## Gotchas
- Stripe `pm_*` IDs are customer-scoped after attach; detaching removes them from the
  customer but does not delete the PaymentMethod object — a second attach is valid.
- D1's `OR IGNORE` on the processor unique index silently swallows duplicate inserts; check
  `meta.changes` to detect whether the row was actually written.
- An expired card still has a valid vault entry and `processor_id`; Stripe will decline the
  charge. Run a nightly job to flag entries where `exp_year * 100 + exp_month < current_ym`.
- `is_default` is per-processor; a user can have one default Stripe card and one default
  Braintree PayPal account simultaneously — the checkout layer must specify processor.

## Verification
```sql
-- Check vault for a user
SELECT id, processor, brand, last4, exp_month, exp_year, is_default, deleted_at
FROM payment_vault
WHERE user_id = 'usr_xxx'
ORDER BY created_at DESC;

-- Find expired vaulted cards
SELECT id, user_id, last4, exp_year * 100 + exp_month AS expiry_ym
FROM payment_vault
WHERE deleted_at IS NULL
  AND exp_year * 100 + exp_month < strftime('%Y%m', 'now')
ORDER BY expiry_ym;
```

```bash
# Apply schema migration
wrangler d1 execute DB --file=migrations/0001_payment_vault.sql
```

## Related
- `tokenization-vault-patterns.md`
- `network-tokenization-vs-vault-tokens.md`
- `pci-dss-scope-reduction-tokenization.md`
- `stripe-account-updater-card-refresh-workers.md`
- `payment-method-fingerprinting-fraud-workers-d1.md`

## Sources
- https://stripe.com/docs/api/payment_methods/attach
- https://stripe.com/docs/payments/save-and-reuse
- https://developers.cloudflare.com/d1/
- https://stripe.com/docs/security/guide#validating-pci-compliance
- https://stripe.com/docs/api/payment_methods/detach
