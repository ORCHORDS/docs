# Receiving and Verifying GitHub App Webhooks in a Cloudflare Worker

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
A GitHub App needs to react to events such as `installation`, `push`, and `pull_request` in real time without running a persistent server. Cloudflare Workers provide an ideal serverless target for webhook ingestion, but the Worker must verify the HMAC-SHA256 signature in `X-Hub-Signature-256` before processing any payload to prevent spoofed requests. Installation tokens obtained via JWT exchange must be cached to avoid hitting GitHub's rate limits on token generation.

---

## Context
GitHub App webhooks are signed using a shared secret configured in the App settings. The signature appears in the `X-Hub-Signature-256` header as `sha256=<hex>`. Workers must read the raw request body as an `ArrayBuffer`, compute the HMAC with the Web Crypto API (which is available in the Workers runtime), and perform a constant-time comparison to prevent timing attacks. After verification, the Worker routes events to typed handlers. GitHub App installation tokens expire after one hour; storing them in KV with a TTL slightly below 3600 seconds avoids unnecessary JWT minting on every event.

---

## Section 1 — Worker Configuration (`wrangler.toml`)
```toml
name = "github-app-webhook-handler"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[[kv_namespaces]]
binding = "INSTALLATION_TOKENS"
id = "YOUR_KV_NAMESPACE_ID"

[vars]
GITHUB_APP_ID = "123456"

[secrets]
# Set via: wrangler secret put GITHUB_WEBHOOK_SECRET
# Set via: wrangler secret put GITHUB_APP_PRIVATE_KEY
```

## Section 2 — Signature Verification and Event Router
```typescript
// src/index.ts
export interface Env {
  GITHUB_WEBHOOK_SECRET: string;
  GITHUB_APP_PRIVATE_KEY: string;
  GITHUB_APP_ID: string;
  INSTALLATION_TOKENS: KVNamespace;
}

async function verifySignature(
  secret: string,
  signature: string | null,
  body: ArrayBuffer
): Promise<boolean> {
  if (!signature?.startsWith('sha256=')) return false;
  const expectedHex = signature.slice('sha256='.length);

  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );

  const mac = await crypto.subtle.sign('HMAC', key, body);
  const actualHex = Array.from(new Uint8Array(mac))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');

  // Constant-time comparison
  if (actualHex.length !== expectedHex.length) return false;
  let diff = 0;
  for (let i = 0; i < actualHex.length; i++) {
    diff |= actualHex.charCodeAt(i) ^ expectedHex.charCodeAt(i);
  }
  return diff === 0;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    const rawBody = await request.arrayBuffer();
    const signature = request.headers.get('X-Hub-Signature-256');
    const valid = await verifySignature(env.GITHUB_WEBHOOK_SECRET, signature, rawBody);

    if (!valid) {
      return new Response('Unauthorized', { status: 401 });
    }

    const eventType = request.headers.get('X-GitHub-Event') ?? '';
    const payload = JSON.parse(new TextDecoder().decode(rawBody));

    switch (eventType) {
      case 'installation':
        await handleInstallation(payload, env);
        break;
      case 'push':
        await handlePush(payload, env);
        break;
      case 'pull_request':
        await handlePullRequest(payload, env);
        break;
      default:
        console.log(`Unhandled event: ${eventType}`);
    }

    return new Response('OK', { status: 200 });
  },
};
```

## Section 3 — Installation Token Exchange and KV Caching
```typescript
// src/installation-token.ts
import { Env } from './index';

async function signJWT(appId: string, privateKeyPem: string): Promise<string> {
  const header = { alg: 'RS256', typ: 'JWT' };
  const now = Math.floor(Date.now() / 1000);
  const payload = { iat: now - 60, exp: now + 540, iss: appId };

  const encode = (obj: object) =>
    btoa(JSON.stringify(obj)).replace(/=/g, '').replace(/\+/g, '-').replace(/\//g, '_');

  const signingInput = `${encode(header)}.${encode(payload)}`;

  // Import RSA private key from PEM
  const pemBody = privateKeyPem
    .replace(/<redacted-private-key>/g, '')
    .replace(/\s/g, '');
  const keyBuffer = Uint8Array.from(atob(pemBody), (c) => c.charCodeAt(0));

  const key = await crypto.subtle.importKey(
    'pkcs8',
    keyBuffer,
    { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' },
    false,
    ['sign']
  );

  const signature = await crypto.subtle.sign(
    'RSASSA-PKCS1-v1_5',
    key,
    new TextEncoder().encode(signingInput)
  );

  const sigBase64 = btoa(String.fromCharCode(...new Uint8Array(signature)))
    .replace(/=/g, '')
    .replace(/\+/g, '-')
    .replace(/\//g, '_');

  return `${signingInput}.${sigBase64}`;
}

export async function getInstallationToken(
  installationId: number,
  env: Env
): Promise<string> {
  const cacheKey = `install-token:${installationId}`;
  const cached = await env.INSTALLATION_TOKENS.get(cacheKey);
  if (cached) return cached;

  const jwt = await signJWT(env.GITHUB_APP_ID, env.GITHUB_APP_PRIVATE_KEY);

  const res = await fetch(
    `https://api.github.com/app/installations/${installationId}/access_tokens`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${jwt}`,
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'orchords-github-app/1.0',
      },
    }
  );

  if (!res.ok) {
    throw new Error(`Failed to get installation token: ${res.status} ${await res.text()}`);
  }

  const { token } = await res.json<{ token: string }>();

  // Cache with 55-minute TTL (tokens expire after 60 min)
  await env.INSTALLATION_TOKENS.put(cacheKey, token, { expirationTtl: 3300 });

  return token;
}

// Event handlers
export async function handleInstallation(payload: any, env: Env): Promise<void> {
  const { action, installation } = payload;
  console.log(`Installation ${action} for account: ${installation.account.login}`);
  if (action === 'deleted') {
    await env.INSTALLATION_TOKENS.delete(`install-token:${installation.id}`);
  }
}

export async function handlePush(payload: any, env: Env): Promise<void> {
  const { installation, repository, ref } = payload;
  if (!installation) return;
  const token = await getInstallationToken(installation.id, env);
  console.log(`Push to ${repository.full_name} ref ${ref}, token acquired: ${!!token}`);
}

export async function handlePullRequest(payload: any, env: Env): Promise<void> {
  const { action, pull_request, installation } = payload;
  if (!installation) return;
  const token = await getInstallationToken(installation.id, env);
  console.log(`PR #${pull_request.number} ${action}, token acquired: ${!!token}`);
}
```

---

## Anti-patterns
- **Reading the body as text before verification** — The HMAC must be computed over the raw bytes; converting to a string first risks encoding issues on non-ASCII payloads.
- **Using `===` for signature comparison** — JavaScript string equality is not constant-time; use the bitwise XOR loop shown above to prevent timing oracle attacks.
- **Minting a new installation token on every event** — GitHub limits token generation to ~5,000 requests per hour per installation; always cache in KV.
- **Storing the private key as a `var`** — Private keys must be stored as Wrangler secrets, never in `wrangler.toml` vars or committed to source.

---

## Gotchas
- GitHub sends webhooks with a 10-second delivery timeout; heavy processing should be offloaded to a Queue or Durable Object.
- The `X-GitHub-Delivery` header contains a unique UUID per event delivery — log it for deduplication.
- Installation tokens are scoped to the repositories the App was installed on; attempting to access other repos returns 403.
- The Workers runtime supports `crypto.subtle` for HMAC/RSA but not Node.js `crypto` — do not import the Node.js crypto module.
- PEM private keys from GitHub contain `PKCS#1` format (`BEGIN RSA PRIVATE KEY`); Web Crypto expects `PKCS#8` — convert with `openssl pkcs8 -topk8 -nocrypt` if needed.

---

## Verification
```bash
# Send a test webhook event locally using wrangler dev
wrangler dev --port 8787

# In another terminal, send a signed test payload
SECRET="your-webhook-secret"
PAYLOAD='{"action":"opened","installation":{"id":1}}'
SIG=$(echo -n "$PAYLOAD" | openssl dgst -sha256 -hmac "$SECRET" | awk '{print $2}')

curl -X POST http://localhost:8787 \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: pull_request" \
  -H "X-Hub-Signature-256: sha256=$SIG" \
  -d "$PAYLOAD"

# Verify KV token caching
wrangler kv key list --binding INSTALLATION_TOKENS
```

---

## Related
- `github-dependabot-auto-merge-workers.md`
- `github-copilot-extension-workers-backend.md`

---

## Sources
- GitHub App webhook signature verification — https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries
- GitHub App installation access tokens — https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-an-installation-access-token-for-a-github-app
- Cloudflare Workers Web Crypto API — https://developers.cloudflare.com/workers/runtime-apis/web-crypto
- Cloudflare Workers KV — https://developers.cloudflare.com/kv/
