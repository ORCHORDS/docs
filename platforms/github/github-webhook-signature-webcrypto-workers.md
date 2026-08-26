# GitHub Webhook Signature Verification in Cloudflare Workers via WebCrypto

2026-08-24 / example.com / production

---

## Symptom / Use-case

A Cloudflare Worker receives GitHub webhook payloads and must reject any request not signed by
GitHub before acting on it. Node.js projects use `crypto.createHmac`; Cloudflare Workers have no
Node.js `crypto` module by default — they expose the Web Crypto API (`crypto.subtle`). Using an
npm polyfill or enabling Node.js compat mode just for HMAC verification is unnecessary overhead.
This article covers a native WebCrypto implementation with timing-safe comparison, constant-time
header parsing, and early rejection of malformed requests.

## Context

GitHub signs every webhook payload with HMAC-SHA256 using the secret you configured when
registering the webhook. The signature is sent in the `X-Hub-Signature-256` header as
`sha256=<hex-digest>`. The canonical verification flow is:

1. Read the raw request body as `ArrayBuffer` (do not parse as JSON first).
2. Import the webhook secret as a `CryptoKey` with the `HMAC` algorithm.
3. Sign the body with `crypto.subtle.sign`.
4. Compare the result with the hex digest from the header using a timing-safe comparison.

Workers' `crypto.subtle` follows the W3C Web Crypto spec exactly. The subtlety is that
`crypto.subtle.verify` for `HMAC` does a timing-safe comparison internally, which is preferable
to a JS-level byte loop. If you need a custom hex comparison, you must implement it in constant
time yourself.

```
GitHub ──► POST /webhook  HTTP/1.1
            X-Hub-Signature-256: sha256=abc123...
            Content-Type: application/json
            Body: { "action": "opened", ... }

Worker:
  1. body = await request.arrayBuffer()
  2. key  = importKey(WEBHOOK_SECRET, "HMAC", "SHA-256")
  3. sig  = await subtle.sign("HMAC", key, body)
  4. hexOf(sig) == header[7:]  ← timing-safe via subtle.verify
```

## Code

### Core verification helper — pure WebCrypto

```typescript
// src/github/verify-signature.ts

/**
 * Verifies a GitHub webhook signature.
 * Returns true if the X-Hub-Signature-256 header matches the body HMAC.
 */
export async function verifyGitHubWebhookSignature(
  request: Request,
  secret: string,
): Promise<{ valid: boolean; body: ArrayBuffer }> {
  const signatureHeader = request.headers.get("X-Hub-Signature-256");
  if (!signatureHeader || !signatureHeader.startsWith("sha256=")) {
    return { valid: false, body: new ArrayBuffer(0) };
  }

  // Read body once; clone is needed because request body is a ReadableStream
  const body = await request.arrayBuffer();

  const expectedHex = signatureHeader.slice(7); // strip "sha256="
  const expectedBytes = hexToBytes(expectedHex);
  if (!expectedBytes) return { valid: false, body };

  // Import the secret as an HMAC key
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["verify"],
  );

  // crypto.subtle.verify performs a timing-safe comparison
  const valid = await crypto.subtle.verify("HMAC", key, expectedBytes, body);

  return { valid, body };
}

/** Convert a hex string to Uint8Array; returns null on invalid hex. */
function hexToBytes(hex: string): Uint8Array | null {
  if (hex.length % 2 !== 0) return null;
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < bytes.length; i++) {
    const byte = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
    if (isNaN(byte)) return null;
    bytes[i] = byte;
  }
  return bytes;
}
```

### Worker entry-point with signature gate

```typescript
// src/index.ts
import { verifyGitHubWebhookSignature } from "./github/verify-signature";

interface Env {
  WEBHOOK_SECRET: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    // Verify signature before any other processing
    const { valid, body } = await verifyGitHubWebhookSignature(request, env.WEBHOOK_SECRET);
    if (!valid) {
      // Return 401 with a generic message to avoid leaking info
      return new Response("Unauthorized", { status: 401 });
    }

    const event = request.headers.get("X-GitHub-Event") ?? "unknown";
    const deliveryId = request.headers.get("X-GitHub-Delivery") ?? "unknown";

    const payload = JSON.parse(new TextDecoder().decode(body));

    // Dispatch by event type
    switch (event) {
      case "push":
        await handlePush(payload, env);
        break;
      case "pull_request":
        await handlePullRequest(payload, env);
        break;
      default:
        // Accept but ignore unknown events
        break;
    }

    return new Response(JSON.stringify({ ok: true, delivery: deliveryId }), {
      headers: { "Content-Type": "application/json" },
    });
  },
};

async function handlePush(payload: Record<string, unknown>, _env: Env): Promise<void> {
  console.log("push event on", payload.ref);
}

async function handlePullRequest(payload: Record<string, unknown>, _env: Env): Promise<void> {
  console.log("PR action:", payload.action);
}
```

### Wrangler configuration

```toml
# wrangler.toml
name = "github-webhook-handler"
main = "src/index.ts"
compatibility_date = "2026-08-01"

# Set WEBHOOK_SECRET as a secret — never in [vars]
# wrangler secret put WEBHOOK_SECRET
```

### GitHub Actions — register the webhook programmatically on deploy

```yaml
# .github/workflows/register-webhook.yml
name: Register GitHub Webhook

on:
  workflow_dispatch:
    inputs:
      worker_url:
        description: "URL of the deployed Worker"
        required: true

permissions:
  contents: read

jobs:
  register:
    runs-on: ubuntu-latest
    steps:
      - name: Create or update webhook
        env:
          GH_TOKEN: ${{ secrets.GH_APP_TOKEN }}
          WEBHOOK_SECRET: ${{ secrets.WEBHOOK_SECRET }}
        run: |
          gh api \
            --method POST \
            /repos/${{ github.repository }}/hooks \
            --field name=web \
            --field active=true \
            --field 'events[]=push' \
            --field 'events[]=pull_request' \
            --field 'config[url]=${{ inputs.worker_url }}' \
            --field 'config[content_type]=json' \
            --field "config[secret]=$WEBHOOK_SECRET" \
            --field 'config[insecure_ssl]=0'
```

### Unit tests for the verification helper

```typescript
// src/github/verify-signature.test.ts
import { describe, it, expect } from "vitest";
import { verifyGitHubWebhookSignature } from "./verify-signature";

const SECRET = "test-webhook-secret";

async function makeHmac(body: string, secret: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(body));
  return Array.from(new Uint8Array(sig)).map((b) => b.toString(16).padStart(2, "0")).join("");
}

describe("verifyGitHubWebhookSignature", () => {
  it("accepts a valid signature", async () => {
    const body = '{"action":"opened"}';
    const hex = await makeHmac(body, SECRET);
    const req = new Request("https://worker.example.com/webhook", {
      method: "POST",
      headers: { "X-Hub-Signature-256": `sha256=${hex}` },
      body,
    });
    const { valid } = await verifyGitHubWebhookSignature(req, SECRET);
    expect(valid).toBe(true);
  });

  it("rejects a tampered body", async () => {
    const hex = await makeHmac('{"action":"opened"}', SECRET);
    const req = new Request("https://worker.example.com/webhook", {
      method: "POST",
      headers: { "X-Hub-Signature-256": `sha256=${hex}` },
      body: '{"action":"deleted"}', // body changed after signing
    });
    const { valid } = await verifyGitHubWebhookSignature(req, SECRET);
    expect(valid).toBe(false);
  });

  it("rejects a missing header", async () => {
    const req = new Request("https://worker.example.com/webhook", {
      method: "POST",
      body: '{"action":"opened"}',
    });
    const { valid } = await verifyGitHubWebhookSignature(req, SECRET);
    expect(valid).toBe(false);
  });
});
```

## Anti-patterns

- **Parsing the JSON body before reading the raw bytes.** `request.json()` consumes the stream.
  You must `await request.arrayBuffer()` first, then `JSON.parse(new TextDecoder().decode(body))`.
- **Using a JS string comparison (`===` or `!==`) to compare HMAC digests.** String comparison
  short-circuits on first mismatch and is vulnerable to timing attacks. Use `crypto.subtle.verify`
  which is timing-safe.
- **Accepting `X-Hub-Signature` (SHA-1) instead of `X-Hub-Signature-256`.** GitHub deprecated
  SHA-1 signatures in 2022. Only accept the SHA-256 variant.
- **Enabling Node.js compat mode solely for HMAC.** `nodejs_compat` expands the Worker's attack
  surface; the native WebCrypto path shown here needs no compat flag.

## Gotchas

- `request.arrayBuffer()` and `request.json()` both drain the body stream. Once called, a second
  call returns an empty buffer. Clone the request with `request.clone()` if you need to pass it
  downstream after verification, or keep the `ArrayBuffer` reference.
- GitHub always sends `sha256=<lowercase-hex>`. If your stored hex has uppercase letters
  (e.g. from `Buffer.toString('hex')` on some platforms), the `parseInt` parsing in `hexToBytes`
  handles both, but an exact string comparison would fail.
- Workers with `compatibility_date >= 2022-10-31` expose `crypto.subtle` unconditionally.
  Older compatibility dates require `import { crypto } from "@cloudflare/workers-types"` or
  accessing `globalThis.crypto`. Set a current compatibility date.
- Empty webhook secrets are accepted by GitHub but produce a `sha256=` header with the HMAC of
  the empty string as the key. Always verify that `env.WEBHOOK_SECRET` is non-empty at startup.

## Verification

```shell
# Compute expected HMAC locally and compare with what the Worker receives
BODY='{"action":"opened","number":1}'
SECRET="your-webhook-secret"
EXPECTED_SIG=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "$SECRET" | awk '{print "sha256=" $2}')
echo "Expected: $EXPECTED_SIG"

# Send a test delivery to the Worker
curl -sSf -X POST https://your-worker.your-subdomain.workers.dev/webhook \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: pull_request" \
  -H "X-GitHub-Delivery: test-$(date +%s)" \
  -H "X-Hub-Signature-256: $EXPECTED_SIG" \
  -d "$BODY"

# Replay a real delivery using the GitHub UI:
# Repository → Settings → Webhooks → Recent Deliveries → Redeliver
```

## Related

- `github-webhook-signing-verification.md`
- `github-app-webhook-workers-handler.md`
- `github-webhook-delivery-reliability-retry-workers.md`
- `github-webhooks-event-handling.md`

## Sources

- <https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries>
- <https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/verify>
- <https://developers.cloudflare.com/workers/runtime-apis/web-crypto/>
- <https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/importKey>
