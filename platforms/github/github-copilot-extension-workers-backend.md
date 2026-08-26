# Building a GitHub Copilot Extension Backend with Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
GitHub Copilot Extensions allow organizations to embed custom AI assistants into Copilot Chat, but they require a secure HTTPS backend that verifies GitHub's request signature, streams SSE responses in the exact format Copilot expects, and handles completions efficiently. Cloudflare Workers is an ideal host: globally distributed, sub-millisecond cold starts, Workers AI available in the same runtime, and D1 for usage logging — all without managing servers.

---

## Context
Copilot Extensions communicate with the backend via signed HTTP requests. GitHub signs each request with an asymmetric key; the backend fetches the public key from GitHub's JWKS endpoint and verifies the `X-GitHub-Public-Key-Signature` and `X-GitHub-Public-Key-Identifier` headers. The response must be a Server-Sent Events (SSE) stream where each `data:` line contains a JSON object in OpenAI chat completion chunk format: `{"choices": [{"delta": {"content": "..."},"finish_reason": null}]}`. Workers AI (`@cf/meta/llama-3.1-8b-instruct`) supports streaming completions natively. Each completion is logged to D1 for usage analytics and quota enforcement.

---

## Section 1 — Worker Configuration (`wrangler.toml`)
```toml
name = "copilot-extension-backend"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[ai]
binding = "AI"

[[d1_databases]]
binding = "USAGE_LOG"
database_name = "copilot-usage"
database_id = "YOUR_D1_DATABASE_ID"

[[kv_namespaces]]
binding = "JWKS_CACHE"
id = "YOUR_KV_NAMESPACE_ID"

[vars]
GITHUB_JWKS_URL = "https://api.github.com/meta/public_keys/copilot_api"

# Schema (run once):
# CREATE TABLE IF NOT EXISTS usage_log (
#   id INTEGER PRIMARY KEY AUTOINCREMENT,
#   github_login TEXT NOT NULL,
#   prompt_tokens INTEGER,
#   completion_tokens INTEGER,
#   model TEXT NOT NULL,
#   requested_at TEXT NOT NULL
# );
```

## Section 2 — Signature Verification and SSE Response
```typescript
// src/index.ts
export interface Env {
  AI: Ai;
  USAGE_LOG: D1Database;
  JWKS_CACHE: KVNamespace;
  GITHUB_JWKS_URL: string;
}

interface GitHubPublicKey {
  key_identifier: string;
  key: string; // PEM-encoded EC public key
  is_current: boolean;
}

async function fetchPublicKey(keyIdentifier: string, env: Env): Promise<string> {
  const cacheKey = `jwks:${keyIdentifier}`;
  const cached = await env.JWKS_CACHE.get(cacheKey);
  if (cached) return cached;

  const res = await fetch(env.GITHUB_JWKS_URL, {
    headers: { 'User-Agent': 'orchords-copilot-extension/1.0' },
  });
  if (!res.ok) throw new Error(`JWKS fetch failed: ${res.status}`);

  const { public_keys }: { public_keys: GitHubPublicKey[] } = await res.json();
  const match = public_keys.find((k) => k.key_identifier === keyIdentifier);
  if (!match) throw new Error(`Key ${keyIdentifier} not found in JWKS`);

  // Cache for 1 hour — GitHub rotates keys infrequently
  await env.JWKS_CACHE.put(cacheKey, match.key, { expirationTtl: 3600 });
  return match.key;
}

async function verifyGitHubSignature(
  publicKeyPem: string,
  signature: string,
  body: ArrayBuffer
): Promise<boolean> {
  // GitHub uses ECDSA P-256 SHA-256
  const pemBody = publicKeyPem
    .replace(/-----BEGIN PUBLIC KEY-----|-----END PUBLIC KEY-----/g, '')
    .replace(/\s/g, '');
  const keyBytes = Uint8Array.from(atob(pemBody), (c) => c.charCodeAt(0));

  const key = await crypto.subtle.importKey(
    'spki',
    keyBytes,
    { name: 'ECDSA', namedCurve: 'P-256' },
    false,
    ['verify']
  );

  // Signature is base64-encoded DER
  const sigBytes = Uint8Array.from(atob(signature), (c) => c.charCodeAt(0));

  return crypto.subtle.verify({ name: 'ECDSA', hash: 'SHA-256' }, key, sigBytes, body);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    const rawBody = await request.arrayBuffer();
    const keyId = request.headers.get('X-GitHub-Public-Key-Identifier');
    const signature = request.headers.get('X-GitHub-Public-Key-Signature');

    if (!keyId || !signature) {
      return new Response('Missing signature headers', { status: 401 });
    }

    let publicKeyPem: string;
    try {
      publicKeyPem = await fetchPublicKey(keyId, env);
    } catch (e) {
      return new Response('Failed to fetch public key', { status: 500 });
    }

    const valid = await verifyGitHubSignature(publicKeyPem, signature, rawBody);
    if (!valid) {
      return new Response('Invalid signature', { status: 401 });
    }

    const payload = JSON.parse(new TextDecoder().decode(rawBody));
    return handleCompletion(payload, env);
  },
};
```

## Section 3 — Workers AI Completion and SSE Streaming with D1 Logging
```typescript
// src/completion.ts
import { Env } from './index';

const MODEL = '@cf/meta/llama-3.1-8b-instruct';

interface CopilotMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

function sseChunk(content: string): string {
  return `data: ${JSON.stringify({
    choices: [{ delta: { content }, finish_reason: null, index: 0 }],
  })}\n\n`;
}

function sseDone(): string {
  return `data: ${JSON.stringify({
    choices: [{ delta: {}, finish_reason: 'stop', index: 0 }],
  })}\n\ndata: [DONE]\n\n`;
}

export async function handleCompletion(payload: any, env: Env): Promise<Response> {
  const messages: CopilotMessage[] = payload.messages ?? [];
  const githubLogin: string = payload.copilot_thread_context?.current_url ?? 'unknown';

  // Prepend a system message if not present
  const systemMessage: CopilotMessage = {
    role: 'system',
    content:
      'You are a helpful GitHub Copilot extension assistant powered by example.com. ' +
      'Be concise, accurate, and developer-focused.',
  };
  const finalMessages =
    messages[0]?.role === 'system' ? messages : [systemMessage, ...messages];

  const promptText = finalMessages.map((m) => `${m.role}: ${m.content}`).join('\n');
  const promptTokenEstimate = Math.ceil(promptText.length / 4);

  let completionTokens = 0;

  const { readable, writable } = new TransformStream();
  const writer = writable.getWriter();
  const encoder = new TextEncoder();

  // Run the AI stream and D1 log concurrently
  const aiStream = async () => {
    try {
      const stream = await env.AI.run(MODEL, {
        messages: finalMessages,
        stream: true,
        max_tokens: 1024,
      } as any);

      const reader = (stream as ReadableStream).getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const text = decoder.decode(value, { stream: true });
        // Workers AI emits SSE lines; parse and re-emit in Copilot format
        for (const line of text.split('\n')) {
          if (!line.startsWith('data: ')) continue;
          const raw = line.slice(6).trim();
          if (raw === '[DONE]') break;
          try {
            const chunk = JSON.parse(raw);
            const content: string = chunk.response ?? '';
            if (content) {
              completionTokens += Math.ceil(content.length / 4);
              await writer.write(encoder.encode(sseChunk(content)));
            }
          } catch {
            // skip malformed chunks
          }
        }
      }

      await writer.write(encoder.encode(sseDone()));
    } finally {
      await writer.close();
      // Log to D1 after stream completes
      await env.USAGE_LOG.prepare(
        `INSERT INTO usage_log (github_login, prompt_tokens, completion_tokens, model, requested_at)
         VALUES (?, ?, ?, ?, ?)`
      )
        .bind(githubLogin, promptTokenEstimate, completionTokens, MODEL, new Date().toISOString())
        .run()
        .catch((e) => console.error('D1 log failed:', e));
    }
  };

  // Don't await — let it stream
  aiStream();

  return new Response(readable, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'X-Content-Type-Options': 'nosniff',
    },
  });
}
```

---

## Anti-patterns
- **Fetching the JWKS on every request** — GitHub's public key endpoint has rate limits; always cache the key in KV by `key_identifier` for at least one hour.
- **Returning a JSON response instead of SSE** — Copilot Chat requires a streaming SSE response; a plain JSON body causes the extension to hang waiting for stream events.
- **Using Node.js `crypto` for signature verification** — Workers runtime does not support Node.js crypto modules; use `crypto.subtle` with the `ECDSA` algorithm.
- **Not validating `X-GitHub-Public-Key-Identifier`** — The key identifier selects which of GitHub's public keys to use; ignoring it and hardcoding one key breaks when GitHub rotates keys.
- **Awaiting the AI stream before responding** — Buffer the full response before returning causes Copilot Chat to show no output until completion; always stream with `TransformStream`.

---

## Gotchas
- GitHub Copilot Extension requests time out after 25 seconds; ensure the AI model responds within this window or stream partial content promptly.
- The `payload.messages` array includes Copilot's injected system context; do not duplicate system messages.
- Workers AI `stream: true` returns a `ReadableStream` of SSE lines in its own format — parse and re-encode into Copilot's expected format.
- The `X-GitHub-Public-Key-Signature` is base64-encoded (not hex) DER-encoded ECDSA signature.
- GitHub may send a verification ping request with an empty body; return 200 OK without attempting AI completion.
- D1 writes after the stream completes may fail silently if the Worker CPU time limit is hit; wrap in `waitUntil` if the environment supports it.

---

## Verification
```bash
# Deploy the Worker
npx wrangler deploy

# Test signature verification locally (wrangler dev)
# GitHub provides a test tool in the Copilot Extension developer docs
curl -X POST http://localhost:8787 \
  -H 'Content-Type: application/json' \
  -H 'X-GitHub-Public-Key-Identifier: YOUR_KEY_ID' \
  -H 'X-GitHub-Public-Key-Signature: YOUR_SIGNATURE' \
  -d '{"messages":[{"role":"user","content":"Hello"}]}'

# Verify SSE stream format
curl -N -X POST https://your-worker.workers.dev \
  -H 'Content-Type: application/json' \
  ... | head -20

# Query usage log
wrangler d1 execute USAGE_LOG \
  --command "SELECT github_login, SUM(completion_tokens) as total FROM usage_log GROUP BY github_login ORDER BY total DESC LIMIT 10"

# Check JWKS cache
wrangler kv key list --binding JWKS_CACHE
```

---

## Related
- `github-app-webhook-workers-installation.md`
- `github-actions-workers-preview-url-pr-comment.md`

---

## Sources
- GitHub Copilot Extensions documentation — https://docs.github.com/en/copilot/building-copilot-extensions/about-building-copilot-extensions
- GitHub Copilot Extension signature verification — https://docs.github.com/en/copilot/building-copilot-extensions/building-a-copilot-agent-for-your-copilot-extension/configuring-your-copilot-agent-to-communicate-with-github
- Cloudflare Workers AI — https://developers.cloudflare.com/workers-ai/
- Cloudflare D1 — https://developers.cloudflare.com/d1/
- OpenAI chat completion streaming format — https://platform.openai.com/docs/api-reference/streaming
