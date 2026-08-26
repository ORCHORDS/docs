# Payment Method Tokenisation Vault with Workers + KV

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

When customers save payment methods for future purchases you need a vault that stores Stripe PaymentMethod tokens (not raw card data), manages defaults per currency, enforces token expiry, and purges vault entries when a customer is deleted — all while staying within PCI DSS scope boundaries.

## Context

Stripe tokenises card data on the client (Stripe.js / Elements). Your server only ever sees a `pm_*` PaymentMethod ID. The vault layer maps customer IDs to lists of `pm_*` tokens stored in KV, with metadata like currency, last-four, card brand, expiry month/year, and whether the token is the default for a given currency. Raw PANs, CVVs, or full magnetic stripe data never touch Workers.

## Solution

### 1. KV data model

```
Key pattern:   vault:{customerId}:methods
Value:         JSON array of VaultEntry

Key pattern:   vault:{customerId}:default:{currency}
Value:         pm_* string (the default PaymentMethod ID for that currency)

Key pattern:   vault:{customerId}:meta
Value:         JSON object with customer-level metadata
```

```typescript
// src/vault/types.ts
export interface VaultEntry {
  pm_id: string;           // Stripe PaymentMethod ID
  brand: string;           // 'visa' | 'mastercard' | etc.
  last4: string;
  exp_month: number;
  exp_year: number;
  currency: string;        // ISO 4217 lowercase, e.g. 'usd'
  created_at: string;      // ISO-8601
  is_default: boolean;
}

export interface Env {
  PAYMENT_VAULT: KVNamespace;
  STRIPE_SECRET_KEY: string;
}
```

### 2. Store a PaymentMethod token

```typescript
// src/vault/store.ts
import Stripe from 'stripe';

const VAULT_TTL = 60 * 60 * 24 * 365 * 3; // 3 years — set to card expiry in production

export async function storePaymentMethod(
  customerId: string,
  pmId: string,
  currency: string,
  env: Env
): Promise<VaultEntry> {
  const stripe = new Stripe(env.STRIPE_SECRET_KEY, { apiVersion: '2024-06-20' });

  // Retrieve from Stripe to validate the pm belongs to this customer
  const pm = await stripe.paymentMethods.retrieve(pmId);

  if (pm.customer !== customerId) {
    throw new Error(`PaymentMethod ${pmId} does not belong to customer ${customerId}`);
  }

  if (!pm.card) {
    throw new Error(`PaymentMethod ${pmId} is not a card`);
  }

  const entry: VaultEntry = {
    pm_id: pmId,
    brand: pm.card.brand,
    last4: pm.card.last4,
    exp_month: pm.card.exp_month,
    exp_year: pm.card.exp_year,
    currency: currency.toLowerCase(),
    created_at: new Date().toISOString(),
    is_default: false,
  };

  const vaultKey = `vault:${customerId}:methods`;
  const existing = await getVaultEntries(customerId, env);

  // Prevent duplicates
  if (existing.some((e) => e.pm_id === pmId)) {
    return existing.find((e) => e.pm_id === pmId)!;
  }

  // Calculate TTL to card expiry (or 3 years, whichever is shorter)
  const expiryDate = new Date(pm.card.exp_year, pm.card.exp_month, 1);
  const ttl = Math.min(
    Math.floor((expiryDate.getTime() - Date.now()) / 1000),
    VAULT_TTL
  );

  const updated = [...existing, entry];
  await env.PAYMENT_VAULT.put(vaultKey, JSON.stringify(updated), {
    expirationTtl: ttl > 0 ? ttl : VAULT_TTL,
  });

  return entry;
}
```

### 3. Retrieve vault entries and handle expired tokens

```typescript
// src/vault/retrieve.ts
export async function getVaultEntries(
  customerId: string,
  env: Env
): Promise<VaultEntry[]> {
  const raw = await env.PAYMENT_VAULT.get(`vault:${customerId}:methods`);
  if (!raw) return [];

  const entries: VaultEntry[] = JSON.parse(raw);
  const now = new Date();

  // Filter out tokens whose card has physically expired
  const valid = entries.filter((e) => {
    const expiry = new Date(e.exp_year, e.exp_month, 1); // 1st of the month after expiry
    return expiry > now;
  });

  // Persist the pruned list if any were removed
  if (valid.length < entries.length) {
    await env.PAYMENT_VAULT.put(
      `vault:${customerId}:methods`,
      JSON.stringify(valid)
    );
  }

  return valid;
}
```

### 4. Default payment method management (multi-currency)

```typescript
// src/vault/defaults.ts
export async function setDefaultPaymentMethod(
  customerId: string,
  pmId: string,
  currency: string,
  env: Env
): Promise<void> {
  const entries = await getVaultEntries(customerId, env);
  const entry = entries.find((e) => e.pm_id === pmId);

  if (!entry) {
    throw new Error(`PaymentMethod ${pmId} not found in vault for ${customerId}`);
  }

  // Update is_default flag in the list
  const updated = entries.map((e) => ({
    ...e,
    is_default: e.pm_id === pmId && e.currency === currency ? true : e.currency === currency ? false : e.is_default,
  }));

  await env.PAYMENT_VAULT.put(`vault:${customerId}:methods`, JSON.stringify(updated));

  // Store the shortcut key for fast lookup
  await env.PAYMENT_VAULT.put(`vault:${customerId}:default:${currency}`, pmId);
}

export async function getDefaultPaymentMethod(
  customerId: string,
  currency: string,
  env: Env
): Promise<string | null> {
  return env.PAYMENT_VAULT.get(`vault:${customerId}:default:${currency}`);
}
```

### 5. Vault purge on customer deletion

```typescript
// src/vault/purge.ts

/**
 * Called from the Stripe customer.deleted webhook handler.
 * Deletes all KV keys for the customer including per-currency defaults.
 */
export async function purgeCustomerVault(
  customerId: string,
  env: Env
): Promise<void> {
  const currencies = ['usd', 'eur', 'gbp', 'jpy', 'cad', 'aud']; // enumerate known currencies

  const keysToDelete = [
    `vault:${customerId}:methods`,
    `vault:${customerId}:meta`,
    ...currencies.map((c) => `vault:${customerId}:default:${c}`),
  ];

  await Promise.all(keysToDelete.map((k) => env.PAYMENT_VAULT.delete(k)));

  console.log(`Vault purged for customer ${customerId}: ${keysToDelete.length} keys removed`);
}
```

### 6. API route wiring

```typescript
// src/index.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { pathname } = new URL(request.url);

    if (pathname === '/vault/store' && request.method === 'POST') {
      const { customer_id, pm_id, currency } = await request.json<any>();
      const entry = await storePaymentMethod(customer_id, pm_id, currency, env);
      return Response.json(entry);
    }

    if (pathname === '/vault/list' && request.method === 'GET') {
      const customer_id = new URL(request.url).searchParams.get('customer_id')!;
      const entries = await getVaultEntries(customer_id, env);
      return Response.json({ entries });
    }

    if (pathname === '/vault/default' && request.method === 'PUT') {
      const { customer_id, pm_id, currency } = await request.json<any>();
      await setDefaultPaymentMethod(customer_id, pm_id, currency, env);
      return Response.json({ ok: true });
    }

    return new Response('Not Found', { status: 404 });
  },
};
```

## Implementation Details

- Only `pm_*` IDs are stored — never PAN, CVV, or any raw card data. This keeps Workers entirely out of PCI DSS scope for cardholder data.
- TTL is set to card expiry so KV self-cleans without manual pruning.
- `is_default` is stored denormalised inside the methods array for O(1) reads while the shortcut key `default:{currency}` enables single-key lookup for checkout flows.
- `purgeCustomerVault` deletes GDPR-sensitive data on customer.deleted — always wire this webhook.
- Retrieving from Stripe before storing validates that the `pm_id` belongs to the stated customer, preventing token injection.

## Anti-patterns

- **Storing card numbers as the "token"** — Stripe gives you `pm_*`; that is the token. Never proxy raw card data through Workers.
- **One default across all currencies** — a customer's USD default card may not be enabled for EUR; always store defaults per currency.
- **Not pruning expired cards** — KV TTL handles vault-level expiry, but also filter by `exp_year`/`exp_month` on read to avoid charging declined cards.
- **Skipping the Stripe API ownership check** — without it, any caller can stuff arbitrary `pm_*` IDs into another customer's vault.

## Gotchas

- KV `delete` is strongly consistent for the Worker that calls it, but global consistency may lag ~60 seconds. Do not immediately re-read after delete in tests and expect `null`.
- Stripe `paymentMethods.retrieve` does not return the `customer` field unless the PM is attached. Attach before calling your vault store endpoint.
- The `exp_month` from Stripe is `1`–`12`; `new Date(year, month, 1)` is the 1st of the **next** month — which is correct, since cards are valid through the end of the stated month.
- KV has a 25 MiB value size limit; a vault with thousands of methods per customer will eventually hit this. Shard by `vault:{customerId}:methods:{page}` if needed.

## Verification

```bash
# Store a payment method
curl -X POST https://<worker>/vault/store \
  -H 'Content-Type: application/json' \
  -d '{"customer_id":"cus_test","pm_id":"pm_test","currency":"usd"}'

# List vault entries
curl "https://<worker>/vault/list?customer_id=cus_test"

# Inspect KV directly
wrangler kv:key get --binding=PAYMENT_VAULT "vault:cus_test:methods"

# Confirm purge removes all keys
wrangler kv:key get --binding=PAYMENT_VAULT "vault:cus_test:methods"
# Expected after purge: (empty / null)
```

## Related

- `documentation/docs/policies/payments/workers-stripe-webhook-idempotency.md`
- `documentation/docs/policies/payments/workers-pci-dss-scope-reduction.md`
- `documentation/docs/policies/payments/workers-stripe-connect-oauth-flow.md`

## Sources

- https://stripe.com/docs/payments/payment-methods
- https://stripe.com/docs/api/payment_methods/retrieve
- https://developers.cloudflare.com/kv/api/write-key-value-pairs/#expiring-keys
- https://www.pcisecuritystandards.org/document_library/
