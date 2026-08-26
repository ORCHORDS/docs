# Capacitor In-App Purchase → Workers Receipt Validation (StoreKit 2 + Google Play)

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Capacitor app sells subscriptions or consumables via `@capacitor-community/in-app-purchases`
(or `@ionic-enterprise/purchase`) and you need server-side receipt validation to:

- Prevent receipt replay / sharing between users.
- Grant entitlements stored in D1 without trusting the client.
- Handle subscription renewals, cancellations, and refunds via Apple/Google server notifications.
- Expose a single `/validate-purchase` endpoint that works for both iOS (StoreKit 2 JWS tokens)
  and Android (Google Play Developer API purchase tokens).

Cloudflare Workers is a natural fit: the validation endpoint runs at the edge, calls Apple or
Google APIs, writes entitlements to D1, and responds in under 200 ms to the mobile client.

---

## Context

**StoreKit 2** (iOS 15+) replaces the old base64 receipt with a signed JWS (JSON Web Signature)
transaction payload. The app receives a `transactionId` and a `jwsRepresentation` string that
can be verified without calling Apple servers, using Apple's public keys from
`https://appleid.apple.com/auth/keys`. For production validation you can additionally call the
App Store Server API (`/inApps/v2/transactions/{transactionId}`) to confirm status and catch
refunds.

**Google Play Billing** uses a `purchaseToken` string. Validation requires calling the Google
Play Developer API (`purchases.subscriptions.get` or `purchases.products.get`) with a service
account JWT, which you generate server-side.

Both flows must happen in Workers, never in the app, because the credentials (App Store Server
API key, Google service account key) must not be bundled with the app binary.

---

## Plugin Setup

```bash
npm install @capacitor-community/in-app-purchases
npx cap sync
```

For `@ionic-enterprise/purchase` (Ionic official, requires license):
```bash
npm install @ionic-enterprise/purchase
npx cap sync
```

iOS — enable In-App Purchase capability in Xcode.
Android — add `com.android.billingclient:billing:7.+` dependency (handled by plugin).

---

## Mobile Client: Initiating a Purchase and Sending to Workers

```typescript
// src/services/purchase.ts
import {
  InAppPurchase,
  ProductType,
  TransactionState,
} from "@capacitor-community/in-app-purchases";
import { Capacitor } from "@capacitor/core";

const WORKERS_BASE = "https://api.example.com";

export interface ValidatedEntitlement {
  productId: string;
  expiresAt: string | null;
  isActive: boolean;
}

export async function purchaseAndValidate(
  productId: string,
  userId: string
): Promise<ValidatedEntitlement> {
  // Step 1: Initiate purchase via native StoreKit / Google Play Billing
  const purchase = await InAppPurchase.purchase({ productId });

  if (purchase.state !== TransactionState.PURCHASED) {
    throw new Error(`Purchase not completed: state=${purchase.state}`);
  }

  const platform = Capacitor.getPlatform();

  // Step 2: Send receipt token to Workers for server-side validation
  const body =
    platform === "ios"
      ? {
          platform: "ios" as const,
          transactionId: purchase.transactionId,
          jwsRepresentation: purchase.receipt, // StoreKit 2 JWS string
          productId,
          userId,
        }
      : {
          platform: "android" as const,
          purchaseToken: purchase.receipt,
          packageName: "com.example.myapp",
          productId,
          userId,
        };

  const resp = await fetch(`${WORKERS_BASE}/purchase/validate`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${await getAccessToken()}`,
    },
    body: JSON.stringify(body),
  });

  if (!resp.ok) {
    const err = await resp.json<{ error: string }>();
    throw new Error(`Validation failed: ${err.error}`);
  }

  const entitlement = await resp.json<ValidatedEntitlement>();

  // Step 3: Finish the transaction on the native side (required to avoid re-delivery)
  await InAppPurchase.finishTransaction({ transactionId: purchase.transactionId });

  return entitlement;
}

async function getAccessToken(): Promise<string> {
  return ""; // retrieve from your auth store
}
```

---

## Workers: Validation Endpoint

```typescript
// workers/src/purchase-validate.ts
import { D1Database } from "@cloudflare/workers-types";

interface Env {
  DB: D1Database;
  APPLE_SHARED_SECRET: string;        // App Store Server API shared secret (legacy) — not needed for JWS
  APPLE_KEY_ID: string;               // App Store Server API private key ID
  APPLE_PRIVATE_KEY: string;          // PEM private key for App Store Server API
  APPLE_ISSUER_ID: string;
  GOOGLE_SERVICE_ACCOUNT_JSON: string; // Stringified service account JSON
  APPLE_BUNDLE_ID: string;
  GOOGLE_PACKAGE_NAME: string;
}

type IosBody = {
  platform: "ios";
  transactionId: string;
  jwsRepresentation: string;
  productId: string;
  userId: string;
};

type AndroidBody = {
  platform: "android";
  purchaseToken: string;
  packageName: string;
  productId: string;
  userId: string;
};

type ValidateBody = IosBody | AndroidBody;

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

    const body = (await request.json()) as ValidateBody;

    let entitlement: { productId: string; expiresAt: string | null; isActive: boolean };

    if (body.platform === "ios") {
      entitlement = await validateAppleTransaction(body, env);
    } else {
      entitlement = await validateGooglePurchase(body, env);
    }

    // Upsert entitlement into D1
    await env.DB.prepare(
      `INSERT INTO entitlements (user_id, product_id, platform, expires_at, is_active, updated_at)
       VALUES (?, ?, ?, ?, ?, datetime('now'))
       ON CONFLICT(user_id, product_id) DO UPDATE SET
         expires_at = excluded.expires_at,
         is_active = excluded.is_active,
         updated_at = excluded.updated_at`
    )
      .bind(body.userId, body.productId, body.platform, entitlement.expiresAt, entitlement.isActive ? 1 : 0)
      .run();

    return Response.json(entitlement);
  },
};

// ── Apple StoreKit 2 JWS verification ──────────────────────────────────────

async function validateAppleTransaction(body: IosBody, env: Env) {
  // 1. Decode JWS header to get kid (key ID)
  const [headerB64] = body.jwsRepresentation.split(".");
  const header = JSON.parse(atob(headerB64.replace(/-/g, "+").replace(/_/g, "/")));

  // 2. Fetch Apple's public keys
  const appleKeys = await fetch("https://appleid.apple.com/auth/keys").then((r) => r.json<{ keys: JsonWebKey[] }>());
  const jwk = appleKeys.keys.find((k) => k.kid === header.kid);
  if (!jwk) throw new Error("Apple key not found");

  // 3. Verify JWS signature using Web Crypto
  const pubKey = await crypto.subtle.importKey("jwk", jwk, { name: "ECDSA", namedCurve: "P-256" }, false, ["verify"]);

  const [headerPart, payloadPart, sigPart] = body.jwsRepresentation.split(".");
  const data = new TextEncoder().encode(`${headerPart}.${payloadPart}`);
  const sig = base64UrlDecode(sigPart);

  const valid = await crypto.subtle.verify({ name: "ECDSA", hash: "SHA-256" }, pubKey, sig, data);
  if (!valid) throw Object.assign(new Error("Invalid JWS signature"), { status: 400 });

  // 4. Parse payload
  const payload = JSON.parse(atob(payloadPart.replace(/-/g, "+").replace(/_/g, "/")));

  if (payload.bundleId !== env.APPLE_BUNDLE_ID) {
    throw Object.assign(new Error("Bundle ID mismatch"), { status: 400 });
  }

  const expiresAt = payload.expiresDate
    ? new Date(payload.expiresDate).toISOString()
    : null;

  return {
    productId: payload.productId as string,
    expiresAt,
    isActive: !expiresAt || new Date(expiresAt) > new Date(),
  };
}

// ── Google Play Developer API validation ───────────────────────────────────

async function validateGooglePurchase(body: AndroidBody, env: Env) {
  const sa = JSON.parse(env.GOOGLE_SERVICE_ACCOUNT_JSON);

  // Mint a Google API access token using service account JWT
  const jwt = await mintGoogleJwt(sa);
  const tokenResp = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: `grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer&assertion=${jwt}`,
  });
  const { access_token } = await tokenResp.json<{ access_token: string }>();

  // Determine if subscription or one-time product
  const isSubscription = body.productId.includes("sub") || body.productId.startsWith("subs");

  const apiPath = isSubscription
    ? `purchases/subscriptionsv2/developers/${body.packageName}/subscriptions/${body.productId}/tokens/${body.purchaseToken}`
    : `purchases/products/${body.productId}/tokens/${body.purchaseToken}`;

  const playResp = await fetch(
    `https://androidpublisher.googleapis.com/androidpublisher/v3/applications/${body.packageName}/${apiPath}`,
    { headers: { Authorization: `Bearer ${access_token}` } }
  );

  if (!playResp.ok) {
    throw Object.assign(new Error(`Google Play API error: ${playResp.status}`), { status: 502 });
  }

  const data = await playResp.json<{ expiryTimeMillis?: string; purchaseState?: number }>();

  const expiresAt = data.expiryTimeMillis
    ? new Date(parseInt(data.expiryTimeMillis)).toISOString()
    : null;

  return {
    productId: body.productId,
    expiresAt,
    isActive: !expiresAt || new Date(expiresAt) > new Date(),
  };
}

// Helpers
function base64UrlDecode(s: string): Uint8Array {
  const b = atob(s.replace(/-/g, "+").replace(/_/g, "/"));
  return new Uint8Array([...b].map((c) => c.charCodeAt(0)));
}

async function mintGoogleJwt(sa: { client_email: string; private_key: string }): Promise<string> {
  const now = Math.floor(Date.now() / 1000);
  const header = { alg: "RS256", typ: "JWT" };
  const payload = {
    iss: sa.client_email,
    scope: "https://www.googleapis.com/auth/androidpublisher",
    aud: "https://oauth2.googleapis.com/token",
    iat: now,
    exp: now + 3600,
  };

  const encode = (o: object) => btoa(JSON.stringify(o)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");
  const sigInput = `${encode(header)}.${encode(payload)}`;

  const keyData = pemToArrayBuffer(sa.private_key);
  const key = await crypto.subtle.importKey(
    "pkcs8", keyData, { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["sign"]
  );

  const sig = await crypto.subtle.sign("RSASSA-PKCS1-v1_5", key, new TextEncoder().encode(sigInput));
  const sigB64 = btoa(String.fromCharCode(...new Uint8Array(sig))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");

  return `${sigInput}.${sigB64}`;
}

function pemToArrayBuffer(pem: string): ArrayBuffer {
  const b64 = pem.replace(/-----[^-]+-----/g, "").replace(/\s/g, "");
  const bin = atob(b64);
  return new Uint8Array([...bin].map((c) => c.charCodeAt(0))).buffer;
}
```

---

## D1 Entitlements Schema

```sql
CREATE TABLE IF NOT EXISTS entitlements (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL,
    product_id  TEXT NOT NULL,
    platform    TEXT NOT NULL CHECK (platform IN ('ios', 'android')),
    expires_at  TEXT,               -- ISO 8601, NULL for lifetime purchases
    is_active   INTEGER NOT NULL DEFAULT 1,
    updated_at  TEXT NOT NULL,
    UNIQUE (user_id, product_id)
);

CREATE INDEX idx_entitlements_user ON entitlements (user_id, is_active);
```

Query active subscriptions for a user:

```sql
SELECT product_id, expires_at
FROM entitlements
WHERE user_id = ? AND is_active = 1
  AND (expires_at IS NULL OR expires_at > datetime('now'));
```

---

## Handling Apple/Google Server Notifications

Configure Apple App Store Server Notifications V2 and Google Play Real-Time Developer
Notifications to POST to a Workers webhook endpoint. On renewal or refund, update the D1 row:

```typescript
// workers/src/purchase-webhook.ts (sketch)
export async function handleAppleNotification(payload: AppleNotificationPayload, env: Env) {
  if (payload.notificationType === "DID_FAIL_TO_RENEW" || payload.notificationType === "REFUND") {
    await env.DB.prepare(
      "UPDATE entitlements SET is_active = 0, updated_at = datetime('now') WHERE product_id = ?"
    ).bind(payload.data.signedTransactionInfo.productId).run();
  }
}
```

---

## Anti-patterns

- **Trusting the client's `isActive` boolean without server validation.** A jailbroken device
  can return `true` for any purchase state. Always validate server-side.
- **Storing the Google service account JSON or Apple private key in KV as a plain string.**
  Use Workers Secrets (`wrangler secret put GOOGLE_SERVICE_ACCOUNT_JSON`) so the value is
  encrypted at rest and not visible in the dashboard.
- **Calling `finishTransaction` before server validation succeeds.** If Workers is unreachable,
  you finish the transaction on-device and lose the ability to re-validate. Only call finish
  after a successful 2xx response from the validation endpoint.
- **Fetching Apple JWK public keys on every request.** Cache the key set in the Workers cache
  API (`caches.default`) for at least 1 hour — Apple rotates keys infrequently.
- **Not handling idempotency.** The same `purchaseToken` or `transactionId` can arrive more
  than once (retries, app restarts). Use `ON CONFLICT DO UPDATE` in D1 (as shown) rather than
  `INSERT` to avoid duplicate entitlement rows.

---

## Gotchas

- StoreKit 2 JWS uses ES256 (ECDSA P-256). The Web Crypto API supports this natively in
  Workers — no external library required.
- Google's `purchases/subscriptionsv2` endpoint replaces the deprecated
  `purchases/subscriptions` endpoint. Use v2 for new integrations.
- The Google service account must have the `Android Publisher` role in Google Play Console —
  a generic GCP IAM role is not sufficient.
- On Android, `finishTransaction` in the Capacitor plugin maps to `acknowledgePurchase` in
  Google Play Billing. Unacknowledged purchases are refunded by Google after 3 days.
- Apple's sandbox environment uses `https://api.storekit-sandbox.itunes.apple.com`; production
  uses `https://api.storekit.itunes.apple.com`. JWS verification uses the same public keys
  for both — but the `environment` field in the JWS payload will say `Sandbox`.

---

## Verification

```bash
# Trigger a StoreKit sandbox purchase and check D1
wrangler d1 execute my-db --command \
  "SELECT user_id, product_id, platform, is_active, expires_at FROM entitlements ORDER BY updated_at DESC LIMIT 10"

# Manually test the validation endpoint with a sandbox JWS
curl -X POST https://api.example.com/purchase/validate \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"platform":"ios","transactionId":"1234","jwsRepresentation":"<jws>","productId":"pro_monthly","userId":"user_abc"}'
```

---

## Related

- `ios-storekit2-workers-receipt-validation.md` — iOS-only StoreKit 2 deep-dive
- `android-in-app-billing.md` — Android billing fundamentals
- `ios-in-app-purchase.md` — iOS purchase flows
- `capacitor-native-bridge-plugin-development.md` — building Capacitor native bridge plugins
- `mobile-digital-wallets-apple-pay-google-pay.md` — payment method integration

---

## Sources

- https://developer.apple.com/documentation/appstoreserverapi
- https://developer.apple.com/documentation/storekit/in-app_purchase/original_api_for_in-app_purchase/validating_receipts_with_the_app_store
- https://developers.google.com/android-publisher/api-ref/rest/v3/purchases.subscriptionsv2
- https://github.com/capacitor-community/in-app-purchases
- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
