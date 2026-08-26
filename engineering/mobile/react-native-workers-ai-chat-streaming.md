# React Native Workers AI Chat Streaming

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

React Native apps calling `@cf/meta/llama-3-8b-instruct` (or any Workers AI text-generation model) via `ai.run()` receive nothing until the entire completion is done, making the UX feel sluggish for long responses. The desired pattern mirrors ChatGPT-style token-by-token delivery inside a `<FlatList>` or custom bubble component.

## Context

Workers AI supports streaming via the `stream: true` option, which emits `text/event-stream` SSE tokens. The challenge on React Native is that Hermes does not fully implement the WHATWG Streams API, and `EventSource` is absent. The recommended approach is: a Cloudflare Worker acts as the AI gateway, streams tokens via SSE, and the React Native app consumes them with `react-native-sse` or a chunked `fetch` with `response.body` on RN 0.73+. This article covers both paths plus abort, error handling, and conversation history via KV.

---

## Worker AI Streaming Gateway

```typescript
// workers/ai-chat.ts
import { Ai } from '@cloudflare/ai';

interface Env {
  AI: Ai;
  CHAT_HISTORY: KVNamespace;
}

interface ChatRequest {
  messages: { role: 'user' | 'assistant' | 'system'; content: string }[];
  sessionId: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method === 'OPTIONS') {
      return new Response(null, {
        headers: {
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Headers': 'Content-Type, Authorization',
          'Access-Control-Allow-Methods': 'POST, OPTIONS',
        },
      });
    }

    const { messages, sessionId } = await request.json<ChatRequest>();

    // Load conversation history from KV (last 10 turns)
    const history = JSON.parse(
      (await env.CHAT_HISTORY.get(`history:${sessionId}`)) ?? '[]'
    );
    const fullMessages = [
      { role: 'system', content: 'You are a helpful assistant.' },
      ...history.slice(-10),
      ...messages,
    ];

    const aiStream = await env.AI.run('@cf/meta/llama-3.1-8b-instruct', {
      messages: fullMessages,
      stream: true,
      max_tokens: 1024,
    });

    // aiStream is already a ReadableStream of SSE chunks
    // Tee it: one branch for the response, one for history accumulation
    const [clientStream, captureStream] = (aiStream as ReadableStream).tee();

    // Background: accumulate assistant reply and persist to KV
    (async () => {
      const reader = captureStream.getReader();
      const decoder = new TextDecoder();
      let accumulated = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value);
        // SSE lines: "data: {"response":"tok"}\n\n"
        for (const line of chunk.split('\n')) {
          if (line.startsWith('data: ') && !line.includes('[DONE]')) {
            try {
              const parsed = JSON.parse(line.slice(6));
              accumulated += parsed.response ?? '';
            } catch {}
          }
        }
      }
      const updated = [
        ...history,
        ...messages,
        { role: 'assistant', content: accumulated },
      ];
      await env.CHAT_HISTORY.put(
        `history:${sessionId}`,
        JSON.stringify(updated),
        { expirationTtl: 86_400 }
      );
    })();

    return new Response(clientStream, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'X-Accel-Buffering': 'no',
        'Access-Control-Allow-Origin': '*',
      },
    });
  },
};
```

---

## React Native SSE Consumer (react-native-sse)

```typescript
// src/hooks/useAIStream.ts
import EventSource from 'react-native-sse';
import { useCallback, useRef, useState } from 'react';

export function useAIStream(workerUrl: string) {
  const [tokens, setTokens] = useState('');
  const [streaming, setStreaming] = useState(false);
  const esRef = useRef<EventSource | null>(null);

  const startStream = useCallback(
    async (userMessage: string, sessionId: string) => {
      // Clean up any prior stream
      esRef.current?.close();
      setTokens('');
      setStreaming(true);

      // Workers AI SSE gateway expects POST — use a custom EventSource
      // that opens a GET request pre-seeded with query params, OR
      // use the fetch-based chunked reader below.
      // Here we POST via fetch and pipe the body to a ReadableStream consumer.
      const response = await fetch(`${workerUrl}/ai-chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: [{ role: 'user', content: userMessage }],
          sessionId,
        }),
      });

      if (!response.body) {
        setStreaming(false);
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      const pump = async () => {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          const chunk = decoder.decode(value, { stream: true });
          for (const line of chunk.split('\n')) {
            if (line.startsWith('data: ') && !line.includes('[DONE]')) {
              try {
                const parsed = JSON.parse(line.slice(6));
                if (parsed.response) {
                  setTokens((prev) => prev + parsed.response);
                }
              } catch {}
            }
          }
        }
        setStreaming(false);
      };

      pump().catch(() => setStreaming(false));
    },
    [workerUrl]
  );

  const abort = useCallback(() => {
    esRef.current?.close();
    setStreaming(false);
  }, []);

  return { tokens, streaming, startStream, abort };
}
```

---

## Chat UI Component

```typescript
// src/components/AIChat.tsx
import React, { useState } from 'react';
import { FlatList, TextInput, TouchableOpacity, Text, View } from 'react-native';
import { useAIStream } from '../hooks/useAIStream';

const WORKER_URL = 'https://your-worker.workers.dev';

interface Message { id: string; role: 'user' | 'assistant'; content: string }

export function AIChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const sessionId = React.useRef(Math.random().toString(36).slice(2)).current;
  const { tokens, streaming, startStream, abort } = useAIStream(WORKER_URL);

  const send = () => {
    const text = input.trim();
    if (!text || streaming) return;
    setInput('');
    setMessages((prev) => [
      ...prev,
      { id: Date.now().toString(), role: 'user', content: text },
    ]);
    startStream(text, sessionId);
  };

  const allMessages: Message[] = [
    ...messages,
    ...(streaming || tokens
      ? [{ id: 'streaming', role: 'assistant' as const, content: tokens || '…' }]
      : []),
  ];

  return (
    <View style={{ flex: 1 }}>
      <FlatList
        data={allMessages}
        keyExtractor={(m) => m.id}
        renderItem={({ item }) => (
          <View style={{ alignSelf: item.role === 'user' ? 'flex-end' : 'flex-start' }}>
            <Text>{item.content}</Text>
          </View>
        )}
      />
      <TextInput value={input} onChangeText={setInput} onSubmitEditing={send} />
      {streaming ? (
        <TouchableOpacity onPress={abort}><Text>Stop</Text></TouchableOpacity>
      ) : (
        <TouchableOpacity onPress={send}><Text>Send</Text></TouchableOpacity>
      )}
    </View>
  );
}
```

---

## Rate Limiting with Cloudflare Workers Rate Limiter

```typescript
// Add to the Worker fetch handler before calling AI
import { RateLimit } from '@cloudflare/workers-rate-limiter';

// wrangler.toml: [[rate_limiting]] binding = "RATE_LIMITER"
const { success } = await env.RATE_LIMITER.limit({ key: sessionId });
if (!success) {
  return new Response('Too many requests', { status: 429 });
}
```

---

## Anti-patterns

- **Calling `ai.run()` without `stream: true`** on long prompts — the Worker CPU limit (30 s on paid, 10 ms on free) will terminate the request before the model finishes.
- **Storing full conversation history in the request body** — tokens balloon quickly; use a KV or D1 cursor keyed to `sessionId` instead.
- **Displaying raw SSE lines in the UI** — always parse `JSON.parse(line.slice(6)).response` before appending to the chat buffer.
- **No abort support** — users who tap "stop" need `reader.cancel()` called; otherwise the Worker continues computing tokens billed to your account.

---

## Gotchas

- `response.body.getReader()` requires React Native ≥ 0.73 with the New Architecture on Android (Fabric + JSI). On the Old Architecture, fall back to `react-native-sse` with a GET endpoint.
- Workers AI streaming responses include a terminal `data: [DONE]` line — guard all `JSON.parse` calls with try/catch.
- The `@cf/meta/llama-3.1-8b-instruct` model has a 4 096 context window; submitting histories larger than ~3 000 tokens causes silent truncation.
- On iOS, the TCP connection is torn down when the app enters the background. The in-progress stream is lost. Show a "generation paused" indicator and resume on `AppState` foreground event.

---

## Verification

```bash
curl -X POST https://your-worker.workers.dev/ai-chat \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Say hi"}],"sessionId":"test1"}' \
  --no-buffer

# Expected incremental output:
# data: {"response":"Hi"}
# data: {"response":"!"}
# data: [DONE]
```

---

## Related

- `cloudflare-workers-ai-mobile-inference-edge.md`
- `react-native-workers-sse-event-stream.md`
- `workers-ai-push-notification-personalization.md`
- `react-native-durable-objects-realtime.md`
- `mobile-network-resilience-cloudflare-workers.md`

---

## Sources

- Workers AI streaming: https://developers.cloudflare.com/workers-ai/get-started/workers-wrangler/#stream-the-response
- Workers AI models: https://developers.cloudflare.com/workers-ai/models/
- React Native 0.73 Streams: https://reactnative.dev/blog/2023/12/06/0.73-release#fetch-streaming
- Cloudflare Rate Limiting: https://developers.cloudflare.com/workers/runtime-apis/bindings/rate-limit/
