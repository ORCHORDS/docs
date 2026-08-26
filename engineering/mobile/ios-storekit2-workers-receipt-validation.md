# iOS StoreKit 2 Transaction Validation via Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

iOS apps using StoreKit 2 receive `Transaction` objects signed as JWS (JSON Web Signature)
tokens rather than the legacy base64-encoded receipts that required server-side decoding via
Apple's `/verifyReceipt` endpoint. Teams migrating to StoreKit 2 need a Cloudflare Workers
backend that can verify the JWS signature using Apple's public keys, persist entitlements to
D1, and handle subscription renewal events from App Store Server Notifications.

## Context

StoreKit 2 (iOS 15+, available via `StoreKit` framework in Swift) presents each transaction
as a `Transaction` struct whose `jsonRepresentation` property contains a JWS-signed payload.
Apple signs these with ECDSA P-256 keys published at
`https://appleid.apple.com/auth/keys`. A Cloudflare Worker acts as the validation backend: it
fetches Apple's JWKS, caches the keys in KV, verifies the JWS signature, decodes the
purchase payload, and writes entitlements to D1. This replaces the legacy App Store receipt
validation flow and removes the need to proxy to Apple's servers from your mobile client.

## Swift StoreKit 2 Transaction Listener

```swift
// Sources/Purchases/PurchaseManager.swift
import StoreKit
import Foundation

actor PurchaseManager {
    private let validationURL: URL
    private var transactionListenerTask: Task<Void, Error>?

    init(validationURL: URL) {
        self.validationURL = validationURL
    }

    func startListening() {
        transactionListenerTask = Task.detached(priority: .background) { [weak self] in
            for await verificationResult in Transaction.updates {
                guard let self else { return }
                await self.handle(verificationResult: verificationResult)
            }
        }
    }

    func purchase(_ product: Product) async throws -> Transaction {
        let result = try await product.purchase()
        switch result {
        case .success(let verification):
            let transaction = try verification.payloadValue
            // Send JWS token to Workers for server-side validation
            try await validateWithWorkers(transaction: transaction)
            await transaction.finish()
            return transaction
        case .userCancelled:
            throw PurchaseError.userCancelled
        case .pending:
            throw PurchaseError.pending
        @unknown default:
            throw PurchaseError.unknown
        }
    }

    private func handle(verificationResult: VerificationResult<Transaction>) async {
        switch verificationResult {
        case .verified(let transaction):
            do {
                try await validateWithWorkers(transaction: transaction)
                await transaction.finish()
            } catch {
                // Log but don't crash — App Store will retry unfinished transactions
                print("[PurchaseManager] Validation failed: \(error)")
            }
        case .unverified(_, let error):
            print("[PurchaseManager] Unverified transaction: \(error)")
        }
    }

    private func validateWithWorkers(transaction: Transaction) async throws {
        guard let token = transaction.jwsRepresentation else {
            throw PurchaseError.missingJWS
        }

        var request = URLRequest(url: validationURL.appendingPathComponent("/api/iap/validate"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(["jwsToken": token])

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            throw PurchaseError.validationFailed
        }

        let result = try JSONDecoder().decode(ValidationResponse.self, from: data)
        guard result.valid else {
            throw PurchaseError.validationFailed
        }
    }
}

enum PurchaseError: Error {
    case userCancelled, pending, unknown, missingJWS, validationFailed
}

struct ValidationResponse: Decodable {
    let valid: Bool
    let entitlements: [String]
    let expiresAt: Date?
}
```

## Workers JWS Verification Endpoint

```typescript
// workers/src/iap/validate.ts
import { validateJWS } from './jws';
import { upsertEntitlement } from './entitlements';

export interface Env {
  DB: D1Database;
  JWK_CACHE: KVNamespace;
  APPLE_BUNDLE_ID: string;
}

export interface StoreKit2Payload {
  transactionId: string;
  originalTransactionId: string;
  bundleId: string;
  productId: string;
  purchaseDate: number;
  expiresDate?: number;
  inAppOwnershipType: 'PURCHASED' | 'FAMILY_SHARED';
  type: 'Auto-Renewable Subscription' | 'Non-Consumable' | 'Consumable';
  revocationDate?: number;
  revocationReason?: number;
}

const APPLE_JWKS_URL = 'https://appleid.apple.com/auth/keys';
const JWK_CACHE_TTL = 3600; // 1 hour

async function getAppleJWKS(env: Env): Promise<JsonWebKey[]> {
  const cached = await env.JWK_CACHE.get<JsonWebKey[]>('apple_jwks', 'json');
  if (cached) return cached;

  const res = await fetch(APPLE_JWKS_URL);
  if (!res.ok) throw new Error(`JWKS fetch failed: ${res.status}`);
  const { keys } = await res.json<{ keys: JsonWebKey[] }>();

  await env.JWK_CACHE.put('apple_jwks', JSON.stringify(keys), {
    expirationTtl: JWK_CACHE_TTL,
  });
  return keys;
}

async function verifyStoreKit2JWS(
  jwsToken: string,
  keys: JsonWebKey[]
): Promise<StoreKit2Payload> {
  const parts = jwsToken.split('.');
  if (parts.length !== 3) throw new Error('Invalid JWS format');

  const [headerB64, payloadB64, signatureB64] = parts;

  // Decode header to find kid
  const header = JSON.parse(atob(headerB64.replace(/-/g, '+').replace(/_/g, '/')));
  const matchingKey = keys.find(k => k.kid === header.kid);
  if (!matchingKey) throw new Error(`No matching key for kid: ${header.kid}`);

  // Import the ECDSA key
  const cryptoKey = await crypto.subtle.importKey(
    'jwk',
    matchingKey,
    { name: 'ECDSA', namedCurve: 'P-256' },
    false,
    ['verify']
  );

  // Verify signature
  const sigData = new TextEncoder().encode(`${headerB64}.${payloadB64}`);
  const signature = Uint8Array.from(
    atob(signatureB64.replace(/-/g, '+').replace(/_/g, '/')),
    c => c.charCodeAt(0)
  );

  const valid = await crypto.subtle.verify(
    { name: 'ECDSA', hash: 'SHA-256' },
    cryptoKey,
    signature,
    sigData
  );
  if (!valid) throw new Error('JWS signature verification failed');

  // Decode payload
  const payloadJson = atob(payloadB64.replace(/-/g, '+').replace(/_/g, '/'));
  return JSON.parse(payloadJson) as StoreKit2Payload;
}

export async function handleValidate(req: Request, env: Env): Promise<Response> {
  if (req.method !== 'POST') {
    return new Response('Method not allowed', { status: 405 });
  }

  let jwsToken: string;
  try {
    const body = await req.json<{ jwsToken: string }>();
    jwsToken = body.jwsToken;
    if (!jwsToken) throw new Error('Missing jwsToken');
  } catch {
    return Response.json({ error: 'Invalid request body' }, { status: 400 });
  }

  let payload: StoreKit2Payload;
  try {
    const jwks = await getAppleJWKS(env);
    payload = await verifyStoreKit2JWS(jwsToken, jwks);
  } catch (err) {
    return Response.json({ valid: false, error: String(err) }, { status: 422 });
  }

  // Validate bundle ID matches your app
  if (payload.bundleId !== env.APPLE_BUNDLE_ID) {
    return Response.json({ valid: false, error: 'Bundle ID mismatch' }, { status: 403 });
  }

  // Reject revoked transactions
  if (payload.revocationDate) {
    return Response.json({ valid: false, error: 'Transaction revoked' }, { status: 403 });
  }

  await upsertEntitlement(env.DB, payload);

  const expiresAt = payload.expiresDate
    ? new Date(payload.expiresDate).toISOString()
    : null;

  return Response.json({
    valid: true,
    entitlements: [payload.productId],
    expiresAt,
    transactionId: payload.transactionId,
  });
}
```

## Entitlement Persistence in D1

```typescript
// workers/src/iap/entitlements.ts
import type { StoreKit2Payload } from './validate';

export async function upsertEntitlement(
  db: D1Database,
  payload: StoreKit2Payload
): Promise<void> {
  const expiresAt = payload.expiresDate
    ? new Date(payload.expiresDate).toISOString()
    : null;

  await db
    .prepare(
      `INSERT INTO entitlements
         (transaction_id, original_transaction_id, product_id, purchase_date, expires_at, revoked)
       VALUES (?, ?, ?, ?, ?, 0)
       ON CONFLICT(transaction_id) DO UPDATE SET
         expires_at = excluded.expires_at,
         revoked = excluded.revoked`
    )
    .bind(
      payload.transactionId,
      payload.originalTransactionId,
      payload.productId,
      new Date(payload.purchaseDate).toISOString(),
      expiresAt
    )
    .run();
}

// D1 schema migration
// CREATE TABLE IF NOT EXISTS entitlements (
//   transaction_id TEXT PRIMARY KEY,
//   original_transaction_id TEXT NOT NULL,
//   product_id TEXT NOT NULL,
//   purchase_date TEXT NOT NULL,
//   expires_at TEXT,
//   revoked INTEGER NOT NULL DEFAULT 0,
//   created_at TEXT NOT NULL DEFAULT (datetime('now'))
// );
// CREATE INDEX IF NOT EXISTS idx_entitlements_original ON entitlements(original_transaction_id);
```

## Anti-patterns

- Trusting the JWS payload without verifying the signature — always call
  `crypto.subtle.verify` before reading any field from the decoded payload.
- Caching Apple's JWKS with `immutable` or very long TTLs — Apple rotates keys; a 1-hour TTL
  with stale-while-revalidate strikes the right balance between freshness and latency.
- Finishing the StoreKit 2 `Transaction` on device before Workers validation succeeds — if
  the network call fails and you've already called `transaction.finish()`, the purchase is
  gone from the queue and the entitlement is never recorded server-side.

## Gotchas

- StoreKit 2's `jwsRepresentation` property is `nil` for transactions restored via
  `Transaction.currentEntitlements` on devices running iOS 15.0–15.3 due to a bug; always
  check for nil and fall back to legacy receipt validation for older OS versions.
- Workers' `crypto.subtle` uses raw ECDSA signatures (r||s format), but Apple's JWS tokens
  use DER-encoded signatures in some older SDK versions — test against real sandbox purchases,
  not just locally crafted JWS tokens.

## Verification

```bash
# Apply D1 migration
npx wrangler d1 execute MY_DB --file ./migrations/0001_entitlements.sql

# Start dev server
npx wrangler dev --port 8787

# Generate a test JWS (requires a real sandbox transaction or use Apple's test environment)
# POST the token to the validation endpoint
curl -s -X POST http://localhost:8787/api/iap/validate \
  -H "Content-Type: application/json" \
  -d '{"jwsToken": "PASTE_REAL_SANDBOX_JWS_HERE"}' | jq

# Check entitlements in D1
npx wrangler d1 execute MY_DB \
  --command "SELECT * FROM entitlements ORDER BY created_at DESC LIMIT 5"
```

## Related

- `mobile/ios-in-app-purchase.md`
- `mobile/android-in-app-billing.md`
- `mobile/mobile-webauthn-workers-credential-storage.md`

## Sources

- https://developer.apple.com/documentation/storekit/transaction
- https://developer.apple.com/documentation/appstoreserverapi
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
