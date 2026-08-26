# Dwolla ACH Transfer API Integration via Cloudflare Workers and D1

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-Case

You need to move money between US bank accounts via ACH without routing through a card network. Dwolla's white-label API lets you initiate bank-to-bank transfers — platform-to-user payouts, user-to-platform payments, and user-to-user transfers — using verified funding sources. Common use cases: marketplace payouts, lending disbursements, insurance settlements, payroll top-ups. The challenge is managing Dwolla's multi-step verification flow (IAV or micro-deposits), storing customer and funding-source state in D1, and handling Dwolla's webhook-driven event model from a Cloudflare Worker.

---

## Context

Dwolla operates as a money transmitter. Your platform must complete KYC on its Dwolla account (business verification) before going live. Each end-user who initiates or receives transfers must be created as a Dwolla Customer and have at least one verified Funding Source.

Verification paths:
- **Instant Account Verification (IAV)** — Dwolla's embedded JS component that links via Plaid or MX behind the scenes. Fastest path.
- **Micro-deposit verification** — Dwolla sends two small deposits; the user confirms the amounts. 1–2 business days.

Dwolla's API is REST + HAL JSON. Resources are referenced by URL (HAL `_links`), not by opaque IDs — you must parse the `Location` header after POSTs to get the created resource URL. Transfer state transitions come via webhooks: `transfer_created`, `transfer_pending`, `transfer_processed`, `transfer_failed`, `transfer_cancelled`.

Workers-specific constraints:
- Dwolla requires an OAuth 2.0 bearer token obtained from `/oauth/v2/token`. Tokens expire in 3,600 seconds. Cache them in KV.
- Dwolla's base URLs: `https://api.dwolla.com` (production), `https://api-sandbox.dwolla.com` (sandbox).

---

## Section 1 — OAuth Token Management with KV Caching

```typescript
// worker/src/lib/dwolla.ts
export interface Env {
  DWOLLA_KEY: string;
  DWOLLA_SECRET: string;
  DWOLLA_ENV: "sandbox" | "production";
  DWOLLA_TOKEN_KV: KVNamespace;
  DWOLLA_DB: D1Database;
}

const BASE_URL: Record<string, string> = {
  sandbox: "https://api-sandbox.dwolla.com",
  production: "https://api.dwolla.com",
};

export async function getDwollaToken(env: Env): Promise<string> {
  const cached = await env.DWOLLA_TOKEN_KV.get("dwolla:access_token");
  if (cached) return cached;

  const base = BASE_URL[env.DWOLLA_ENV];
  const resp = await fetch(`${base}/oauth/v2/token`, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      Authorization: `Basic ${btoa(`${env.DWOLLA_KEY}:${env.DWOLLA_SECRET}`)}`,
    },
    body: "grant_type=client_credentials",
  });

  if (!resp.ok) throw new Error(`Dwolla token error: ${await resp.text()}`);

  const data = await resp.json() as { access_token: string; expires_in: number };

  // Cache with 55-second margin before expiry
  await env.DWOLLA_TOKEN_KV.put(
    "dwolla:access_token",
    data.access_token,
    { expirationTtl: data.expires_in - 55 }
  );

  return data.access_token;
}

export function dwollaFetch(
  path: string,
  token: string,
  env: Env,
  init: RequestInit = {}
): Promise<Response> {
  const base = BASE_URL[env.DWOLLA_ENV];
  return fetch(`${base}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.dwolla.v1.hal+json",
      "Content-Type": "application/vnd.dwolla.v1.hal+json",
      ...(init.headers ?? {}),
    },
  });
}
```

---

## Section 2 — Creating a Dwolla Customer and Storing in D1

```sql
-- migrations/0020_dwolla_customers.sql
CREATE TABLE IF NOT EXISTS dwolla_customers (
  id              TEXT PRIMARY KEY,       -- internal UUID
  dwolla_url      TEXT NOT NULL UNIQUE,   -- HAL URL, e.g. https://api.dwolla.com/customers/xxx
  user_id         TEXT NOT NULL UNIQUE,
  type            TEXT NOT NULL DEFAULT 'personal', -- personal | business | receive-only | unverified
  status          TEXT NOT NULL DEFAULT 'unverified',
  -- unverified | retry | document | verified | suspended | deactivated
  created_at      INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS dwolla_funding_sources (
  id              TEXT PRIMARY KEY,
  dwolla_url      TEXT NOT NULL UNIQUE,
  customer_url    TEXT NOT NULL,
  name            TEXT NOT NULL,
  type            TEXT NOT NULL DEFAULT 'checking',
  status          TEXT NOT NULL DEFAULT 'unverified',
  -- unverified | verified
  removed         INTEGER NOT NULL DEFAULT 0,
  created_at      INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS dwolla_transfers (
  id              TEXT PRIMARY KEY,
  dwolla_url      TEXT UNIQUE,
  source_url      TEXT NOT NULL,
  destination_url TEXT NOT NULL,
  amount_cents    INTEGER NOT NULL,
  currency        TEXT NOT NULL DEFAULT 'USD',
  status          TEXT NOT NULL DEFAULT 'created',
  -- created | pending | processed | failed | cancelled
  idempotency_key TEXT NOT NULL UNIQUE,
  created_at      INTEGER NOT NULL,
  processed_at    INTEGER
);
```

```typescript
// worker/src/handlers/dwolla-customers.ts
import { getDwollaToken, dwollaFetch, Env } from "../lib/dwolla";
import { v4 as uuidv4 } from "uuid";

export async function createDwollaCustomer(
  userId: string,
  firstName: string,
  lastName: string,
  email: string,
  env: Env
): Promise<{ customerUrl: string }> {
  const token = await getDwollaToken(env);

  const resp = await dwollaFetch("/customers", token, env, {
    method: "POST",
    body: JSON.stringify({ firstName, lastName, email, type: "personal" }),
  });

  if (resp.status !== 201) {
    const err = await resp.json() as { message?: string };
    throw new Error(`Dwolla customer creation failed: ${err.message}`);
  }

  const customerUrl = resp.headers.get("Location") ?? "";

  await env.DWOLLA_DB.prepare(
    `INSERT INTO dwolla_customers (id, dwolla_url, user_id, type, status, created_at)
     VALUES (?, ?, ?, 'personal', 'unverified', ?)`
  )
    .bind(uuidv4(), customerUrl, userId, Math.floor(Date.now() / 1000))
    .run();

  return { customerUrl };
}
```

---

## Section 3 — Initiating an ACH Transfer with Idempotency

```typescript
// worker/src/handlers/dwolla-transfer.ts
import { getDwollaToken, dwollaFetch, Env } from "../lib/dwolla";
import { v4 as uuidv4 } from "uuid";

export async function initiateTransfer(
  sourceFundingUrl: string,
  destinationFundingUrl: string,
  amountCents: number,
  idempotencyKey: string,
  env: Env
): Promise<{ transferUrl: string }> {
  // Check for prior attempt
  const existing = await env.DWOLLA_DB.prepare(
    `SELECT dwolla_url FROM dwolla_transfers WHERE idempotency_key = ?`
  )
    .bind(idempotencyKey)
    .first<{ dwolla_url: string | null }>();

  if (existing?.dwolla_url) {
    return { transferUrl: existing.dwolla_url };
  }

  const token = await getDwollaToken(env);

  // Insert pending row before calling Dwolla
  const internalId = uuidv4();
  await env.DWOLLA_DB.prepare(
    `INSERT INTO dwolla_transfers
       (id, source_url, destination_url, amount_cents, status, idempotency_key, created_at)
     VALUES (?, ?, ?, ?, 'created', ?, ?)`
  )
    .bind(internalId, sourceFundingUrl, destinationFundingUrl,
          amountCents, idempotencyKey, Math.floor(Date.now() / 1000))
    .run();

  const amountDollars = (amountCents / 100).toFixed(2);

  const resp = await dwollaFetch("/transfers", token, env, {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    body: JSON.stringify({
      _links: {
        source: { href: sourceFundingUrl },
        destination: { href: destinationFundingUrl },
      },
      amount: { currency: "USD", value: amountDollars },
    }),
  });

  if (resp.status !== 201) {
    const err = await resp.json() as { message?: string };
    await env.DWOLLA_DB.prepare(
      `UPDATE dwolla_transfers SET status = 'failed' WHERE id = ?`
    ).bind(internalId).run();
    throw new Error(`Dwolla transfer failed: ${err.message}`);
  }

  const transferUrl = resp.headers.get("Location") ?? "";

  await env.DWOLLA_DB.prepare(
    `UPDATE dwolla_transfers SET dwolla_url = ?, status = 'pending' WHERE id = ?`
  ).bind(transferUrl, internalId).run();

  return { transferUrl };
}
```

---

## Section 4 — Dwolla Webhook Handler for Transfer Status Updates

```typescript
// worker/src/handlers/dwolla-webhook.ts
import { Env } from "../lib/dwolla";
import { createHmac } from "crypto"; // Not available in Workers — use Web Crypto

async function verifyDwollaWebhook(
  body: string,
  signature: string,
  secret: string
): Promise<boolean> {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["verify"]
  );
  const sigBytes = Uint8Array.from(
    signature.match(/.{2}/g)!.map(b => parseInt(b, 16))
  );
  return crypto.subtle.verify(
    "HMAC",
    key,
    sigBytes,
    new TextEncoder().encode(body)
  );
}

export async function handleDwollaWebhook(
  request: Request,
  env: Env & { DWOLLA_WEBHOOK_SECRET: string }
): Promise<Response> {
  const body = await request.text();
  const sig = request.headers.get("X-Request-Signature-SHA-256") ?? "";

  const valid = await verifyDwollaWebhook(body, sig, env.DWOLLA_WEBHOOK_SECRET);
  if (!valid) return new Response("Invalid signature", { status: 400 });

  const event = JSON.parse(body) as {
    topic: string;
    resourceSummary: { id: string };
    _links: { resource: { href: string } };
  };

  const transferUrl = event._links.resource.href;

  const statusMap: Record<string, string> = {
    "transfer_created": "created",
    "transfer_pending": "pending",
    "transfer_processed": "processed",
    "transfer_failed": "failed",
    "transfer_cancelled": "cancelled",
  };

  const newStatus = statusMap[event.topic];
  if (newStatus) {
    await env.DWOLLA_DB.prepare(
      `UPDATE dwolla_transfers
       SET status = ?, processed_at = CASE WHEN ? = 'processed' THEN ? ELSE processed_at END
       WHERE dwolla_url = ?`
    )
      .bind(newStatus, newStatus, Math.floor(Date.now() / 1000), transferUrl)
      .run();
  }

  return new Response(JSON.stringify({ received: true }), { status: 200 });
}
```

---

## Anti-Patterns

- **Storing Dwolla resource URLs as opaque IDs in your UI.** Dwolla URLs contain environment-specific domains (`api.dwolla.com` vs `api-sandbox.dwolla.com`). Store the full URL in D1 and use your internal UUID in all user-facing contexts.
- **Parsing the transfer URL from the JSON body instead of the `Location` header.** Dwolla's HAL JSON may include self-referencing links, but the canonical created-resource URL is always the `Location` response header.
- **Omitting the `Idempotency-Key` header on transfer creation.** Workers can crash between the `fetch` call and the response storage. Without an idempotency key, a retry creates a duplicate transfer.
- **Polling for transfer status instead of consuming webhooks.** Dwolla does not provide a real-time polling path; webhook delivery is the intended status update mechanism. Polling the transfer endpoint on a cron costs API quota.
- **Treating `transfer_pending` as funds available.** Pending means the ACH entry was submitted. Funds are not available to the destination until `transfer_processed`, which can be 1–3 business days later.

---

## Gotchas

1. **HAL JSON content type.** All requests must include `Accept: application/vnd.dwolla.v1.hal+json` and `Content-Type: application/vnd.dwolla.v1.hal+json`. Sending `application/json` returns a 406.
2. **Dollar amounts, not cents, in Dwolla API.** Unlike Stripe, Dwolla expects string dollar amounts (`"10.50"` not `1050`). Convert cents to dollars with `.toFixed(2)` before submission.
3. **Unverified customers cannot initiate transfers.** A customer in `unverified` status can only receive transfers up to $500/week. For full send capability, the customer must complete personal or business verification.
4. **Sandbox transfers process immediately.** In sandbox, transfers move to `processed` within seconds. In production, standard ACH takes 1–3 business days; same-day ACH (if enabled) settles same day if submitted before 3 PM CT.
5. **Webhook secret rotation.** Dwolla generates a webhook subscription secret at subscription creation time. Store it as a Worker Secret. If you need to rotate it, create a new webhook subscription and delete the old one — there is no update-in-place endpoint.

---

## Verification

```bash
# 1. Obtain a sandbox OAuth token
curl -X POST https://api-sandbox.dwolla.com/oauth/v2/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -u "YOUR_KEY:YOUR_SECRET" \
  -d "grant_type=client_credentials"

# 2. Create a sandbox customer and note the Location header
curl -X POST https://api-sandbox.dwolla.com/customers \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/vnd.dwolla.v1.hal+json" \
  -d '{"firstName":"Test","lastName":"User","email":"test@example.com","type":"personal"}'

# 3. Verify D1 transfer table updates on webhook receipt
wrangler d1 execute DWOLLA_DB --remote \
  --command "SELECT id, status, amount_cents, processed_at FROM dwolla_transfers ORDER BY created_at DESC LIMIT 5;"

# 4. Confirm no duplicate transfers for the same idempotency key
wrangler d1 execute DWOLLA_DB --remote \
  --command "SELECT idempotency_key, COUNT(*) as n FROM dwolla_transfers GROUP BY idempotency_key HAVING n > 1;"
```

---

## Related

- `documentation/categories/payments/plaid-link-ach-payment-initiation-workers.md`
- `documentation/categories/payments/ach-debit-pull-payment-orchestration-workers-d1.md`
- `documentation/categories/payments/idempotency-keys-payment-apis.md`
- `documentation/categories/payments/payment-retry-exponential-backoff-cloudflare-queues.md`
- `documentation/categories/payments/fednow-instant-payments-integration.md`

---

## Sources

- Dwolla API reference — https://developers.dwolla.com/api-reference
- Dwolla transfers guide — https://developers.dwolla.com/docs/balance/transfer-money-between-users
- Dwolla webhook verification — https://developers.dwolla.com/docs/drop-in-components/webhooks
- Cloudflare Workers KV — https://developers.cloudflare.com/kv/
- Cloudflare D1 — https://developers.cloudflare.com/d1/
