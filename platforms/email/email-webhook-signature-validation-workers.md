# ESP Webhook Signature Validation in Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Forged webhook payloads from malicious actors can inject fake bounce or complaint events, corrupting suppression lists and disabling real subscriber addresses. HMAC signature validation at the Worker layer ensures only payloads from the configured ESP are processed.

## Context
SendGrid, Mailgun, and Postmark each sign their webhook payloads differently. A single Cloudflare Worker can validate all three using the Web Crypto `SubtleCrypto` API, which is available natively in the Workers runtime without any external library. Secrets are stored in Workers Secrets (environment variables) and never appear in source code.

## SendGrid Event Webhook Validation

SendGrid signs payloads with ECDSA P-256. The public key is provided in the SendGrid dashboard under Mail Settings → Event Webhook.

```typescript
async function validateSendGrid(
  request: Request,
  publicKeyPem: string
): Promise<boolean> {
  const signature = request.headers.get("X-Twilio-Email-Event-Webhook-Signature") ?? "";
  const timestamp = request.headers.get("X-Twilio-Email-Event-Webhook-Timestamp") ?? "";
  const body = await request.text();

  const pemBody = publicKeyPem
    .replace(/-----BEGIN PUBLIC KEY-----/, "")
    .replace(/-----END PUBLIC KEY-----/, "")
    .replace(/\s/g, "");
  const keyBytes = Uint8Array.from(atob(pemBody), (c) => c.charCodeAt(0));

  const key = await crypto.subtle.importKey(
    "spki",
    keyBytes.buffer,
    { name: "ECDSA", namedCurve: "P-256" },
    false,
    ["verify"]
  );

  const sigBytes = Uint8Array.from(atob(signature), (c) => c.charCodeAt(0));
  const payload = new TextEncoder().encode(timestamp + body);

  return crypto.subtle.verify({ name: "ECDSA", hash: "SHA-256" }, key, sigBytes, payload);
}
```

## Mailgun Webhook Validation

Mailgun uses HMAC-SHA256 over `timestamp + token` with the webhook signing key.

```typescript
async function validateMailgun(
  timestamp: string,
  token: string,
  signature: string,
  signingKey: string
): Promise<boolean> {
  const keyMaterial = new TextEncoder().encode(signingKey);
  const hmacKey = await crypto.subtle.importKey(
    "raw",
    keyMaterial,
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );

  const message = new TextEncoder().encode(timestamp + token);
  const mac = await crypto.subtle.sign("HMAC", hmacKey, message);
  const computed = Array.from(new Uint8Array(mac))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");

  // Constant-time comparison using HMAC trick
  const expectedKey = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode("constant-time"),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const [a, b] = await Promise.all([
    crypto.subtle.sign("HMAC", expectedKey, new TextEncoder().encode(computed)),
    crypto.subtle.sign("HMAC", expectedKey, new TextEncoder().encode(signature)),
  ]);
  return btoa(String.fromCharCode(...new Uint8Array(a))) ===
    btoa(String.fromCharCode(...new Uint8Array(b)));
}
```

## Postmark Webhook Validation

Postmark does not sign payloads with HMAC; instead it uses HTTP Basic Auth with a per-stream username/password pair configured in the Postmark dashboard. Validate credentials from the `Authorization` header.

```typescript
function validatePostmark(request: Request, expectedToken: string): boolean {
  const authHeader = request.headers.get("Authorization") ?? "";
  if (!authHeader.startsWith("Basic ")) return false;
  const decoded = atob(authHeader.slice(6));
  // Postmark uses "webhook-username:webhook-password" format
  const [, password] = decoded.split(":");
  // Constant-time comparison via encoding both values
  const enc = new TextEncoder();
  const a = enc.encode(password.padEnd(64, "\0").slice(0, 64));
  const b = enc.encode(expectedToken.padEnd(64, "\0").slice(0, 64));
  // XOR-based equality check to avoid short-circuit
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a[i] ^ b[i];
  return diff === 0;
}
```

## Unified Router Worker

A single Worker routes incoming webhook payloads to the correct validator based on the URL path, then dispatches to shared event-processing logic.

```typescript
export interface Env {
  SENDGRID_PUBLIC_KEY: string;  // PEM-encoded ECDSA public key
  MAILGUN_SIGNING_KEY: string;
  POSTMARK_WEBHOOK_TOKEN: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    let valid = false;

    if (url.pathname === "/webhooks/sendgrid") {
      const cloned = request.clone();
      valid = await validateSendGrid(cloned, env.SENDGRID_PUBLIC_KEY);
    } else if (url.pathname === "/webhooks/mailgun") {
      const body = await request.json<{ signature: { timestamp: string; token: string; signature: string } }>();
      const { timestamp, token, signature } = body.signature;
      valid = await validateMailgun(timestamp, token, signature, env.MAILGUN_SIGNING_KEY);
    } else if (url.pathname === "/webhooks/postmark") {
      valid = validatePostmark(request, env.POSTMARK_WEBHOOK_TOKEN);
    } else {
      return new Response("Not Found", { status: 404 });
    }

    if (!valid) {
      return new Response("Forbidden", { status: 403 });
    }

    // Dispatch to shared event processing…
    return new Response("OK", { status: 200 });
  },
};
```

## Replay Attack Prevention

ESP webhooks may be replayed by attackers capturing valid requests. Reject payloads whose timestamp is older than a tolerance window.

```typescript
function isTimestampFresh(timestampSeconds: string, toleranceSeconds = 300): boolean {
  const ts = parseInt(timestampSeconds, 10);
  if (isNaN(ts)) return false;
  const ageSeconds = Math.floor(Date.now() / 1000) - ts;
  return ageSeconds >= 0 && ageSeconds <= toleranceSeconds;
}
```

## Anti-patterns
- Logging or echoing the raw signing key in error messages
- Using string equality (`===`) for HMAC comparison — vulnerable to timing attacks
- Skipping signature validation in staging environments where the signing key is "not configured"
- Re-reading the request body after `request.text()` without cloning first — the stream is consumed

## Gotchas
- `request.text()` consumes the body; clone the request before validation if the body is also needed for parsing
- SendGrid rotates its signing key periodically; subscribe to SendGrid changelog notifications
- Cloudflare Workers Secrets are not visible in plain text after creation; store the raw PEM or hex key as-is
- Mailgun's `token` field changes per-event and must be stored in KV for deduplication if idempotency is required

## Verification
1. Send a valid signed POST to `/webhooks/sendgrid` — expect HTTP 200
2. Tamper with the `X-Twilio-Email-Event-Webhook-Signature` header — expect HTTP 403
3. Replay the same valid SendGrid request 10 minutes later — confirm it is rejected if timestamp freshness check is active
4. Send an unsigned POST directly — confirm 403 is returned immediately

## Related
- `/documentation/categories/email/email-webhook-idempotency-deduplication.md`
- `/documentation/categories/email/sendgrid-event-webhook.md`
- `/documentation/categories/email/ses-bounce-complaint-webhooks.md`
- `/documentation/categories/email/inbound-webhook-workers-d1.md`

## Sources
- SendGrid Event Webhook Security: https://docs.sendgrid.com/for-developers/tracking-events/getting-started-event-webhook-security-features
- Mailgun Webhook Signing: https://documentation.mailgun.com/docs/mailgun/user-manual/webhooks/#securing-webhooks
- Web Crypto API — SubtleCrypto: https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto
- Cloudflare Workers Secrets: https://developers.cloudflare.com/workers/configuration/secrets/
