# GitHub Copilot Extensions Workers API Plugin

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A platform team wants to expose internal tooling — D1 schema lookups, Wrangler deploy commands, R2 bucket stats — directly inside VS Code's Copilot Chat panel via an `@plugin-name` mention, without requiring engineers to leave their editor. The extension must verify that requests genuinely come from GitHub, stream responses back over SSE, and run without managing any server infrastructure.

## Context

GitHub Copilot Extensions (GA 2025) allow organizations to build custom chat agents that appear alongside Copilot in VS Code, JetBrains, and github.com. An extension is a GitHub App whose webhook URL receives signed `POST` requests when a user types `@your-extension`. The backend must verify the `X-GitHub-Public-Key-Signature` header, parse the conversation payload, call whatever APIs it needs, and return a streaming SSE response in the Copilot agent protocol format. A Cloudflare Worker is well-suited as the extension backend: it handles the crypto verification with the Web Crypto API, streams SSE natively via `TransformStream`, and scales to zero when no one is chatting.

## GitHub App and extension registration

1. Create a GitHub App at **Settings → Developer settings → GitHub Apps → New**.
2. Set the **Webhook URL** to the Worker's route (`https://copilot-ext.example.com/`).
3. Under **Copilot** → **Agent Type**: choose **Agent**.
4. Set **Copilot Chat description** and **Pre-authorization URL** (for OAuth flows, if needed).
5. Install the App on the target org. Users then mention `@your-app-slug` in Copilot Chat.

## Signature verification

GitHub signs each request with a per-request ECDSA signature over the raw body. The public key is fetched from `https://api.github.com/meta/public_keys/copilot_api`.

```typescript
// src/verify.ts
const GITHUB_KEYS_URL =
  "https://api.github.com/meta/public_keys/copilot_api";

interface GitHubKey {
  key_identifier: string;
  key: string;       // PEM public key
  is_current: boolean;
}

export async function verifyGitHubSignature(
  request: Request,
  rawBody: string
): Promise<void> {
  const keyId = request.headers.get("X-GitHub-Public-Key-Identifier");
  const signature = request.headers.get("X-GitHub-Public-Key-Signature");

  if (!keyId || !signature) {
    throw new Error("Missing signature headers");
  }

  const keysResp = await fetch(GITHUB_KEYS_URL, {
    headers: { "User-Agent": "copilot-worker-extension/1.0" },
  });
  const { public_keys } = await keysResp.json<{ public_keys: GitHubKey[] }>();
  const keyEntry = public_keys.find((k) => k.key_identifier === keyId);
  if (!keyEntry) throw new Error(`Unknown key identifier: ${keyId}`);

  // Import the ECDSA public key (P-256, used by GitHub for Copilot)
  const pemBody = keyEntry.key
    .replace(/-----BEGIN PUBLIC KEY-----/, "")
    .replace(/-----END PUBLIC KEY-----/, "")
    .replace(/\s/g, "");
  const der = Uint8Array.from(atob(pemBody), (c) => c.charCodeAt(0));
  const cryptoKey = await crypto.subtle.importKey(
    "spki",
    der,
    { name: "ECDSA", namedCurve: "P-256" },
    false,
    ["verify"]
  );

  const sigBytes = Uint8Array.from(atob(signature), (c) => c.charCodeAt(0));
  const bodyBytes = new TextEncoder().encode(rawBody);
  const valid = await crypto.subtle.verify(
    { name: "ECDSA", hash: "SHA-256" },
    cryptoKey,
    sigBytes,
    bodyBytes
  );
  if (!valid) throw new Error("Signature verification failed");
}
```

## Streaming SSE response

Copilot Extensions receive responses as server-sent events. Each event is a JSON-encoded message following the agent protocol.

```typescript
// src/stream.ts
export type CopilotRole = "assistant" | "system";

export interface CopilotMessage {
  role: CopilotRole;
  content: string;
}

/**
 * Build a streaming SSE Response compatible with the Copilot agent protocol.
 * chunks: array of text fragments to stream; last event signals completion.
 */
export function streamCopilotResponse(chunks: string[]): Response {
  const { readable, writable } = new TransformStream<Uint8Array, Uint8Array>();
  const writer = writable.getWriter();
  const enc = new TextEncoder();

  (async () => {
    for (const chunk of chunks) {
      const event = JSON.stringify({
        choices: [{ delta: { role: "assistant", content: chunk }, index: 0 }],
      });
      await writer.write(enc.encode(`data: ${event}\n\n`));
    }
    // Signal completion
    await writer.write(enc.encode("data: [DONE]\n\n"));
    await writer.close();
  })();

  return new Response(readable, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
}
```

## Worker entry point

```typescript
// src/index.ts
import { verifyGitHubSignature } from "./verify";
import { streamCopilotResponse } from "./stream";

export interface Env {
  D1_DB: D1Database;
  GITHUB_APP_ID: string;
}

interface CopilotPayload {
  messages: Array<{ role: string; content: string }>;
  copilot_thread_id: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    const rawBody = await request.text();

    try {
      await verifyGitHubSignature(request, rawBody);
    } catch (err) {
      console.error("Verification failed:", err);
      return new Response("Unauthorized", { status: 401 });
    }

    const payload: CopilotPayload = JSON.parse(rawBody);
    const lastMessage = payload.messages.findLast((m) => m.role === "user");
    const userText = lastMessage?.content ?? "";

    // Route user intent to internal tooling
    if (/d1|schema|table/i.test(userText)) {
      return handleD1Query(userText, env);
    }

    return streamCopilotResponse([
      "I can help with D1 schema lookups and Worker deploys. ",
      "Try: `@your-ext show tables in my-database`",
    ]);
  },
} satisfies ExportedHandler<Env>;

async function handleD1Query(query: string, env: Env): Promise<Response> {
  const tableMatch = /in\s+([\w-]+)/i.exec(query);
  const dbName = tableMatch?.[1] ?? "default";

  const result = await env.D1_DB.prepare(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
  ).all<{ name: string }>();

  const tableList = result.results.map((r) => `- ${r.name}`).join("\n");
  const chunks = [
    `Tables in **${dbName}**:\n\n`,
    tableList || "_No tables found_",
  ];
  return streamCopilotResponse(chunks);
}
```

## CI/CD: deploying the extension Worker

```yaml
# .github/workflows/deploy-copilot-ext.yml
name: Deploy Copilot Extension Worker

on:
  push:
    branches: [main]
    paths:
      - "copilot-ext/**"
      - ".github/workflows/deploy-copilot-ext.yml"

permissions:
  contents: read
  id-token: write

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - run: pnpm install --frozen-lockfile
        working-directory: copilot-ext

      - name: Deploy Worker
        uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          accountId: ${{ vars.CF_ACCOUNT_ID }}
          workingDirectory: copilot-ext
          command: deploy --env production
```

## Anti-patterns

- Skipping signature verification and trusting the payload directly — any HTTP client can call the Worker URL and inject arbitrary messages.
- Caching the GitHub public keys response indefinitely — GitHub rotates keys; cache with a short TTL (5–15 minutes) or re-fetch per request.
- Blocking the event loop with a long synchronous D1 query before opening the SSE stream — start the stream immediately with a "Thinking…" event, then write results as they resolve.
- Returning a regular JSON response instead of SSE — Copilot's extension protocol requires `text/event-stream` with the agent event format; a JSON body is ignored or shown as an error.

## Gotchas

- The GitHub public key endpoint (`/meta/public_keys/copilot_api`) is separate from the standard webhook signing key (`/meta/public_keys/webhooks`). Using the wrong key causes all verifications to fail.
- Copilot Extensions must respond within 10 seconds or GitHub times out the request from the user's side. For slow D1 or Workers AI calls, stream an initial "processing" event within 2 seconds.
- The `X-GitHub-Public-Key-Signature` header uses base64-encoded DER-format ECDSA (not the signature envelope format). Decode with `atob`, not a custom base64url decoder.
- Extension agents are invoked by GitHub's infrastructure over the public internet — the Worker URL must be publicly reachable. There is no IP allowlisting mechanism for Copilot Extension callbacks.
- Preview limitations as of mid-2026: Copilot Extensions cannot initiate conversations, access code context beyond what the user explicitly pastes, or read repository files unless the user grants additional OAuth scopes.

## Verification

```bash
# Install the GitHub Copilot CLI extension tester (if available)
# Or send a test payload manually with the correct signature headers

curl -X POST https://copilot-ext.example.com/ \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Public-Key-Identifier: <key-id>" \
  -H "X-GitHub-Public-Key-Signature: <sig>" \
  -d '{"messages":[{"role":"user","content":"show tables in my-db"}],"copilot_thread_id":"test-123"}'

# Expected: SSE stream with table list and final [DONE] event
```

In VS Code, type `@your-extension show tables in my-db` in Copilot Chat. The extension should stream a markdown-formatted table list.

## Related

- `github-apps-installation-tokens.md`
- `github-app-webhook-workers-handler.md`
- `github-apps-jwt-webcrypto-workers-auth.md`
- `github-actions-workers-for-platforms-dispatch-deploy.md`
- `github-webhook-signing-verification.md`

## Sources

- https://docs.github.com/en/copilot/building-copilot-extensions/about-building-copilot-extensions
- https://docs.github.com/en/copilot/building-copilot-extensions/building-a-copilot-agent-for-your-copilot-extension/configuring-your-copilot-agent-to-communicate-with-the-copilot-platform
- https://developers.cloudflare.com/workers/runtime-apis/streams/transformstream/
- https://api.github.com/meta/public_keys/copilot_api
