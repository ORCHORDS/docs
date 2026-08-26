# Webhook Signature Verification Pattern

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A Worker receives webhooks from Stripe, GitHub, Shopify, or an internal publisher and
processes them to update database rows or trigger downstream actions. Without
signature verification, any actor on the internet can send forged payloads to your
endpoint — fabricating payment confirmations, fake commit events, or inventory
changes. A replay attack can also re-trigger an event that was already processed.

The fix is to verify a HMAC-SHA256 signature included in the request header before
touching any payload data, and to reject requests that fall outside a short timestamp
window to defeat replays.

## Context

Nearly every webhook provider signs payloads with HMAC-SHA256 using a shared secret:

| Provider | Header | Body encoding |
|----------|--------|---------------|
| Stripe | `Stripe-Signature` | Raw bytes (`t=`, `v1=` format) |
| GitHub | `X-Hub-Signature-256` | `sha256=<hex>` |
| Shopify | `X-Shopify-Hmac-Sha256` | Base64 |
| Svix / custom | `webhook-signature` | `v1,<base64>` |
| PagerDuty | `X-PagerDuty-Signature` | `v1=<hex>` |

The Workers `crypto.subtle` API exposes native HMAC-SHA256 without external
dependencies. Always read the raw body as `ArrayBuffer` or `text` _before_ parsing
JSON, because signature verification must operate on the exact bytes transmitted.

## Generic HMAC-SHA256 Verifier

```typescript
// webhook-verify.ts
export interface VerifyOptions {
  /** The raw shared secret string or bytes from the provider dashboard. */
  secret:    string;
  /** The signature value from the incoming request header (after stripping prefix). */
  signature: string;
  /** Encoding of the incoming signature: 'hex' | 'base64'. */
  encoding:  "hex" | "base64";
  /** The exact body bytes the provider signed. */
  body:      string | ArrayBuffer;
}

async function importKey(secret: string): Promise<CryptoKey> {
  const enc = new TextEncoder();
  return crypto.subtle.importKey(
    "raw",
    enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign", "verify"]
  );
}

function hexToBytes(hex: string): Uint8Array {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < hex.length; i += 2) {
    bytes[i / 2] = parseInt(hex.slice(i, i + 2), 16);
  }
  return bytes;
}

export async function verifyHmac(opts: VerifyOptions): Promise<boolean> {
  const key = await importKey(opts.secret);

  const expectedBytes =
    opts.encoding === "hex"
      ? hexToBytes(opts.signature)
      : Uint8Array.from(atob(opts.signature), c => c.charCodeAt(0));

  const bodyBuffer =
    typeof opts.body === "string"
      ? new TextEncoder().encode(opts.body)
      : new Uint8Array(opts.body);

  return crypto.subtle.verify("HMAC", key, expectedBytes, bodyBuffer);
}

/** Constant-time comparison (redundant when using crypto.subtle.verify, but explicit). */
export function safeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) {
    diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return diff === 0;
}
```

## Provider-specific Adapters

```typescript
// adapters/stripe.ts
import { verifyHmac } from "../webhook-verify";

/**
 * Stripe sends: Stripe-Signature: t=1614556800,v1=<hex>,v0=<hex>
 * The signed payload is: `${timestamp}.${rawBody}`
 */
export async function verifyStripe(
  request:  Request,
  rawBody:  string,
  secret:   string,
  maxAgeMs: number = 300_000   // 5-minute replay window
): Promise<void> {
  const header = request.headers.get("stripe-signature") ?? "";
  const parts  = Object.fromEntries(
    header.split(",").map(p => p.split("=") as [string, string])
  );

  const timestamp = parseInt(parts["t"] ?? "0", 10);
  const v1sig     = parts["v1"] ?? "";

  if (!timestamp || !v1sig) {
    throw new Response("Missing Stripe-Signature components", { status: 400 });
  }

  const age = Date.now() - timestamp * 1000;
  if (age > maxAgeMs) {
    throw new Response("Webhook timestamp too old (replay?)", { status: 400 });
  }

  const signedPayload = `${timestamp}.${rawBody}`;
  const valid = await verifyHmac({
    secret,
    signature: v1sig,
    encoding:  "hex",
    body:      signedPayload,
  });

  if (!valid) throw new Response("Invalid Stripe signature", { status: 401 });
}

// adapters/github.ts
import { verifyHmac } from "../webhook-verify";

/**
 * GitHub sends: X-Hub-Signature-256: sha256=<hex>
 */
export async function verifyGitHub(
  request: Request,
  rawBody: string,
  secret:  string
): Promise<void> {
  const header = request.headers.get("x-hub-signature-256") ?? "";
  const sig    = header.startsWith("sha256=") ? header.slice(7) : "";

  if (!sig) throw new Response("Missing X-Hub-Signature-256", { status: 400 });

  const valid = await verifyHmac({ secret, signature: sig, encoding: "hex", body: rawBody });
  if (!valid) throw new Response("Invalid GitHub signature", { status: 401 });
}

// adapters/shopify.ts
import { verifyHmac } from "../webhook-verify";

/**
 * Shopify sends: X-Shopify-Hmac-Sha256: <base64>
 */
export async function verifyShopify(
  request: Request,
  rawBody: string,
  secret:  string
): Promise<void> {
  const sig = request.headers.get("x-shopify-hmac-sha256") ?? "";
  if (!sig) throw new Response("Missing Shopify signature header", { status: 400 });

  const valid = await verifyHmac({ secret, signature: sig, encoding: "base64", body: rawBody });
  if (!valid) throw new Response("Invalid Shopify signature", { status: 401 });
}
```

## Putting It All Together in a Worker

```typescript
// worker.ts
import { verifyStripe }  from "./adapters/stripe";
import { verifyGitHub }  from "./adapters/github";
import { verifyShopify } from "./adapters/shopify";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method not allowed", { status: 405 });
    }

    // IMPORTANT: read raw body BEFORE any JSON.parse
    const rawBody = await request.text();

    const url      = new URL(request.url);
    const provider = url.pathname.split("/")[2]; // /webhooks/{provider}

    try {
      switch (provider) {
        case "stripe":
          await verifyStripe(request, rawBody, env.STRIPE_WEBHOOK_SECRET);
          break;
        case "github":
          await verifyGitHub(request, rawBody, env.GITHUB_WEBHOOK_SECRET);
          break;
        case "shopify":
          await verifyShopify(request, rawBody, env.SHOPIFY_WEBHOOK_SECRET);
          break;
        default:
          return new Response("Unknown provider", { status: 404 });
      }
    } catch (errResponse) {
      if (errResponse instanceof Response) return errResponse;
      throw errResponse;
    }

    // Signature verified — safe to parse and process
    const event = JSON.parse(rawBody);
    await processEvent(env, provider, event);

    return new Response(null, { status: 204 });
  },
};

async function processEvent(env: Env, provider: string, event: unknown): Promise<void> {
  // Route to provider-specific handler
  await env.EVENT_QUEUE.send({ provider, event });
}
```

## Anti-patterns

- **Parsing JSON before verification**: `request.json()` consumes the body; you cannot
  then read it as raw bytes for HMAC. Always call `request.text()` or
  `request.arrayBuffer()` first, then `JSON.parse(rawBody)` after verification.
- **String comparison with `===`**: timing side-channels can leak signature length.
  Always use `crypto.subtle.verify` or a constant-time compare. `crypto.subtle.verify`
  internally uses a constant-time comparison in the runtime.
- **Ignoring the timestamp / replay window**: without a replay check, an attacker who
  captures a valid signed request can resubmit it minutes or hours later.
- **Logging the raw body containing PII before verification**: if the payload contains
  card numbers or PII and your log pipeline is compromised, you leak data. Log only
  after verification and only non-sensitive fields.
- **Storing webhook secrets in Worker environment variables checked into source**:
  use Cloudflare Secrets (`wrangler secret put`) so secrets are encrypted at rest and
  never visible in wrangler.toml or source history.

## Gotchas

- **Stripe double-hashing**: Stripe's `t=…,v1=…` format signs `${t}.${body}`, not
  just `body`. Forgetting the timestamp prefix causes every verification to fail.
- **Body encoding sensitivity**: some providers sign the JSON with specific
  whitespace; do not re-serialize or pretty-print before signing. Preserve exact bytes.
- **Base64 variants**: Shopify uses standard Base64; some providers use URL-safe
  Base64 (`-` and `_` instead of `+` and `/`). Use the correct `atob`/`Buffer`
  variant or decoding will produce wrong bytes.
- **Secret rotation**: when rotating secrets, accept both old and new signature
  during a brief overlap window. Stripe's `v0`/`v1` multi-signature header is
  designed for exactly this.
- **`crypto.subtle` is async**: the `importKey` and `verify` calls return Promises.
  Forgetting `await` gives you a Promise that is always truthy — every signature
  appears valid. Always await.

## Verification

```bash
# Generate a test Stripe signature and POST it to the Worker
SECRET="whsec_test123"
BODY='{"id":"evt_test","type":"payment_intent.succeeded"}'
TS=$(date +%s)
SIGNED_PAYLOAD="${TS}.${BODY}"
SIG=$(echo -n "${SIGNED_PAYLOAD}" | openssl dgst -sha256 -hmac "${SECRET}" | awk '{print $2}')

curl -X POST https://your-worker.dev/webhooks/stripe \
  -H "Stripe-Signature: t=${TS},v1=${SIG}" \
  -H "Content-Type: application/json" \
  -d "${BODY}"
# Expected: 204 No Content

# Test replay rejection: use a timestamp older than 5 minutes
OLD_TS=$(($(date +%s) - 400))
curl -X POST https://your-worker.dev/webhooks/stripe \
  -H "Stripe-Signature: t=${OLD_TS},v1=${SIG}" \
  -H "Content-Type: application/json" \
  -d "${BODY}"
# Expected: 400 Webhook timestamp too old
```

## Related

- `webhook-implementation.md` — end-to-end webhook delivery setup
- `webhook-reliability.md` — retry queues and delivery guarantees
- `idempotency-key-pattern-workers-d1.md` — deduplicate replayed events at DB layer
- `secure-defaults.md` — security hardening checklist for Workers
- `scim-bearer-token-auth.md` — bearer-token auth (alternative for internal webhooks)

## Sources

- Stripe webhook signature verification
  https://stripe.com/docs/webhooks#verify-official-libraries
- GitHub webhook security
  https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries
- Shopify HMAC verification
  https://shopify.dev/docs/apps/build/webhooks/secure/validate-webhooks
- Web Crypto API (HMAC) — MDN
  https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/verify
- Cloudflare Workers Secrets
  https://developers.cloudflare.com/workers/configuration/secrets/
