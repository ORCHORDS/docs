# Building a GitHub Copilot Extension Served by Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You want to ship a GitHub Copilot Extension (a GitHub App that integrates into the Copilot Chat UI) and host the agent endpoint on Cloudflare Workers instead of a traditional server. The Worker must verify the `X-GitHub-Token` header, stream Server-Sent Events (SSE) back to Copilot, expose tools for Copilot function-calling, store conversation context in D1, and exchange an OIDC token to call internal APIs.

## Context

GitHub Copilot Extensions work by forwarding user messages to an agent URL you register in the GitHub App manifest. The agent must:

1. Verify the `X-GitHub-Token` bearer token against GitHub's OIDC discovery endpoint.
2. Return an SSE stream with `text/event-stream` content-type, emitting `copilot_references`, `copilot_confirmation`, and `choices` event types.
3. Optionally expose tool definitions so Copilot can call back for structured data.
4. Maintain per-conversation context (D1 is ideal — persistent, SQL, zero-ops on Workers).
5. Exchange an OIDC token for your internal API using a client-credentials flow.

Workers handle SSE via `ReadableStream` + `TransformStream`. The `waitUntil` pattern lets you flush D1 writes after the response is sent.

## Solution

```typescript
// src/index.ts
import { Hono } from 'hono';
import { stream } from 'hono/streaming';

export interface Env {
  DB: D1Database;
  GITHUB_APP_CLIENT_ID: string;
  GITHUB_APP_CLIENT_SECRET: string;
  INTERNAL_API_URL: string;
  INTERNAL_CLIENT_ID: string;
  INTERNAL_CLIENT_SECRET: string;
}

interface CopilotMessage {
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  tool_call_id?: string;
}

interface CopilotRequest {
  messages: CopilotMessage[];
  copilot_thread_id: string;
  agent?: { name: string };
}

interface GitHubOidcClaims {
  sub: string;
  iss: string;
  aud: string;
  exp: number;
  iat: number;
  login: string;
  repository_owner_id?: string;
}

// --- OIDC token verification ---
async function verifyGitHubToken(
  token: string,
  expectedAudience: string,
): Promise<GitHubOidcClaims> {
  // Fetch GitHub OIDC discovery document
  const discovery = await fetch(
    'https://token.actions.githubusercontent.com/.well-known/openid-configuration',
  );
  const { jwks_uri } = (await discovery.json()) as { jwks_uri: string };

  const jwksRes = await fetch(jwks_uri);
  const { keys } = (await jwksRes.json()) as { keys: JsonWebKey[] };

  // Decode header to identify the signing key
  const [headerB64] = token.split('.');
  const header = JSON.parse(atob(headerB64.replace(/-/g, '+').replace(/_/g, '/'))) as {
    kid: string;
    alg: string;
  };

  const jwk = keys.find((k: JsonWebKey & { kid?: string }) => k.kid === header.kid);
  if (!jwk) throw new Error('No matching JWK found');

  const cryptoKey = await crypto.subtle.importKey(
    'jwk',
    jwk,
    { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' },
    false,
    ['verify'],
  );

  const [, payloadB64, sigB64] = token.split('.');
  const signingInput = new TextEncoder().encode(
    `${headerB64}.${payloadB64}`,
  );
  const signature = Uint8Array.from(
    atob(sigB64.replace(/-/g, '+').replace(/_/g, '/')),
    (c) => c.charCodeAt(0),
  );

  const valid = await crypto.subtle.verify(
    'RSASSA-PKCS1-v1_5',
    cryptoKey,
    signature,
    signingInput,
  );
  if (!valid) throw new Error('Invalid JWT signature');

  const payload = JSON.parse(
    atob(payloadB64.replace(/-/g, '+').replace(/_/g, '/')),
  ) as GitHubOidcClaims;

  if (payload.aud !== expectedAudience) throw new Error('Audience mismatch');
  if (payload.exp < Math.floor(Date.now() / 1000)) throw new Error('Token expired');

  return payload;
}

// --- OIDC token exchange for internal API ---
async function exchangeForInternalToken(env: Env): Promise<string> {
  const res = await fetch(`${env.INTERNAL_API_URL}/oauth/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      grant_type: 'client_credentials',
      client_id: env.INTERNAL_CLIENT_ID,
      client_secret: env.INTERNAL_CLIENT_SECRET,
    }),
  });
  const { access_token } = (await res.json()) as { access_token: string };
  return access_token;
}

// --- Tool definitions (Copilot function calling) ---
const TOOLS = [
  {
    type: 'function',
    function: {
      name: 'search_internal_docs',
      description: 'Search the internal knowledge base for code examples and architecture docs.',
      parameters: {
        type: 'object',
        properties: {
          query: { type: 'string', description: 'Natural language search query.' },
          top_k: { type: 'number', description: 'Number of results to return (max 10).' },
        },
        required: ['query'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_repo_context',
      description: 'Fetch recent commits, open PRs, and active branches for a given repository.',
      parameters: {
        type: 'object',
        properties: {
          owner: { type: 'string' },
          repo: { type: 'string' },
        },
        required: ['owner', 'repo'],
      },
    },
  },
];

// --- D1 helpers ---
async function loadContext(db: D1Database, threadId: string): Promise<CopilotMessage[]> {
  const result = await db
    .prepare('SELECT messages FROM copilot_context WHERE thread_id = ?')
    .bind(threadId)
    .first<{ messages: string }>();
  return result ? (JSON.parse(result.messages) as CopilotMessage[]) : [];
}

async function saveContext(
  db: D1Database,
  threadId: string,
  messages: CopilotMessage[],
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO copilot_context (thread_id, messages, updated_at)
       VALUES (?, ?, datetime('now'))
       ON CONFLICT(thread_id) DO UPDATE SET messages = excluded.messages, updated_at = excluded.updated_at`,
    )
    .bind(threadId, JSON.stringify(messages))
    .run();
}

// --- SSE helpers ---
function sseEvent(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

function copilotDelta(content: string, finishReason: string | null = null): string {
  return sseEvent('choices', [
    {
      delta: { role: 'assistant', content },
      finish_reason: finishReason,
      index: 0,
    },
  ]);
}

// --- Main app ---
const app = new Hono<{ Bindings: Env }>();

app.get('/health', (c) => c.text('ok'));

app.post('/agent', async (c) => {
  const authHeader = c.req.header('X-GitHub-Token') ?? c.req.header('Authorization') ?? '';
  const token = authHeader.replace(/^Bearer\s+/i, '');

  try {
    await verifyGitHubToken(token, c.env.GITHUB_APP_CLIENT_ID);
  } catch (err) {
    return c.json({ error: `Unauthorized: ${(err as Error).message}` }, 401);
  }

  const body = (await c.req.json()) as CopilotRequest;
  const { messages, copilot_thread_id } = body;

  // Merge stored context with incoming messages
  const storedMessages = await loadContext(c.env.DB, copilot_thread_id);
  const allMessages: CopilotMessage[] = [
    { role: 'system', content: 'You are an expert Cloudflare Workers assistant for example.com.' },
    ...storedMessages,
    ...messages,
  ];

  const internalToken = await exchangeForInternalToken(c.env);

  return stream(c, async (s) => {
    c.header('Content-Type', 'text/event-stream');
    c.header('Cache-Control', 'no-cache');
    c.header('X-Accel-Buffering', 'no');

    // Emit tool definitions so Copilot knows what tools are available
    await s.write(
      sseEvent('copilot_references', {
        type: 'tool_definitions',
        tools: TOOLS,
      }),
    );

    // Call internal AI endpoint with streaming
    const aiRes = await fetch(`${c.env.INTERNAL_API_URL}/v1/chat/completions`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${internalToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        model: 'claude-sonnet-4-6',
        messages: allMessages,
        stream: true,
        tools: TOOLS,
      }),
    });

    if (!aiRes.ok || !aiRes.body) {
      await s.write(copilotDelta('Sorry, the internal AI service is unavailable.', 'stop'));
      await s.write('data: [DONE]\n\n');
      return;
    }

    const reader = aiRes.body.getReader();
    const decoder = new TextDecoder();
    let assistantContent = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const chunk = decoder.decode(value, { stream: true });
      for (const line of chunk.split('\n')) {
        if (!line.startsWith('data: ')) continue;
        const payload = line.slice(6).trim();
        if (payload === '[DONE]') {
          await s.write(copilotDelta('', 'stop'));
          await s.write('data: [DONE]\n\n');
          break;
        }
        try {
          const parsed = JSON.parse(payload) as {
            choices: Array<{ delta: { content?: string }; finish_reason: string | null }>;
          };
          const delta = parsed.choices?.[0]?.delta?.content ?? '';
          if (delta) {
            assistantContent += delta;
            await s.write(copilotDelta(delta));
          }
        } catch {
          // skip malformed chunks
        }
      }
    }

    // Persist updated context — fire-and-forget after stream closes
    c.executionCtx.waitUntil(
      saveContext(c.env.DB, copilot_thread_id, [
        ...messages,
        { role: 'assistant', content: assistantContent },
      ]),
    );
  });
});

export default app;
```

## Implementation Details

**D1 schema** — create the context table in a migration:

```sql
CREATE TABLE IF NOT EXISTS copilot_context (
  thread_id  TEXT PRIMARY KEY,
  messages   TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

**wrangler.toml** bindings:

```toml
[[d1_databases]]
binding = "DB"
database_name = "copilot-context"
database_id   = "<your-d1-id>"
```

**GitHub App settings** — set the agent URL to `https://<worker>.workers.dev/agent` and enable the `Copilot Chat` permission (read). The `X-GitHub-Token` is sent by GitHub with every request; no webhook secret is needed for the agent endpoint.

**OIDC verification caching** — in production, cache the JWKS response in Workers KV (TTL 1 hour) to avoid refetching on every request.

## Anti-patterns

- Do not buffer the full AI response before streaming — Copilot has a 30-second timeout; stream incrementally.
- Do not store full message history unbounded in D1; cap at the last N turns (e.g., 20) to keep prompt size manageable.
- Do not skip signature verification — token replay attacks are trivial without it.
- Do not use `waitUntil` for D1 writes inside the stream body; call it on the outer `c.executionCtx` after the stream function is invoked.

## Gotchas

- GitHub sends `X-GitHub-Token` (not `Authorization`) for Copilot Extension agent requests.
- The SSE `Content-Type` must be exactly `text/event-stream`; Copilot rejects `text/event-stream; charset=utf-8`.
- Workers SSE via `hono/streaming` flushes on each `write()` call — do not batch deltas.
- The OIDC issuer for Copilot Extensions is `https://token.actions.githubusercontent.com`, not `https://github.com`.
- `crypto.subtle` is available natively in the Workers runtime; no polyfill is needed.

## Verification

```bash
# Local smoke test with GitHub Copilot CLI proxy
wrangler dev --local
curl -N -X POST http://localhost:8787/agent \
  -H 'Content-Type: application/json' \
  -H 'X-GitHub-Token: <test-token>' \
  -d '{"messages":[{"role":"user","content":"Hello"}],"copilot_thread_id":"test-1"}'

# D1 migrations
wrangler d1 migrations apply copilot-context --local
wrangler d1 migrations apply copilot-context --remote
```

## Related

- `documentation/docs/policies/github/workers-github-code-review-stats.md`
- `documentation/docs/policies/cloudflare/workers-d1-migrations.md`
- `documentation/docs/policies/cloudflare/workers-sse-streaming.md`

## Sources

- https://docs.github.com/en/copilot/building-copilot-extensions/building-a-copilot-agent-for-your-copilot-extension
- https://developers.cloudflare.com/d1/
- https://hono.dev/docs/helpers/streaming
- https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-user-access-token-for-a-github-app
