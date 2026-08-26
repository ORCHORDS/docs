# Wise Payouts API for Multi-Currency Mass Payouts on Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Marketplace and gig-economy platforms need to pay out earnings to recipients in 50+ countries in local currency without holding foreign currency balances. Wise (formerly TransferWise) provides competitive FX rates, a batch payout API, and multi-currency balances that integrate well with a Cloudflare Workers orchestration layer.

## Context
Wise Business offers a Payouts API that supports bank transfers in 70+ currencies via local payment rails (UK Faster Payments, SEPA, ACH, etc.). The platform holds balances in Wise multi-currency accounts and tops them up as needed. Cloudflare Workers handle recipient management, batch job orchestration, and webhook processing. D1 tracks transfer lifecycle and reconciliation state.

## Creating and Verifying Recipient Accounts

Before sending funds, create and verify a recipient profile. Wise performs bank account validation synchronously where possible.

```typescript
// wise-recipients.ts
interface Env {
  WISE_API_KEY: string;
  WISE_PROFILE_ID: string;   // numeric Wise business profile ID
  WISE_BASE_URL: string;     // https://api.wise.com
}

interface RecipientCreateParams {
  currency: string;           // ISO 4217, e.g. "EUR", "GBP", "USD"
  legalType: "PRIVATE" | "BUSINESS";
  fullName: string;
  iban?: string;              // SEPA
  sortCode?: string;          // UK
  accountNumber?: string;
  routingNumber?: string;     // US ACH
  email?: string;             // for PayPal-style transfers
  countryCode: string;        // ISO 3166-1 alpha-2
}

interface WiseRecipient {
  id: number;
  currency: string;
  name: { fullName: string };
  active: boolean;
}

export async function createRecipient(
  params: RecipientCreateParams,
  env: Env
): Promise<WiseRecipient> {
  const details: Record<string, string> = {};
  if (params.iban) details["iban"] = params.iban;
  if (params.sortCode) details["sortCode"] = params.sortCode;
  if (params.accountNumber) details["accountNumber"] = params.accountNumber;
  if (params.routingNumber) details["abartn"] = params.routingNumber;
  if (params.email) details["email"] = params.email;

  const res = await fetch(`${env.WISE_BASE_URL}/v1/accounts`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.WISE_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      profile: Number(env.WISE_PROFILE_ID),
      accountHolderName: params.fullName,
      currency: params.currency,
      type: params.iban ? "iban" : params.sortCode ? "sort_code" : "aba",
      details,
      legalType: params.legalType,
    }),
  });

  if (!res.ok) throw new Error(`Wise recipient create error: ${res.status} ${await res.text()}`);
  return res.json<WiseRecipient>();
}
```

## Quoting the Transfer

Always quote before creating a transfer; the quote locks in the exchange rate for a short window and returns the guaranteed delivery amount.

```typescript
// wise-quote.ts
interface WiseQuote {
  id: string;
  sourceCurrency: string;
  targetCurrency: string;
  sourceAmount: number;
  targetAmount: number;
  rate: number;
  fee: number;
  expirationTime: string;
}

export async function createQuote(
  sourceCurrency: string,
  targetCurrency: string,
  targetAmount: number,   // pay exactly this amount in target currency
  env: { WISE_API_KEY: string; WISE_PROFILE_ID: string; WISE_BASE_URL: string }
): Promise<WiseQuote> {
  const res = await fetch(`${env.WISE_BASE_URL}/v3/profiles/${env.WISE_PROFILE_ID}/quotes`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.WISE_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      sourceCurrency,
      targetCurrency,
      targetAmount,
      payOut: "BANK_TRANSFER",
    }),
  });

  if (!res.ok) throw new Error(`Wise quote error: ${res.status} ${await res.text()}`);
  return res.json<WiseQuote>();
}
```

## Creating Transfers and Funding

Tie a quote to a recipient and fund from the platform's Wise balance. Use idempotency keys to prevent double-sends.

```typescript
// wise-transfer.ts
import type { D1Database } from "@cloudflare/workers-types";
import { createQuote } from "./wise-quote";

interface Env {
  WISE_API_KEY: string;
  WISE_PROFILE_ID: string;
  WISE_BASE_URL: string;
  DB: D1Database;
}

interface WiseTransfer {
  id: number;
  status: string;
  targetValue: number;
  targetCurrency: string;
}

export async function createAndFundTransfer(
  recipientId: number,
  sourceCurrency: string,
  targetCurrency: string,
  targetAmountMinor: number,    // smallest unit (cents, pence, etc.)
  referenceId: string,          // idempotency / your internal ID
  env: Env
): Promise<WiseTransfer> {
  // Convert minor units to major
  const targetAmount = targetAmountMinor / 100;

  const quote = await createQuote(sourceCurrency, targetCurrency, targetAmount, env);

  // Check for existing transfer to ensure idempotency
  const existingRow = await env.DB.prepare(
    "SELECT wise_transfer_id FROM wise_transfers WHERE reference_id = ?"
  )
    .bind(referenceId)
    .first<{ wise_transfer_id: number }>();

  if (existingRow) {
    return { id: existingRow.wise_transfer_id, status: "existing", targetValue: targetAmount, targetCurrency };
  }

  const res = await fetch(`${env.WISE_BASE_URL}/v1/transfers`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.WISE_API_KEY}`,
      "Content-Type": "application/json",
      "X-idempotence-uuid": referenceId,
    },
    body: JSON.stringify({
      targetAccount: recipientId,
      quoteUuid: quote.id,
      customerTransactionId: referenceId,
      details: { reference: referenceId.slice(0, 35) },
    }),
  });

  if (!res.ok) throw new Error(`Wise transfer create error: ${res.status} ${await res.text()}`);
  const transfer = await res.json<WiseTransfer>();

  // Fund the transfer from Wise balance
  const fundRes = await fetch(
    `${env.WISE_BASE_URL}/v3/profiles/${env.WISE_PROFILE_ID}/transfers/${transfer.id}/payments`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${env.WISE_API_KEY}`, "Content-Type": "application/json" },
      body: JSON.stringify({ type: "BALANCE" }),
    }
  );
  if (!fundRes.ok) throw new Error(`Wise funding error: ${fundRes.status} ${await fundRes.text()}`);

  await env.DB.prepare(
    `INSERT INTO wise_transfers (reference_id, wise_transfer_id, status, target_currency,
       target_amount, source_currency, rate, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)`
  )
    .bind(referenceId, transfer.id, transfer.status, targetCurrency, targetAmount, sourceCurrency, quote.rate)
    .run();

  return transfer;
}
```

## Webhook Handling for Transfer State Updates

Wise sends signed webhook events when transfer status changes (`processing`, `funds_converted`, `outgoing_payment_sent`, `bounced_back`, `cancelled`).

```typescript
// wise-webhooks.ts
import type { D1Database } from "@cloudflare/workers-types";
import * as crypto from "node:crypto";

interface Env {
  WISE_WEBHOOK_PUBLIC_KEY: string;  // PEM; store in secret
  DB: D1Database;
}

export async function handleWiseWebhook(req: Request, env: Env): Promise<Response> {
  const signature = req.headers.get("X-Signature-SHA256") ?? "";
  const rawBody = await req.text();

  // Wise signs with RSA-SHA256; verify using Web Crypto
  const valid = await verifyRsaSignature(rawBody, signature, env.WISE_WEBHOOK_PUBLIC_KEY);
  if (!valid) return new Response("Unauthorized", { status: 401 });

  const event = JSON.parse(rawBody) as {
    event_type: string;
    data: { resource: { id: number; profile_id: number; current_state: string } };
  };

  if (event.event_type === "transfers#state-change") {
    const { id, current_state } = event.data.resource;
    await env.DB.prepare(
      "UPDATE wise_transfers SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE wise_transfer_id = ?"
    )
      .bind(current_state, id)
      .run();
  }

  return new Response("ok");
}

async function verifyRsaSignature(body: string, b64Sig: string, pemKey: string): Promise<boolean> {
  try {
    // Strip PEM headers and decode
    const pem = pemKey.replace(/-----[^-]+-----/g, "").replace(/\s/g, "");
    const keyData = Uint8Array.from(atob(pem), (c) => c.charCodeAt(0));
    const key = await crypto.subtle.importKey(
      "spki", keyData.buffer, { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["verify"]
    );
    const sig = Uint8Array.from(atob(b64Sig), (c) => c.charCodeAt(0));
    return crypto.subtle.verify("RSASSA-PKCS1-v1_5", key, sig, new TextEncoder().encode(body));
  } catch {
    return false;
  }
}
```

## Anti-patterns
- Creating a transfer without a quote — Wise uses dynamic FX rates; skipping the quote step means you don't know the source debit until after the fact.
- Reusing an expired quote — quotes expire in ~30 minutes; check `expirationTime` and re-quote if stale.
- Not storing `customerTransactionId` — it is the only idempotency anchor; lose it and you cannot detect duplicates.
- Sending `sourceAmount` instead of `targetAmount` — for recipient-focused payouts, always specify the target to guarantee the exact amount received.
- Polling for status instead of consuming webhooks — transfers can take hours for some corridors.

## Gotchas
- Wise's sandbox environment uses different API keys and base URL (`https://api.sandbox.transferwise.tech`); keep them strictly separated.
- `bounced_back` transfers require manual intervention in the Wise dashboard or a re-quote and re-send; automate alerting, not the retry.
- Balance top-ups are done via bank transfer to Wise; automate low-balance alerts to avoid insufficient funds blocking a batch.
- Some recipient account types require additional detail fields (e.g. BIC for SWIFT); use the Wise `/v1/account-requirements` endpoint to discover required fields per corridor dynamically.

## Verification
1. Create a sandbox recipient with a valid IBAN.
2. Request a quote for EUR → GBP 50.00 and confirm `rate` and `expirationTime` fields are present.
3. Create and fund the transfer; confirm D1 row with `status = "processing"`.
4. Simulate a `transfers#state-change` webhook payload signed with the sandbox key.
5. Query D1: `SELECT status FROM wise_transfers WHERE reference_id = '<your-id>'` — expect `"outgoing_payment_sent"`.

## Related
- [Multi-currency KV Exchange Rate Cache](multi-currency-kv-exchange-rate-cache-edge-pricing.md)
- [Payout Run Scheduling](payout-run-scheduling-engineering.md)
- [Payment Reconciliation](payment-reconciliation.md)
- [Cross-border Payment Routing](cross-border-payment-routing.md)

## Sources
- Wise Payouts API documentation: https://docs.wise.com/api-docs/guides/payouts
- Wise webhook events: https://docs.wise.com/api-docs/features/notifications/webhooks
- ISO 4217 currency codes: https://www.iso.org/iso-4217-currency-codes.html
