# Cloudflare Workers AI: Edge Inference for UI Features

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
You want to add AI-powered features (streaming chat, content summarization, alt-text generation) to your frontend without provisioning a separate inference server or paying per-token to a third-party API from the client side.

## Context
Cloudflare Workers AI provides a binding (`AI`) that runs inference on Cloudflare's GPU fleet directly within a Worker. Requests never leave Cloudflare's network until they hit the GPU, latency is low (Workers are colocated with the inference hardware), and billing is on the Workers AI usage tier rather than a separate SaaS API. Supported model families include text generation (Llama, Mistral, Phi), embeddings, image classification, and speech-to-text.

## Wrangler Binding and TypeScript Types

```typescript
// wrangler.toml (add to existing config)
// [ai]
// binding = "AI"

// src/types.ts
export type Env = {
  AI: Ai; // Provided by @cloudflare/workers-types
};

// Install: npm i -D @cloudflare/workers-types
// tsconfig.json: { "compilerOptions": { "types": ["@cloudflare/workers-types"] } }
```

## Streaming Text Generation to the Browser

```typescript
// src/routes/chat.ts
import { Hono } from 'hono';
import { stream } from 'hono/streaming';
import type { Env } from '../types';

const chatApp = new Hono<{ Bindings: Env }>();

chatApp.post('/chat', async (c) => {
  const { messages } = await c.req.json<{
    messages: Array<{ role: 'user' | 'assistant'; content: string }>;
  }>();

  const aiStream = await c.env.AI.run('@cf/meta/llama-3.1-8b-instruct', {
    messages: [
      { role: 'system', content: 'You are a helpful assistant for an e-commerce store.' },
      ...messages,
    ],
    stream: true,
    max_tokens: 512,
  });

  // Forward the ReadableStream directly to the browser as SSE
  return stream(c, async (s) => {
    s.onAbort(() => {
      // Cloudflare automatically cancels the upstream when the client disconnects
    });
    // aiStream is a ReadableStream<Uint8Array> when stream: true
    const reader = (aiStream as ReadableStream).getReader();
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      await s.write(value);
    }
  });
});

export default chatApp;
```

## Browser-Side Streaming Consumer

```typescript
// src/lib/useChat.ts
import { useState, useCallback } from 'react';

export function useChat() {
  const [messages, setMessages] = useState<Array<{ role: string; content: string }>>([]);
  const [streaming, setStreaming] = useState(false);

  const send = useCallback(async (userMessage: string) => {
    const next = [...messages, { role: 'user', content: userMessage }];
    setMessages([...next, { role: 'assistant', content: '' }]);
    setStreaming(true);

    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages: next }),
    });

    if (!res.body) return;
    const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      // Workers AI SSE format: "data: {...}\n\n"
      buffer += value;
      const lines = buffer.split('\n');
      buffer = lines.pop() ?? '';
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const raw = line.slice(6).trim();
        if (raw === '[DONE]') break;
        try {
          const { response } = JSON.parse(raw) as { response: string };
          setMessages((prev) => {
            const updated = [...prev];
            updated[updated.length - 1] = {
              role: 'assistant',
              content: updated[updated.length - 1].content + response,
            };
            return updated;
          });
        } catch {
          // partial JSON chunk, accumulate
        }
      }
    }
    setStreaming(false);
  }, [messages]);

  return { messages, streaming, send };
}
```

## Image Alt-Text Generation

```typescript
// src/routes/alt-text.ts
import { Hono } from 'hono';
import type { Env } from '../types';

const altTextApp = new Hono<{ Bindings: Env }>();

altTextApp.post('/alt-text', async (c) => {
  const formData = await c.req.formData();
  const file = formData.get('image') as File | null;
  if (!file) return c.json({ error: 'No image provided' }, 400);

  if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
    return c.json({ error: 'Unsupported image type' }, 415);
  }

  const buffer = await file.arrayBuffer();

  // Use image-to-text model for caption generation
  const result = await c.env.AI.run('@cf/unum/uform-gen2-qnx', {
    image: [...new Uint8Array(buffer)],
    prompt: 'Generate a concise, descriptive alt text for this image in 15 words or fewer.',
    max_tokens: 64,
  });

  return c.json({ altText: result.description ?? '' });
});

export default altTextApp;
```

## Semantic Embeddings for Search

```typescript
// src/routes/search.ts
import { Hono } from 'hono';
import type { Env } from '../types';

type SearchEnv = Env & { VECTORIZE: VectorizeIndex };

const searchApp = new Hono<{ Bindings: SearchEnv }>();

searchApp.get('/search', async (c) => {
  const query = c.req.query('q');
  if (!query) return c.json({ results: [] });

  // Generate embedding for the query string
  const embeddingRes = await c.env.AI.run('@cf/baai/bge-small-en-v1.5', {
    text: [query],
  });
  const queryVector = embeddingRes.data[0];

  // Query Vectorize for top-5 nearest neighbors
  const matches = await c.env.VECTORIZE.query(queryVector, {
    topK: 5,
    returnValues: false,
    returnMetadata: 'all',
  });

  return c.json({
    results: matches.matches.map((m) => ({
      id: m.id,
      score: m.score,
      title: (m.metadata as Record<string, string>).title,
      url: (m.metadata as Record<string, string>).url,
    })),
  });
});

export default searchApp;
```

## Anti-patterns
- Calling Workers AI from the browser directly — the AI binding is server-side only; expose it through a Worker route
- Buffering the entire AI response before sending to the browser — use `stream: true` and pipe `ReadableStream` to avoid timeout (Workers have a 30 s CPU time limit)
- Not validating file size and MIME type before sending to image models — large images consume significant CPU time and can exceed the 10 MB request body limit
- Using Workers AI for latency-sensitive synchronous UI interactions (< 200 ms expected) — LLM inference typically takes 500 ms–3 s
- Hardcoding model IDs without version pinning — models are updated; pin to a specific version suffix when output consistency is required

## Gotchas
- `@cf/meta/llama-3.1-8b-instruct` returns an `AiTextGenerationOutput` which is either a `{ response: string }` object or a `ReadableStream` depending on the `stream` flag — TypeScript type narrowing is required
- Workers AI responses count against the account's AI token quota, not Workers CPU time — monitor usage in the Cloudflare dashboard under AI > Usage
- `Vectorize.query()` requires the embedding dimension to match the index's configured dimension exactly — mismatches produce a 400 error with no client hint
- The `image` field on image models expects `number[]` (a plain array), not `Uint8Array` — spread with `[...new Uint8Array(buffer)]`
- Streaming requires the Workers runtime to keep the connection open; set `fetch` keepalive and ensure the browser does not apply an aggressive read timeout

## Verification
```bash
# Local dev with remote AI binding (AI cannot run locally)
npx wrangler dev --remote

# Test streaming endpoint
curl -N -X POST https://my-worker.workers.dev/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Hello"}]}'

# Verify alt-text endpoint
curl -X POST https://my-worker.workers.dev/api/alt-text \
  -F 'image=@./test.jpg'
```

## Related
- [Hono.js on Cloudflare Workers Frontend API](hono-cloudflare-workers-frontend-api.md)
- [WebSocket Durable Objects Realtime UI](websocket-durable-objects-realtime-ui.md)
- [Server-Sent Events Streaming UI](server-sent-events-streaming-ui.md)
- [Feature Flags Cloudflare Workers KV](feature-flags-cloudflare-workers-kv-edge-config.md)

## Sources
- https://developers.cloudflare.com/workers-ai/
- https://developers.cloudflare.com/workers-ai/models/
- https://developers.cloudflare.com/vectorize/
- https://github.com/cloudflare/workers-types
