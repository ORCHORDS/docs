# Google Pay Payment Token Decryption in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Google Pay returns an encrypted `PaymentMethodData` token when the user authorizes a payment. Your backend must decrypt the `encryptedMessage` field to access the raw PAN, expiry, and cryptogram before submitting to an acquirer. Running this decryption in a Cloudflare Worker keeps the private key server-side and avoids standing up a dedicated decryption microservice.

---

## Context

Google Pay uses an ECDH-based hybrid encryption scheme (ECv2): the token contains an ephemeral EC public key, a MAC, and an AES-256-CTR-encrypted message. Decryption requires your merchant EC private key (stored as a Workers Secret in PKCS8 PEM form), an ECDH key agreement with the ephemeral key, HKDF derivation of symmetric keys, AES-256-CTR decryption of `encryptedMessage`, and HMAC-SHA256 verification of the MAC. The Web Crypto API available in Workers supports all of these primitives natively—no npm crypto library is needed. Decryption audit events (token ID, masked PAN, timestamp) are written to a D1 table for PCI compliance.

---

## Section 1 — D1 Schema

```sql
CREATE TABLE IF NOT EXISTS decryption_audit (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  message_id  TEXT    NOT NULL UNIQUE,  -- Google Pay message_id field
  masked_pan  TEXT    NOT NULL,         -- last 4 digits only
  network     TEXT    NOT NULL,
  decrypted_at TEXT   NOT NULL,         -- ISO-8601
  worker_ray  TEXT                      -- CF-Ray header for tracing
);

CREATE INDEX IF NOT EXISTS idx_audit_message_id ON decryption_audit(message_id);
```

Apply via:

```bash
wrangler d1 execute gpay-audit --file schema.sql
```

---

## Section 2 — Worker Implementation

```typescript
export interface Env {
  DB: D1Database;
  GOOGLE_PAY_PRIVATE_KEY_PEM: string; // Workers Secret (PKCS8 PEM, no headers)
  GOOGLE_PAY_RECIPIENT_ID: string;    // e.g. "merchant:yoursite.com"
}

// ----- Key helpers -----

function pemToDer(pem: string): ArrayBuffer {
  const b64 = pem
    .replace(/-----BEGIN [^-]+-----|-----END [^-]+-----/g, "")
    .replace(/\s/g, "");
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}

async function importMerchantPrivateKey(pem: string): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    "pkcs8",
    pemToDer(pem),
    { name: "ECDH", namedCurve: "P-256" },
    false,
    ["deriveKey", "deriveBits"]
  );
}

async function importEphemeralPublicKey(base64: string): Promise<CryptoKey> {
  const der = Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));
  return crypto.subtle.importKey(
    "raw",
    der,
    { name: "ECDH", namedCurve: "P-256" },
    false,
    []
  );
}

// ----- HKDF derivation -----

async function hkdfDeriveKeys(
  sharedSecret: ArrayBuffer,
  info: string
): Promise<{ encKey: CryptoKey; macKey: CryptoKey }> {
  const ikm = await crypto.subtle.importKey(
    "raw",
    sharedSecret,
    { name: "HKDF" },
    false,
    ["deriveKey", "deriveBits"]
  );

  const encoder = new TextEncoder();

  // Derive 512 bits: first 256 for AES key, next 256 for HMAC key
  const bits = await crypto.subtle.deriveBits(
    {
      name: "HKDF",
      hash: "SHA-256",
      salt: new Uint8Array(32), // zero salt per Google spec
      info: encoder.encode(info),
    },
    ikm,
    512
  );

  const encKeyRaw = bits.slice(0, 32);
  const macKeyRaw = bits.slice(32, 64);

  const encKey = await crypto.subtle.importKey(
    "raw",
    encKeyRaw,
    { name: "AES-CTR" },
    false,
    ["decrypt"]
  );

  const macKey = await crypto.subtle.importKey(
    "raw",
    macKeyRaw,
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["verify"]
  );

  return { encKey, macKey };
}

// ----- Decryption core -----

interface GooglePayToken {
  signature: string;
  intermediateSigningKey?: unknown;
  protocolVersion: string;
  signedMessage: string;
}

interface SignedMessage {
  encryptedMessage: string;
  ephemeralPublicKey: string;
  tag: string;
}

interface DecryptedPayload {
  messageId: string;
  messageExpiration: string;
  paymentMethod: string;
  paymentMethodDetails: {
    pan: string;
    expirationMonth: number;
    expirationYear: number;
    authMethod: string;
    cryptogram?: string;
    eciIndicator?: string;
  };
}

async function decryptGooglePayToken(
  token: GooglePayToken,
  privateKey: CryptoKey,
  recipientId: string
): Promise<DecryptedPayload> {
  if (token.protocolVersion !== "ECv2") {
    throw new Error(`Unsupported protocol: ${token.protocolVersion}`);
  }

  const signedMessage: SignedMessage = JSON.parse(token.signedMessage);
  const ephemeralKey = await importEphemeralPublicKey(
    signedMessage.ephemeralPublicKey
  );

  // ECDH shared secret
  const sharedSecretBits = await crypto.subtle.deriveBits(
    { name: "ECDH", public: ephemeralKey },
    privateKey,
    256
  );

  // HKDF info string per Google ECv2 spec
  const hkdfInfo = `Google Pay ECv2:${recipientId}`;
  const { encKey, macKey } = await hkdfDeriveKeys(sharedSecretBits, hkdfInfo);

  // Verify HMAC-SHA256 tag
  const encryptedMessageBytes = Uint8Array.from(
    atob(signedMessage.encryptedMessage),
    (c) => c.charCodeAt(0)
  );
  const tagBytes = Uint8Array.from(
    atob(signedMessage.tag),
    (c) => c.charCodeAt(0)
  );

  const tagValid = await crypto.subtle.verify(
    { name: "HMAC", hash: "SHA-256" },
    macKey,
    tagBytes,
    encryptedMessageBytes
  );
  if (!tagValid) throw new Error("Google Pay MAC verification failed");

  // AES-256-CTR decrypt (counter = 64-bit big-endian 0)
  const counter = new Uint8Array(16); // all zeros
  const plaintext = await crypto.subtle.decrypt(
    { name: "AES-CTR", counter, length: 128 },
    encKey,
    encryptedMessageBytes
  );

  return JSON.parse(new TextDecoder().decode(plaintext)) as DecryptedPayload;
}

// ----- Audit log -----

async function logAudit(
  db: D1Database,
  payload: DecryptedPayload,
  ray: string
): Promise<void> {
  const pan = payload.paymentMethodDetails.pan;
  const masked = `****${pan.slice(-4)}`;
  await db
    .prepare(
      `INSERT OR IGNORE INTO decryption_audit
       (message_id, masked_pan, network, decrypted_at, worker_ray)
       VALUES (?, ?, ?, ?, ?)`
    )
    .bind(
      payload.messageId,
      masked,
      payload.paymentMethodDetails.authMethod,
      new Date().toISOString(),
      ray
    )
    .run();
}

// ----- Fetch handler -----

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    if (request.method !== "POST" || new URL(request.url).pathname !== "/googlepay/decrypt") {
      return new Response("Not Found", { status: 404 });
    }

    let token: GooglePayToken;
    try {
      token = await request.json<GooglePayToken>();
    } catch {
      return new Response(JSON.stringify({ error: "Invalid JSON" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
    }

    const privateKey = await importMerchantPrivateKey(env.GOOGLE_PAY_PRIVATE_KEY_PEM);

    let payload: DecryptedPayload;
    try {
      payload = await decryptGooglePayToken(token, privateKey, env.GOOGLE_PAY_RECIPIENT_ID);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Decryption failed";
      return new Response(JSON.stringify({ error: msg }), {
        status: 422,
        headers: { "Content-Type": "application/json" },
      });
    }

    const ray = request.headers.get("CF-Ray") ?? "unknown";
    ctx.waitUntil(logAudit(env.DB, payload, ray));

    return new Response(
      JSON.stringify({
        pan: payload.paymentMethodDetails.pan,
        expirationMonth: payload.paymentMethodDetails.expirationMonth,
        expirationYear: payload.paymentMethodDetails.expirationYear,
        cryptogram: payload.paymentMethodDetails.cryptogram,
        authMethod: payload.paymentMethodDetails.authMethod,
      }),
      { headers: { "Content-Type": "application/json" } }
    );
  },
};
```

---

## Section 3 — Secret Setup

```bash
# Export your PKCS8 private key as base64 PEM, strip headers, set as secret
wrangler secret put GOOGLE_PAY_PRIVATE_KEY_PEM
# Paste the PEM content (with -----BEGIN/END----- headers included) when prompted

wrangler secret put GOOGLE_PAY_RECIPIENT_ID
# e.g. merchant:yourdomain.com

# Create D1 database
wrangler d1 create gpay-audit

# Apply schema
wrangler d1 execute gpay-audit --file schema.sql

# Deploy
wrangler deploy
```

---

## Anti-patterns

- **Using Node.js `crypto` module** — Workers use the Web Crypto API (`crypto.subtle`); Node crypto is not available. Use `importKey`, `deriveBits`, and `decrypt` directly.
- **Skipping MAC verification** — Decrypting without verifying the HMAC tag first allows attackers to feed crafted ciphertext and observe error oracles. Always verify before decrypting.
- **Logging the full PAN to D1** — Store only the last 4 digits (`masked_pan`) for PCI DSS compliance. Never persist the full PAN beyond the in-memory decryption result.
- **Reusing key derivation across tokens** — Each Google Pay token carries its own ephemeral public key. Never cache the derived AES/HMAC keys between requests.

---

## Gotchas

- Google Pay ECv2 uses a zero (all-0x00) 32-byte HKDF salt, not an empty byte sequence. Passing an empty `Uint8Array(0)` produces wrong keys.
- The AES-CTR counter in Web Crypto is the full 128-bit block. Google Pay specifies a 64-bit counter starting at 0, which maps to the first 8 bytes set to 0 and the last 8 bytes as the counter—use `new Uint8Array(16)` (all zeros) with `length: 128`.
- `INSERT OR IGNORE` in the audit log prevents double-logging if the Worker retries due to a transient D1 write failure while the payment actually succeeded.
- `messageExpiration` in the decrypted payload is a Unix timestamp (milliseconds). Validate it before forwarding to your acquirer to reject replayed tokens.
- The `GOOGLE_PAY_PRIVATE_KEY_PEM` secret must be the leaf merchant key, not the intermediate Google signing key.

---

## Verification

```bash
# Generate a test token with the Google Pay test environment
# (set your payment environment to TEST in the Google Pay API)
curl -X POST https://<worker>.workers.dev/googlepay/decrypt \
  -H "Content-Type: application/json" \
  -d @test_token.json

# Check audit log in D1
wrangler d1 execute gpay-audit \
  --command "SELECT * FROM decryption_audit ORDER BY id DESC LIMIT 5"
```

---

## Related

- `workers-apple-pay-payment-session.md`
- `stripe-checkout-session-workers-d1.md`
- `workers-paypal-webhook-verification.md`

---

## Sources

- Google Pay Encryption — https://developers.google.com/pay/api/web/guides/resources/payment-data-cryptography
- Web Crypto API — https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto
- Cloudflare Workers Secrets — https://developers.cloudflare.com/workers/configuration/secrets/
- Cloudflare D1 — https://developers.cloudflare.com/d1/
