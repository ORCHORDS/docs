# Braintree GraphQL API Workers Integration

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You need server-side Braintree operations (vault a payment method, create a transaction, search transactions) from a Cloudflare Worker without the official Node SDK (which relies on Node built-ins unavailable in Workers). Braintree's GraphQL API (`https://payments.braintree-gateway.com/graphql`) works over plain HTTPS with Basic auth, making it fully compatible with Workers fetch.

## Context

Braintree exposes a GraphQL endpoint in addition to its REST API. All mutations and queries follow the same schema regardless of sandbox vs. production — only the host changes. Authentication is HTTP Basic with `PUBLIC_KEY:PRIVATE_KEY` base64-encoded. The API version is passed via the `Braintree-Version` header (use the latest stable, e.g. `2023-05-01`). Workers can call this endpoint directly; no SDK required.

---

## Environment Setup (wrangler.toml)

```toml
[vars]
BRAINTREE_ENV = "sandbox"   # or "production"

[[secrets]]
# wrangler secret put BRAINTREE_PUBLIC_KEY
# wrangler secret put BRAINTREE_PRIVATE_KEY
# wrangler secret put BRAINTREE_MERCHANT_ID
```

## GraphQL Client Helper

```typescript
// src/lib/braintree.ts
const ENDPOINTS: Record<string, string> = {
  sandbox:    "https://payments.sandbox.braintree-gateway.com/graphql",
  production: "https://payments.braintree-gateway.com/graphql",
};

interface BraintreeEnv {
  BRAINTREE_ENV: string;
  BRAINTREE_PUBLIC_KEY: string;
  BRAINTREE_PRIVATE_KEY: string;
  BRAINTREE_MERCHANT_ID: string;
}

export async function btGql<T = unknown>(
  env: BraintreeEnv,
  query: string,
  variables: Record<string, unknown> = {}
): Promise<T> {
  const creds = btoa(`${env.BRAINTREE_PUBLIC_KEY}:${env.BRAINTREE_PRIVATE_KEY}`);
  const url = ENDPOINTS[env.BRAINTREE_ENV] ?? ENDPOINTS.sandbox;

  const res = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Basic ${creds}`,
      "Content-Type": "application/json",
      "Braintree-Version": "2023-05-01",
    },
    body: JSON.stringify({ query, variables }),
  });

  if (!res.ok) {
    throw new Error(`Braintree HTTP ${res.status}: ${await res.text()}`);
  }

  const json = (await res.json()) as { data?: T; errors?: unknown[] };
  if (json.errors?.length) {
    throw new Error(`Braintree GQL errors: ${JSON.stringify(json.errors)}`);
  }
  return json.data as T;
}
```

## Tokenize a Client Nonce into a Vault Payment Method

```typescript
// src/handlers/vault-payment-method.ts
import { btGql } from "../lib/braintree";

const VAULT_MUTATION = /* GraphQL */ `
  mutation VaultPaymentMethod($input: VaultPaymentMethodInput!) {
    vaultPaymentMethod(input: $input) {
      paymentMethod {
        id
        usage
        details {
          ... on CreditCardDetails {
            cardholderName
            last4
            expirationMonth
            expirationYear
            brandCode
          }
        }
      }
    }
  }
`;

export async function handleVaultPaymentMethod(
  req: Request,
  env: BraintreeEnv
): Promise<Response> {
  const { nonce, customerId } = await req.json<{
    nonce: string;
    customerId: string;
  }>();

  const data = await btGql<{
    vaultPaymentMethod: {
      paymentMethod: { id: string; details: unknown };
    };
  }>(env, VAULT_MUTATION, {
    input: { paymentMethodId: nonce, customerId },
  });

  return Response.json({ paymentMethodId: data.vaultPaymentMethod.paymentMethod.id });
}
```

## Create a Transaction

```typescript
const CHARGE_MUTATION = /* GraphQL */ `
  mutation ChargePaymentMethod($input: ChargePaymentMethodInput!) {
    chargePaymentMethod(input: $input) {
      transaction {
        id
        status
        amount { value currencyIsoCode }
      }
    }
  }
`;

export async function chargeVaultedMethod(
  env: BraintreeEnv,
  paymentMethodId: string,
  amountCents: number,
  orderId: string
): Promise<string> {
  const amount = (amountCents / 100).toFixed(2);
  const data = await btGql<{
    chargePaymentMethod: { transaction: { id: string; status: string } };
  }>(env, CHARGE_MUTATION, {
    input: {
      paymentMethodId,
      transaction: {
        amount,
        orderId,
        merchantAccountId: env.BRAINTREE_MERCHANT_ID,
      },
    },
  });

  const tx = data.chargePaymentMethod.transaction;
  if (!["SUBMITTED_FOR_SETTLEMENT", "SETTLING", "SETTLED"].includes(tx.status)) {
    throw new Error(`Unexpected Braintree status: ${tx.status}`);
  }
  return tx.id;
}
```

## Search Transactions by Order ID

```typescript
const SEARCH_QUERY = /* GraphQL */ `
  query SearchTransactions($input: TransactionSearchInput!) {
    search {
      transactions(input: $input) {
        edges {
          node { id status amount { value } createdAt }
        }
      }
    }
  }
`;

export async function findTransactionsByOrder(
  env: BraintreeEnv,
  orderId: string
) {
  return btGql(env, SEARCH_QUERY, {
    input: { orderId: { is: orderId } },
  });
}
```

## Generate a Client Token (for Braintree.js Drop-in)

```typescript
const CLIENT_TOKEN_MUTATION = /* GraphQL */ `
  mutation CreateClientToken($input: CreateClientTokenInput) {
    createClientToken(input: $input) { clientToken }
  }
`;

export async function generateClientToken(
  env: BraintreeEnv,
  customerId?: string
): Promise<string> {
  const input = customerId ? { clientToken: { customerId } } : {};
  const data = await btGql<{ createClientToken: { clientToken: string } }>(
    env,
    CLIENT_TOKEN_MUTATION,
    { input }
  );
  return data.createClientToken.clientToken;
}
```

---

## Anti-patterns

- Using `node-braintree` SDK in Workers — it imports `https`, `http`, `child_process`; all unavailable.
- Omitting `Braintree-Version` header — the API may silently use a deprecated schema version.
- Hardcoding `sandbox` in production deployments — always branch on `BRAINTREE_ENV`.
- Ignoring `errors[]` in GraphQL responses — a 200 HTTP status does NOT mean the operation succeeded.

## Gotchas

- Braintree's GraphQL schema uses `brandCode` (e.g. `"VISA"`) not `brand` — field names differ from the REST API.
- `VaultPaymentMethodInput.paymentMethodId` is the **client nonce**, not the vaulted token; the vaulted token is in the response `paymentMethod.id`.
- The `orderId` field on transactions must be unique per merchant account — reuse causes duplicate-detection rejection.
- Client token generation requires the `Braintree-Version` header even though it is listed as optional in some docs.
- Sandbox credentials reject production hostnames and vice versa silently (returns auth error, not a redirect).

## Verification

```bash
# Generate client token
curl https://payments.sandbox.braintree-gateway.com/graphql \
  -u "$PUBLIC_KEY:$PRIVATE_KEY" \
  -H "Braintree-Version: 2023-05-01" \
  -H "Content-Type: application/json" \
  -d '{"query":"mutation { createClientToken(input:{}) { clientToken } }"}'

# Check worker locally
wrangler dev --local
curl -X POST http://localhost:8787/client-token
```

## Related

- `braintree-dropin-ui-workers-tokenization.md`
- `braintree-paypal-workers-checkout-integration.md`
- `payment-method-vaulting-d1-workers.md`
- `idempotency-keys-payment-apis.md`

## Sources

- https://developer.paypal.com/braintree/docs/guides/graphql/overview
- https://graphql.braintreepayments.com/reference
- https://developer.paypal.com/braintree/docs/guides/client-sdk/setup/javascript/v3
