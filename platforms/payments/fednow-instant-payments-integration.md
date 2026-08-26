# FedNow Instant Payments Integration on Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Platforms that need real-time USD fund movement between US bank accounts — payroll, marketplace payouts, insurance claims — require a sub-10-second settlement rail. FedNow, the Federal Reserve's instant payment service (live since July 2023), provides 24/7/365 settlement finality under ISO 20022 messaging.

## Context
FedNow is accessed indirectly: your platform connects to a FedNow-participating bank or payment service provider (PSP) such as Column Bank, Lead Bank, or Moov via their REST or ISO 20022 API. Cloudflare Workers act as the orchestration layer — validating requests, calling the bank API, and handling inbound credit notifications via webhook. Settlement is final in < 10 seconds; there are no chargebacks, only returns (R-codes) within the R-return window.

## Initiating a Credit Transfer

Build a strongly-typed wrapper around your bank's FedNow API. Column Bank is used as an example; adapt field names for your provider.

```typescript
// fednow-send.ts
import type { D1Database } from "@cloudflare/workers-types";

interface Env {
  COLUMN_API_KEY: string;
  COLUMN_BASE_URL: string;   // https://api.column.com
  DB: D1Database;
}

interface FedNowSendParams {
  idempotencyKey: string;
  debtorAccountId: string;     // your platform's Column account
  creditorRoutingNumber: string;
  creditorAccountNumber: string;
  creditorName: string;
  amountCents: number;         // USD cents
  remittanceInfo: string;      // max 140 chars (ISO 20022 unstructured remittance)
}

interface FedNowTransferResponse {
  id: string;
  status: "pending" | "completed" | "returned";
  createdAt: string;
  message?: string;
}

export async function sendFedNow(
  params: FedNowSendParams,
  env: Env
): Promise<FedNowTransferResponse> {
  const payload = {
    idempotency_key: params.idempotencyKey,
    account_number_id: params.debtorAccountId,
    counterparty: {
      routing_number: params.creditorRoutingNumber,
      account_number: params.creditorAccountNumber,
      name: params.creditorName,
    },
    amount: params.amountCents,
    currency_code: "USD",
    description: params.remittanceInfo.slice(0, 140),
    type: "fedwire_instant",  // Column-specific: selects FedNow rail
  };

  const res = await fetch(`${env.COLUMN_BASE_URL}/transfers/bank`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.COLUMN_API_KEY}`,
      "Content-Type": "application/json",
      "Idempotency-Key": params.idempotencyKey,
    },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`FedNow send failed: ${res.status} ${err}`);
  }

  const data = await res.json<FedNowTransferResponse>();

  await env.DB.prepare(
    `INSERT OR IGNORE INTO fednow_transfers
       (id, idempotency_key, debtor_account, creditor_routing, creditor_account,
        amount_cents, status, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
  )
    .bind(
      data.id,
      params.idempotencyKey,
      params.debtorAccountId,
      params.creditorRoutingNumber,
      params.creditorAccountNumber,
      params.amountCents,
      data.status,
      data.createdAt
    )
    .run();

  return data;
}
```

## Receiving Credit Notifications via Webhook

Banks push ISO 20022 `pacs.008` (credit transfer) events as webhooks. Verify the HMAC signature before processing.

```typescript
// fednow-webhook.ts
import type { D1Database } from "@cloudflare/workers-types";

interface Env {
  COLUMN_WEBHOOK_SECRET: string;
  DB: D1Database;
}

export async function handleColumnWebhook(req: Request, env: Env): Promise<Response> {
  const rawBody = await req.text();
  const signature = req.headers.get("Column-Signature") ?? "";

  if (!(await verifyHmac(rawBody, signature, env.COLUMN_WEBHOOK_SECRET))) {
    return new Response("Unauthorized", { status: 401 });
  }

  const event = JSON.parse(rawBody) as {
    type: string;
    data: {
      id: string;
      status: string;
      amount: number;
      description: string;
      created_at: string;
      return_code?: string;
    };
  };

  if (event.type === "bank_transfer.updated") {
    const t = event.data;
    await env.DB.prepare(
      `UPDATE fednow_transfers
         SET status = ?, return_code = ?, updated_at = CURRENT_TIMESTAMP
       WHERE id = ?`
    )
      .bind(t.status, t.return_code ?? null, t.id)
      .run();

    if (t.status === "returned" && t.return_code) {
      await handleReturn(t.id, t.return_code, env);
    }
  }

  return new Response("ok");
}

async function handleReturn(
  transferId: string,
  returnCode: string,
  env: { DB: D1Database }
): Promise<void> {
  // R01 = insufficient funds, R02 = account closed, R03 = no account, etc.
  const reason = RETURN_CODES[returnCode] ?? "unknown";
  await env.DB.prepare(
    `INSERT INTO fednow_returns (transfer_id, return_code, reason, returned_at)
     VALUES (?, ?, ?, CURRENT_TIMESTAMP)`
  )
    .bind(transferId, returnCode, reason)
    .run();
  // Trigger notification to platform ops — integrate with your alerting system
}

const RETURN_CODES: Record<string, string> = {
  R01: "insufficient_funds",
  R02: "account_closed",
  R03: "no_account_located",
  R04: "invalid_account_number",
  R07: "authorization_revoked",
  R10: "customer_advises_not_authorized",
};

async function verifyHmac(body: string, signature: string, secret: string): Promise<boolean> {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["verify"]
  );
  const expected = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(body));
  const expectedHex = Array.from(new Uint8Array(expected))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
  return expectedHex === signature;
}
```

## Idempotency and Duplicate Transfer Prevention

FedNow has no chargeback mechanism; a duplicate send costs real money. Gate every outbound transfer through a D1 idempotency check.

```typescript
// fednow-idempotency.ts
import type { D1Database } from "@cloudflare/workers-types";
import { sendFedNow, type FedNowTransferResponse } from "./fednow-send";

export async function idempotentSend(
  params: Parameters<typeof sendFedNow>[0],
  env: Parameters<typeof sendFedNow>[1]
): Promise<FedNowTransferResponse> {
  const existing = await env.DB.prepare(
    `SELECT id, status FROM fednow_transfers WHERE idempotency_key = ?`
  )
    .bind(params.idempotencyKey)
    .first<{ id: string; status: string }>();

  if (existing) {
    return { id: existing.id, status: existing.status as FedNowTransferResponse["status"], createdAt: "" };
  }

  return sendFedNow(params, env);
}
```

## Amount and Routing Validation

FedNow has a $500 000 per-transaction limit (participants may set lower). Validate before calling the bank API.

```typescript
// fednow-validate.ts
const FEDNOW_MAX_CENTS = 50_000_000; // $500,000.00

export function validateFedNowParams(params: {
  amountCents: number;
  creditorRoutingNumber: string;
  remittanceInfo: string;
}): string | null {
  if (params.amountCents <= 0) return "amount must be positive";
  if (params.amountCents > FEDNOW_MAX_CENTS)
    return `amount ${params.amountCents} exceeds FedNow limit ${FEDNOW_MAX_CENTS}`;
  if (!/^\d{9}$/.test(params.creditorRoutingNumber))
    return "routing number must be exactly 9 digits";
  if (params.remittanceInfo.length > 140)
    return "remittance info exceeds 140-char ISO 20022 limit";
  return null;
}
```

## Anti-patterns
- Polling the bank API for transfer status instead of handling webhooks — FedNow settles in seconds; polling adds unnecessary load and delay.
- Omitting idempotency keys — duplicate POSTs during network retries result in duplicate real-money transfers.
- Not storing return codes — R-code patterns identify systemic issues (stale account numbers, bad routing) that need ops remediation.
- Treating FedNow as equivalent to ACH — ACH has 2-day settlement and chargebacks; FedNow is final and irrevocable within the settlement window.

## Gotchas
- Not all US banks participate in FedNow; verify participation at the Federal Reserve's directory before attempting a credit transfer to a given routing number.
- FedNow operates 24/7 but your participating bank's API may have maintenance windows — handle 503 responses with a Cloudflare Queue retry.
- The per-transaction limit ($500 000 at launch) is set by the Fed but individual banks can lower it further; confirm your bank's limit.
- ISO 20022 `pacs.008` fields map differently across bank wrappers — always test end-to-end in sandbox before production.

## Verification
1. Use Column Bank sandbox: send a test transfer to the Column test creditor account.
2. Verify D1 row inserted with `status = "pending"`.
3. Simulate the webhook payload with the sandbox signature secret — confirm status updates to `"completed"`.
4. Send a duplicate request with the same idempotency key — confirm it returns the existing record without a second API call.
5. Send amount > $500 000 — expect validation error before network call.

## Related
- [ACH vs Card Cost Economics](ach-vs-card-cost-economics.md)
- [Payment Retry Exponential Backoff with Cloudflare Queues](payment-retry-exponential-backoff-cloudflare-queues.md)
- [Idempotency Keys for Payment APIs](idempotency-keys-payment-apis.md)
- [Real-time Payments Fraud Window](real-time-payments-fraud-window.md)

## Sources
- Federal Reserve FedNow Service: https://www.frbservices.org/financial-services/fednow/
- Column Bank Transfer API: https://column.com/docs/transfers
- ISO 20022 pacs.008 message definition: https://www.iso20022.org/iso-20022-message-definitions
- FedNow participation directory: https://www.frbservices.org/financial-services/fednow/fednow-participant-list.html
