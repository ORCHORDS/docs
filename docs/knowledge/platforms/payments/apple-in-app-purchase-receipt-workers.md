# Verifying Apple In-App Purchase Receipts Server-Side in a Cloudflare Worker

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your iOS app sends a purchase token to your backend and you need to verify it with Apple's App Store Server API v2, store the verified transaction in D1 to prevent replay attacks, and grant the appropriate entitlement to the user — all without Node.js or a traditional server.

---

## Context

Apple's App Store Server API v2 replaces the deprecated `verifyReceipt` endpoint with a REST API that returns signed JWS transaction objects. Authentication requires a JSON Web Token (ES256) signed with a private key obtained from App Store Connect. The private key is stored as a PEM-encoded environment secret and loaded at runtime using `crypto.subtle.importKey`. D1 stores verified `originalTransactionId` values with a `UNIQUE` constraint so duplicate or replayed transactions are rejected at the database layer. An entitlement table is updated transactionally after verification. The Worker also exposes a webhook endpoint for App Store Server Notifications v2 to handle refunds and renewals.

---

## Section 1 — D1 Schema

```sql
CREATE TABLE IF NOT EXISTS iap_transactions (
  original_transaction_id TEXT PRIMARY KEY,
  transaction_id          TEXT NOT NULL,
  bundle_id               TEXT NOT NULL,
  product_id              TEXT NOT NULL,
  purchase_date           TEXT NOT NULL,
  expires_date            TEXT,
  in_app_ownership_type   TEXT NOT NULL CHECK(in_app_ownership_type IN ('PURCHASED','FAMILY_SHARED')),
  revocation_date         TEXT,
  user_id                 TEXT NOT NULL,
  environment             TEXT NOT NULL CHECK(environment IN ('Sandbox','Production')),
  recorded_at             TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_iap_user_product
  ON iap_transactions (user_id, product_id);

CREATE TABLE IF NOT EXISTS entitlements (
  user_id          TEXT NOT NULL,
  product_id       TEXT NOT NULL,
  granted_at       TEXT NOT NULL DEFAULT (datetime('now')),
  expires_at       TEXT,
  revoked_at       TEXT,
  source_txn_id    TEXT REFERENCES iap_transactions(original_transaction_id),
  PRIMARY KEY (user_id, product_id)
);
```

---

## Section 2 — JWT Authentication and Verification Worker

```typescript
export interface Env {
  DB: D1Database;
  APPLE_PRIVATE_KEY_PEM: string;   // ES256 .p8 file contents from App Store Connect
  APPLE_KEY_ID: string;            // 10-char key identifier
  APPLE_ISSUER_ID: string;         // Team ID (UUID format)
  APPLE_BUNDLE_ID: string;         // e.g. com.orchords.app
  ENVIRONMENT: string;             // 'production' | 'sandbox'
}

// Convert PEM private key string to CryptoKey for ES256 signing
async function importApplePrivateKey(pem: string): Promise<CryptoKey> {
  // Strip PEM headers and decode base64
  const pemBody = pem
    .replace(/<redacted-private-key>/, '')
    .replace(/\s+/g, '');

  const derBuffer = Uint8Array.from(atob(pemBody), (c) => c.charCodeAt(0));

  return crypto.subtle.importKey(
    'pkcs8',
    derBuffer,
    { name: 'ECDSA', namedCurve: 'P-256' },
    false,
    ['sign']
  );
}

// Build a signed App Store Server API JWT (valid for 60 minutes)
async function buildAppleJWT(env: Env): Promise<string> {
  const now = Math.floor(Date.now() / 1000);

  const header = { alg: 'ES256', kid: env.APPLE_KEY_ID, typ: 'JWT' };
  const payload = {
    iss: env.APPLE_ISSUER_ID,
    iat: now,
    exp: now + 3600,
    aud: 'appstoreconnect-v1',
    bid: env.APPLE_BUNDLE_ID,
  };

  const encode = (obj: object) =>
    btoa(JSON.stringify(obj)).replace(/=/g, '').replace(/\+/g, '-').replace(/\//g, '_');

  const headerEncoded = encode(header);
  const payloadEncoded = encode(payload);
  const signingInput = `${headerEncoded}.${payloadEncoded}`;

  const privateKey = await importApplePrivateKey(env.APPLE_PRIVATE_KEY_PEM);

  const signatureBuffer = await crypto.subtle.sign(
    { name: 'ECDSA', hash: 'SHA-256' },
    privateKey,
    new TextEncoder().encode(signingInput)
  );

  const signatureEncoded = btoa(
    String.fromCharCode(...new Uint8Array(signatureBuffer))
  ).replace(/=/g, '').replace(/\+/g, '-').replace(/\//g, '_');

  return `${signingInput}.${signatureEncoded}`;
}

interface AppStoreTransaction {
  originalTransactionId: string;
  transactionId: string;
  bundleId: string;
  productId: string;
  purchaseDate: number;      // milliseconds since epoch
  expiresDate?: number;
  inAppOwnershipType: string;
  revocationDate?: number;
  environment: string;
}

// Decode a JWS payload (trust is established by the App Store API — the response itself is signed by Apple)
function decodeJWSPayload(jws: string): AppStoreTransaction {
  const parts = jws.split('.');
  if (parts.length !== 3) throw new Error('Invalid JWS format');
  const decoded = atob(parts[1].replace(/-/g, '+').replace(/_/g, '/'));
  return JSON.parse(decoded) as AppStoreTransaction;
}

// POST /iap/verify  — called by the iOS app after a successful StoreKit 2 purchase
export async function verifyReceipt(
  request: Request,
  env: Env
): Promise<Response> {
  const { user_id, transaction_id } = await request.json<{
    user_id: string;
    transaction_id: string;     // originalTransactionId from StoreKit 2
  }>();

  if (!user_id || !transaction_id) {
    return Response.json({ error: 'user_id and transaction_id are required' }, { status: 422 });
  }

  // Check D1 first — fast dedup before hitting Apple
  const existing = await env.DB.prepare(
    'SELECT original_transaction_id, user_id FROM iap_transactions WHERE original_transaction_id = ?1'
  )
    .bind(transaction_id)
    .first<{ original_transaction_id: string; user_id: string }>();

  if (existing) {
    if (existing.user_id !== user_id) {
      return Response.json({ error: 'Transaction belongs to a different user' }, { status: 409 });
    }
    return Response.json({ status: 'already_verified', original_transaction_id: transaction_id });
  }

  // Call App Store Server API v2
  const env_ = env.ENVIRONMENT === 'production' ? '' : 'sandbox.';
  const apiUrl = `https://api.${env_}storekit.itunes.apple.com/inApps/v2/history/${transaction_id}`;
  const jwt = await buildAppleJWT(env);

  const appleResponse = await fetch(apiUrl, {
    headers: { Authorization: `Bearer ${jwt}` },
  });

  if (!appleResponse.ok) {
    const errBody = await appleResponse.text();
    return Response.json(
      { error: 'Apple API error', detail: errBody },
      { status: appleResponse.status }
    );
  }

  const appleData = await appleResponse.json<{ signedTransactions: string[] }>();
  if (!appleData.signedTransactions?.length) {
    return Response.json({ error: 'No transactions found' }, { status: 404 });
  }

  // Decode the most recent transaction (last in the array)
  const txn = decodeJWSPayload(appleData.signedTransactions[appleData.signedTransactions.length - 1]);

  // Validate bundle ID matches
  if (txn.bundleId !== env.APPLE_BUNDLE_ID) {
    return Response.json({ error: 'Bundle ID mismatch' }, { status: 403 });
  }

  const purchaseDate = new Date(txn.purchaseDate).toISOString();
  const expiresDate = txn.expiresDate ? new Date(txn.expiresDate).toISOString() : null;

  // Insert — UNIQUE constraint on original_transaction_id prevents race-condition dupes
  try {
    await env.DB.prepare(
      `INSERT INTO iap_transactions
         (original_transaction_id, transaction_id, bundle_id, product_id,
          purchase_date, expires_date, in_app_ownership_type, user_id, environment)
       VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9)`
    )
      .bind(
        txn.originalTransactionId,
        txn.transactionId,
        txn.bundleId,
        txn.productId,
        purchaseDate,
        expiresDate,
        txn.inAppOwnershipType,
        user_id,
        txn.environment
      )
      .run();
  } catch (err) {
    // UNIQUE constraint violation — another request won the race; treat as already verified
    if ((err as Error).message?.includes('UNIQUE constraint failed')) {
      return Response.json({ status: 'already_verified', original_transaction_id: txn.originalTransactionId });
    }
    throw err;
  }

  // Grant entitlement
  await env.DB.prepare(
    `INSERT INTO entitlements (user_id, product_id, expires_at, source_txn_id)
     VALUES (?1, ?2, ?3, ?4)
     ON CONFLICT(user_id, product_id) DO UPDATE
       SET expires_at    = excluded.expires_at,
           revoked_at    = NULL,
           granted_at    = datetime('now'),
           source_txn_id = excluded.source_txn_id`
  )
    .bind(user_id, txn.productId, expiresDate, txn.originalTransactionId)
    .run();

  return Response.json({
    status: 'verified',
    original_transaction_id: txn.originalTransactionId,
    product_id: txn.productId,
    expires_at: expiresDate,
  });
}
```

---

## Section 3 — App Store Server Notifications Webhook

```typescript
// POST /iap/notifications  — App Store Server Notifications v2
export async function handleAppleNotification(
  request: Request,
  env: Env
): Promise<Response> {
  const { signedPayload } = await request.json<{ signedPayload: string }>();

  // Apple's notification payload is a JWS; the outer payload contains a nested signedTransactionInfo
  let notificationData: {
    notificationType: string;
    subtype?: string;
    data: { signedTransactionInfo?: string };
  };

  try {
    notificationData = decodeJWSPayload(signedPayload) as typeof notificationData;
  } catch {
    return new Response('Invalid JWS', { status: 400 });
  }

  const { notificationType, data } = notificationData;

  if (notificationType === 'REFUND' && data.signedTransactionInfo) {
    const txn = decodeJWSPayload(data.signedTransactionInfo);
    await env.DB.prepare(
      `UPDATE iap_transactions
       SET revocation_date = datetime('now')
       WHERE original_transaction_id = ?1`
    )
      .bind(txn.originalTransactionId)
      .run();

    // Revoke entitlement
    await env.DB.prepare(
      `UPDATE entitlements
       SET revoked_at = datetime('now')
       WHERE source_txn_id = ?1`
    )
      .bind(txn.originalTransactionId)
      .run();
  }

  // Handle DID_RENEW — update expires_date for auto-renewable subscriptions
  if (notificationType === 'DID_RENEW' && data.signedTransactionInfo) {
    const txn = decodeJWSPayload(data.signedTransactionInfo);
    const newExpiry = txn.expiresDate ? new Date(txn.expiresDate).toISOString() : null;
    await env.DB.prepare(
      `UPDATE entitlements SET expires_at = ?1
       WHERE user_id = (
         SELECT user_id FROM iap_transactions
         WHERE original_transaction_id = ?2
       ) AND product_id = ?3`
    )
      .bind(newExpiry, txn.originalTransactionId, txn.productId)
      .run();
  }

  return new Response('ok', { status: 200 });
}
```

---

## Anti-patterns

- **Using the deprecated `/verifyReceipt` endpoint** — Apple deprecated it; use App Store Server API v2 (`/inApps/v2/history/:transactionId`) for all new integrations.
- **Trusting the client's decoded transaction data** — Always decode the JWS on the server; never accept a client-provided `productId` or `expiresDate` without verifying against the Apple API response.
- **Storing the raw `.p8` private key in `wrangler.toml`** — Store it with `wrangler secret put APPLE_PRIVATE_KEY_PEM`; PEM files contain newlines so use `printf` rather than `echo` when setting the secret.
- **Re-using the same JWT for multiple requests** — The JWT has a 60-minute TTL but re-importing the key on every request is cheap enough; alternatively cache the JWT in memory for the Worker's lifetime (V8 isolate scope).

---

## Gotchas

- Apple's `.p8` private key file uses `BEGIN PRIVATE KEY` (PKCS#8), not `BEGIN EC PRIVATE KEY`; `crypto.subtle.importKey` with `pkcs8` format is correct.
- The `purchaseDate` and `expiresDate` fields in the JWS payload are milliseconds since epoch (not seconds); divide by 1000 before passing to `new Date()` if using Unix timestamps directly.
- Sandbox transactions come from `api.sandbox.storekit.itunes.apple.com`; always gate on the environment to avoid production API calls in development.
- The `signedTransactions` array in the history response is paginated; for long transaction histories follow the `hasMore` field and `revision` cursor.
- `atob`/`btoa` in Workers handle the Base64URL alphabet (`-` and `_`) if you replace characters before calling; failure to replace causes silent `undefined` payloads.

---

## Verification

```bash
# Set the private key secret (multiline-safe)
printf '%s' "$(cat AuthKey_XXXXXXXXXX.p8)" | npx wrangler secret put APPLE_PRIVATE_KEY_PEM
npx wrangler secret put APPLE_KEY_ID
npx wrangler secret put APPLE_ISSUER_ID

# Test with a Sandbox transaction ID from StoreKit 2
curl -X POST https://your-worker.workers.dev/iap/verify \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"u_001","transaction_id":"2000000xxxxxxxxx"}'

# Confirm transaction in D1
npx wrangler d1 execute your-db --command \
  "SELECT original_transaction_id, product_id, environment, recorded_at FROM iap_transactions;"

# Confirm entitlement
npx wrangler d1 execute your-db --command \
  "SELECT user_id, product_id, expires_at, revoked_at FROM entitlements;"
```

---

## Related

- `payment-idempotency-key-workers-kv.md`
- `paddle-webhook-workers-d1-billing.md`

---

## Sources

- App Store Server API — https://developer.apple.com/documentation/appstoreserverapi
- App Store Server Notifications v2 — https://developer.apple.com/documentation/appstoreservernotifications
- Web Crypto API ECDSA — https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/sign
