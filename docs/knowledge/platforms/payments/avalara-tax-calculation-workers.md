# Avalara AvaTax Calculation on Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Your checkout flow must calculate US sales tax and VAT in real time before the customer submits payment, and your legal team requires the authoritative Avalara AvaTax engine rather than a simple rate table. The calculation must happen edge-side on Cloudflare Workers to keep latency below 200 ms and avoid rounding discrepancies when the PSP later captures the exact amount.

## Context

Avalara's AvaTax REST v2 API accepts a `CreateTransactionModel` and returns per-line tax detail. Workers calls AvaTax synchronously during checkout (`/api/v2/transactions/create?$include=Lines,Details`). On payment capture the Worker commits the same transaction by its `code`; on refund it voids or creates a return invoice. Credentials are a username/password (account number + license key) sent as HTTP Basic Auth — store both in Workers secrets, never in `wrangler.toml` plain-text.

## Calculate Tax at Checkout

```typescript
// src/avalara.ts
export interface Env {
  AVALARA_ACCOUNT_NUMBER: string; // e.g. "1234567890"
  AVALARA_LICENSE_KEY: string;    // e.g. "ABCD1234567890EF"
  AVALARA_COMPANY_CODE: string;   // e.g. "DEFAULT"
  AVALARA_ENV: "sandbox" | "production";
}

const BASE_URL: Record<string, string> = {
  sandbox: "https://sandbox-rest.avatax.com",
  production: "https://rest.avatax.com",
};

function avataxAuth(env: Env): string {
  return "Basic " + btoa(`${env.AVALARA_ACCOUNT_NUMBER}:${env.AVALARA_LICENSE_KEY}`);
}

export interface LineItem {
  lineNumber: string;
  quantity: number;
  amount: number; // pre-tax, in major currency unit (USD)
  taxCode: string; // e.g. "P0000000" for tangible personal property
  description: string;
}

export interface TaxResult {
  transactionCode: string;
  totalTax: number;
  totalAmount: number;
  lines: Array<{ lineNumber: string; tax: number }>;
}

export async function calculateTax(
  transactionCode: string,
  shipToAddress: {
    line1: string;
    city: string;
    region: string; // state code
    postalCode: string;
    country: string;
  },
  lines: LineItem[],
  env: Env
): Promise<TaxResult> {
  const body = {
    type: "SalesOrder", // do not commit yet
    companyCode: env.AVALARA_COMPANY_CODE,
    date: new Date().toISOString().slice(0, 10),
    code: transactionCode,
    customerCode: "CHECKOUT",
    addresses: {
      singleLocation: {
        ...shipToAddress,
      },
    },
    lines: lines.map((l) => ({
      number: l.lineNumber,
      quantity: l.quantity,
      amount: l.amount,
      taxCode: l.taxCode,
      description: l.description,
    })),
    commit: false,
  };

  const res = await fetch(
    `${BASE_URL[env.AVALARA_ENV]}/api/v2/transactions/create`,
    {
      method: "POST",
      headers: {
        Authorization: avataxAuth(env),
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(body),
    }
  );

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`AvaTax error ${res.status}: ${err}`);
  }

  const data: any = await res.json();

  return {
    transactionCode: data.code,
    totalTax: data.totalTax,
    totalAmount: data.totalAmount,
    lines: data.lines.map((l: any) => ({ lineNumber: l.lineNumber, tax: l.tax })),
  };
}
```

## Commit Transaction on Payment Capture

```typescript
// src/handlers/avalara-commit.ts
import { avataxAuth } from "../avalara";

export async function commitTransaction(
  transactionCode: string,
  env: Env
): Promise<void> {
  const url =
    `${BASE_URL[env.AVALARA_ENV]}/api/v2/companies/${env.AVALARA_COMPANY_CODE}` +
    `/transactions/${encodeURIComponent(transactionCode)}/commit`;

  const res = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: avataxAuth(env),
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ commit: true }),
  });

  if (!res.ok) {
    throw new Error(`AvaTax commit failed ${res.status}: ${await res.text()}`);
  }
}
```

## Void or Refund a Transaction

```typescript
// src/handlers/avalara-void.ts
import { avataxAuth } from "../avalara";

type VoidReason = "DocDeleted" | "DocVoided" | "TaxDateAdjustment" | "AdjustmentCancelled";

export async function voidTransaction(
  transactionCode: string,
  reason: VoidReason,
  env: Env
): Promise<void> {
  const url =
    `${BASE_URL[env.AVALARA_ENV]}/api/v2/companies/${env.AVALARA_COMPANY_CODE}` +
    `/transactions/${encodeURIComponent(transactionCode)}/void`;

  const res = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: avataxAuth(env),
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ code: reason }),
  });

  if (!res.ok) {
    throw new Error(`AvaTax void failed ${res.status}: ${await res.text()}`);
  }
}

// For partial refunds, create a ReturnInvoice instead of voiding
export async function createReturnInvoice(
  originalCode: string,
  lines: Array<{ lineNumber: string; quantity: number; amount: number; taxCode: string }>,
  env: Env
): Promise<void> {
  const body = {
    type: "ReturnInvoice",
    companyCode: env.AVALARA_COMPANY_CODE,
    date: new Date().toISOString().slice(0, 10),
    code: `REFUND-${originalCode}-${Date.now()}`,
    referenceCode: originalCode,
    customerCode: "CHECKOUT",
    lines: lines.map((l) => ({
      number: l.lineNumber,
      quantity: -Math.abs(l.quantity),
      amount: -Math.abs(l.amount),
      taxCode: l.taxCode,
    })),
    commit: true,
  };

  const res = await fetch(
    `${BASE_URL[env.AVALARA_ENV]}/api/v2/transactions/create`,
    {
      method: "POST",
      headers: {
        Authorization: avataxAuth(env),
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    }
  );

  if (!res.ok) {
    throw new Error(`AvaTax return invoice failed: ${await res.text()}`);
  }
}
```

## Anti-patterns

- Do not commit a `SalesOrder` transaction during the checkout estimate step; commit only after successful payment capture to keep your Avalara ledger clean.
- Do not cache tax calculations by postal code alone; rates vary by product `taxCode` and nexus registration, so always call AvaTax with the full address.
- Do not reuse the same `transactionCode` for a retry without voiding the previous one; AvaTax deduplicates by code and returns the original (possibly stale) result.

## Gotchas

- Workers does not have access to a `btoa` polyfill in older runtimes; use `Buffer.from(...).toString("base64")` or confirm `btoa` is available in your `compatibility_date`.
- The Avalara sandbox URL (`sandbox-rest.avatax.com`) returns 401 if you use production credentials and vice versa — keep `AVALARA_ENV` in sync with which credential set you deploy.
- AvaTax rate-limits unauthenticated pings; your health-check endpoint should call `/api/v2/utilities/ping` with valid credentials, not anonymously.

## Verification

```bash
# Ping AvaTax sandbox
curl -u "$AVALARA_ACCOUNT_NUMBER:$AVALARA_LICENSE_KEY" \
  https://sandbox-rest.avatax.com/api/v2/utilities/ping

# Calculate tax for a California address
curl -u "$AVALARA_ACCOUNT_NUMBER:$AVALARA_LICENSE_KEY" \
  -X POST https://sandbox-rest.avatax.com/api/v2/transactions/create \
  -H "Content-Type: application/json" \
  -d '{"type":"SalesOrder","companyCode":"DEFAULT","date":"2026-08-23","code":"TEST-001","customerCode":"TEST","addresses":{"singleLocation":{"line1":"123 Main St","city":"Los Angeles","region":"CA","postalCode":"90001","country":"US"}},"lines":[{"number":"1","quantity":1,"amount":100,"taxCode":"P0000000","description":"Widget"}],"commit":false}'
```

## Related

- `payments/tax-calculation-workers-stripe-tax.md`
- `payments/vat-calculation-eu.md`
- `payments/sales-tax-us-states.md`

## Sources

- https://developer.avalara.com/api-reference/avatax/rest/v2/methods/Transactions/CreateTransaction/
- https://developer.avalara.com/avatax/commit-void/
- https://developer.avalara.com/avatax/return-invoice/
