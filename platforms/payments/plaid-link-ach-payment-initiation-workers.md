# Plaid Link Bank Account Verification and ACH Payment Initiation via Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-Case

You want to let users pay via ACH bank transfer by securely linking their bank account through Plaid Link — the OAuth-like browser flow that lets users select their bank, authenticate, and grant a scoped access token without exposing credentials to your platform. The Cloudflare Worker then exchanges the Link public token for a Stripe or Dwolla bank funding source and initiates an ACH pull. The challenge is coordinating the stateful Plaid OAuth redirect flow across Workers (which are stateless) while storing account metadata in D1 and protecting the access token.

---

## Context

Plaid Link generates a short-lived `public_token` in the browser after the user authenticates. Your server must exchange it for a long-lived `access_token` and an `item_id` within 30 minutes. From there, two paths exist:

1. **Stripe bank account path.** Call `plaid.processorStripeBankAccountTokenCreate` to get a Stripe-compatible bank account token, then attach it to a Stripe customer and initiate a PaymentIntent or SetupIntent with `payment_method_types: ["us_bank_account"]`.
2. **Dwolla funding source path.** Create a Dwolla processor token via Plaid and add it as a Dwolla funding source.

This article covers the Stripe path — the same Worker pattern applies to Dwolla by swapping the processor token call.

Constraints at the edge:
- Plaid's `/link/token/create` must be called server-side (it requires the Plaid secret).
- The `public_token` exchange (`/item/public_token/exchange`) must also be server-side.
- Workers have no persistent memory between requests; store `item_id` → `access_token` mapping in D1 (encrypted).
- Plaid access tokens never expire but items can lose healthy status. Store and monitor `ITEM_LOGIN_REQUIRED` webhooks.

---

## Section 1 — Creating a Plaid Link Token (Server-Side)

```typescript
// worker/src/handlers/plaid-link-token.ts
export interface Env {
  PLAID_CLIENT_ID: string;
  PLAID_SECRET: string;     // stored as Worker secret
  PLAID_ENV: "sandbox" | "development" | "production";
  PLAID_DB: D1Database;
  ENCRYPTION_KEY: string;   // AES-256-GCM key, hex-encoded, Worker secret
}

const PLAID_BASE: Record<string, string> = {
  sandbox: "https://sandbox.plaid.com",
  development: "https://development.plaid.com",
  production: "https://production.plaid.com",
};

export async function createLinkToken(
  userId: string,
  env: Env
): Promise<{ linkToken: string; expiration: string }> {
  const base = PLAID_BASE[env.PLAID_ENV];

  const resp = await fetch(`${base}/link/token/create`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      client_id: env.PLAID_CLIENT_ID,
      secret: env.PLAID_SECRET,
      client_name: "Your Platform",
      language: "en",
      country_codes: ["US"],
      user: { client_user_id: userId },
      products: ["auth"],    // "auth" provides routing + account numbers
      webhook: "https://api.example.com/plaid/webhook",
    }),
  });

  if (!resp.ok) {
    const err = await resp.json() as { error_message?: string };
    throw new Error(`Plaid link token error: ${err.error_message}`);
  }

  const data = await resp.json() as { link_token: string; expiration: string };
  return { linkToken: data.link_token, expiration: data.expiration };
}
```

---

## Section 2 — Exchanging the Public Token and Storing the Access Token

```typescript
// worker/src/handlers/plaid-exchange.ts
import { Env } from "./plaid-link-token";

async function encryptAccessToken(token: string, keyHex: string): Promise<string> {
  const keyBytes = Uint8Array.from(keyHex.match(/.{2}/g)!.map(b => parseInt(b, 16)));
  const key = await crypto.subtle.importKey(
    "raw", keyBytes, { name: "AES-GCM" }, false, ["encrypt"]
  );
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const enc = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv },
    key,
    new TextEncoder().encode(token)
  );
  const combined = new Uint8Array(iv.byteLength + enc.byteLength);
  combined.set(iv);
  combined.set(new Uint8Array(enc), iv.byteLength);
  return btoa(String.fromCharCode(...combined));
}

export async function exchangePublicToken(
  publicToken: string,
  userId: string,
  env: Env
): Promise<{ itemId: string; stripeToken: string }> {
  const base = PLAID_BASE[env.PLAID_ENV];

  // Step 1: Exchange public token → access token + item ID
  const exchangeResp = await fetch(`${base}/item/public_token/exchange`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      client_id: env.PLAID_CLIENT_ID,
      secret: env.PLAID_SECRET,
      public_token: publicToken,
    }),
  });

  const exchangeData = await exchangeResp.json() as {
    access_token: string;
    item_id: string;
  };

  // Step 2: Create a Stripe processor token from the access token
  const accountsResp = await fetch(`${base}/auth/get`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      client_id: env.PLAID_CLIENT_ID,
      secret: env.PLAID_SECRET,
      access_token: <redacted-secret>
    }),
  });
  const accountsData = await accountsResp.json() as {
    accounts: Array<{ account_id: string; subtype: string }>;
  };
  const checkingAccount = accountsData.accounts.find(a => a.subtype === "checking");
  if (!checkingAccount) throw new Error("No checking account found");

  const processorResp = await fetch(`${base}/processor/stripe/bank_account_token/create`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      client_id: env.PLAID_CLIENT_ID,
      secret: env.PLAID_SECRET,
      access_token: <redacted-secret>
      account_id: checkingAccount.account_id,
    }),
  });
  const processorData = await processorResp.json() as { stripe_bank_account_token: string };

  // Step 3: Encrypt and store access token
  const encryptedToken = await encryptAccessToken(exchangeData.access_token, env.ENCRYPTION_KEY);

  await env.PLAID_DB.prepare(
    `INSERT INTO plaid_items (item_id, user_id, encrypted_access_token, status, created_at)
     VALUES (?, ?, ?, 'good', ?)
     ON CONFLICT(item_id) DO UPDATE SET encrypted_access_token = excluded.encrypted_access_token`
  )
    .bind(exchangeData.item_id, userId, encryptedToken, Math.floor(Date.now() / 1000))
    .run();

  return { itemId: exchangeData.item_id, stripeToken: processorData.stripe_bank_account_token };
}

const PLAID_BASE: Record<string, string> = {
  sandbox: "https://sandbox.plaid.com",
  development: "https://development.plaid.com",
  production: "https://production.plaid.com",
};
```

---

## Section 3 — Attaching the Bank Account to Stripe and Initiating ACH

```typescript
// worker/src/handlers/ach-payment.ts
import Stripe from "stripe";
import { Env } from "./plaid-link-token";

export async function initiateAchPayment(
  stripeCustomerId: string,
  stripeBankToken: string,
  amountCents: number,
  env: Env
): Promise<{ paymentIntentId: string }> {
  const stripe = new Stripe(env.STRIPE_SECRET_KEY, {
    apiVersion: "2024-11-20.acacia",
    httpClient: Stripe.createFetchHttpClient(),
  });

  // Attach the Plaid-sourced bank account token to the Stripe customer
  const bankAccount = await stripe.customers.createSource(stripeCustomerId, {
    source: stripeBankToken,
  }) as Stripe.BankAccount;

  // Verify the account (Stripe requires micro-deposit verification for non-instant-verify)
  // For Plaid-sourced tokens the bank account is already verified — skip micro-deposits
  // by checking `bankAccount.status === "verified"`

  if (bankAccount.status !== "verified") {
    throw new Error(`Bank account not instantly verified: ${bankAccount.status}`);
  }

  // Create a PaymentIntent for ACH debit
  const intent = await stripe.paymentIntents.create({
    amount: amountCents,
    currency: "usd",
    customer: stripeCustomerId,
    payment_method_data: {
      type: "us_bank_account",
      us_bank_account: {
        account_holder_type: "individual",
        // Stripe attaches the bank account as a source; reference it here
      },
    },
    payment_method_types: ["us_bank_account"],
    mandate_data: {
      customer_acceptance: {
        type: "online",
        online: { ip_address: "0.0.0.0", user_agent: "CloudflareWorker" },
      },
    },
    confirm: true,
    metadata: { plaid_bank_account_id: bankAccount.id },
  });

  return { paymentIntentId: intent.id };
}
```

---

## Section 4 — Plaid Webhook Handler for Item Health Monitoring

```typescript
// worker/src/handlers/plaid-webhook.ts
import { Env } from "./plaid-link-token";

export async function handlePlaidWebhook(
  request: Request,
  env: Env
): Promise<Response> {
  // Plaid sends webhook verification header — validate it
  const body = await request.text();
  const webhookType = (JSON.parse(body) as { webhook_type: string }).webhook_type;
  const webhookCode = (JSON.parse(body) as { webhook_code: string }).webhook_code;
  const itemId = (JSON.parse(body) as { item_id: string }).item_id;

  if (webhookType === "ITEM" && webhookCode === "ERROR") {
    const error = (JSON.parse(body) as { error: { error_code: string } }).error;

    if (error.error_code === "ITEM_LOGIN_REQUIRED") {
      // User must re-authenticate through Plaid Link (update mode)
      await env.PLAID_DB.prepare(
        `UPDATE plaid_items SET status = 'login_required', updated_at = ? WHERE item_id = ?`
      )
        .bind(Math.floor(Date.now() / 1000), itemId)
        .run();

      // Notify the user to re-link their bank account
      // (queue a task to your notification system)
    }
  }

  return new Response(JSON.stringify({ received: true }), { status: 200 });
}
```

---

## Anti-Patterns

- **Sending the Plaid access token to the client.** The access token is equivalent to the user's banking credentials scoped to your item. Store it encrypted server-side only; never return it in a browser response.
- **Using `products: ["transactions"]` when you only need ACH.** Request only the `auth` product. Additional products increase the data Plaid accesses from the user's bank, widen your compliance scope, and require explicit user consent disclosures.
- **Skipping Item health monitoring.** Plaid access tokens can go invalid when the user's bank requires re-authentication (password change, MFA upgrade). Without the `ITEM_LOGIN_REQUIRED` webhook handler, your ACH payments silently fail.
- **Storing the Plaid access token in KV unencrypted.** KV values are accessible to all Workers in your account. Encrypt at rest using AES-256-GCM with a Workers Secret as the key.
- **Initiating ACH for amounts below the bank's minimum.** Many banks reject ACH debits below $1.00. Enforce a minimum server-side before calling Stripe.

---

## Gotchas

1. **Plaid sandbox uses static credentials.** In sandbox mode, `user_good / pass_good` works for most test banks. In production, users must authenticate with real credentials through the bank's own OAuth flow.
2. **Stripe processor bank tokens are single-use.** The token returned by `/processor/stripe/bank_account_token/create` can only be used once to attach a bank account. Attempting to reuse it returns a Stripe `invalid_request_error`.
3. **ACH pull settlement takes 2–5 business days.** The PaymentIntent moves through `requires_payment_method → processing → succeeded` over days, not seconds. Do not grant access based on `processing` status.
4. **Micro-deposit fallback.** If the Plaid `auth` product cannot instantly verify the account (less common banks), Stripe falls back to micro-deposit verification — a 1–2 day delay. Build this path in your UI.
5. **Plaid does not support Workers' `fetch` without a custom `user-agent`.** Plaid's API does not impose restrictions on fetch, but some reverse proxies between Workers and Plaid may block requests with no User-Agent header. Set `User-Agent: YourPlatform/1.0` on all Plaid API calls.

---

## Verification

```bash
# 1. Create a Plaid sandbox link token
curl -X POST https://sandbox.plaid.com/link/token/create \
  -H "Content-Type: application/json" \
  -d '{"client_id":"...","secret":"...","client_name":"Test","language":"en",
       "country_codes":["US"],"user":{"client_user_id":"user_123"},"products":["auth"]}'

# 2. Complete Link flow in sandbox using user_good / pass_good
# Capture the public_token from the onSuccess callback

# 3. Exchange and verify D1 item record
wrangler d1 execute PLAID_DB --remote \
  --command "SELECT item_id, user_id, status FROM plaid_items ORDER BY created_at DESC LIMIT 5;"

# 4. Confirm the Stripe bank account attached and is verified
stripe customers retrieve cus_xxx --expand sources
```

---

## Related

- `documentation/categories/payments/ach-debit-pull-payment-orchestration-workers-d1.md`
- `documentation/categories/payments/open-banking-pay-by-bank-integration.md`
- `documentation/categories/payments/dwolla-ach-transfer-api-workers-d1.md`
- `documentation/categories/payments/stripe-bank-transfer.md`
- `documentation/categories/payments/idempotency-keys-payment-apis.md`

---

## Sources

- Plaid Link documentation — https://plaid.com/docs/link/
- Plaid processor token for Stripe — https://plaid.com/docs/auth/partnerships/stripe/
- Stripe US bank account payments — https://stripe.com/docs/payments/ach-debit
- Plaid webhook reference — https://plaid.com/docs/api/webhooks/
- Cloudflare Workers Secrets — https://developers.cloudflare.com/workers/configuration/secrets/
