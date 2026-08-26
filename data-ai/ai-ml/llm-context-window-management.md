# llm-context-window-management

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

A request to an LLM fails with `context_length_exceeded` or an
equivalent 400 error mid-conversation. Alternatively, early turns
silently drop from the context, causing the model to contradict
itself or forget user preferences set at the start of a session.
In a Cloudflare Worker AI Gateway session, the accumulated
history grows until the Worker hits its 128 MB memory limit.

## Context

Every model has a hard token ceiling (4 k to 1 M+ tokens).
Beyond that the provider errors or silently truncates from the
left. Effective context management: count tokens before sending,
choose a truncation or compression strategy, and preserve KV
cache hits to avoid full-prompt latency on every turn. In a
stateless Cloudflare Worker, history is stored in KV or D1 and
reconstructed per request.

## 1  Token counting

```typescript
import { encoding_for_model } from "tiktoken";

const enc = encoding_for_model("gpt-4o");

function countTokens(messages: ChatMessage[]): number {
  // 4 tokens overhead per message (OpenAI convention)
  return messages.reduce(
    (total, m) =>
      total + 4 + enc.encode(m.content ?? "").length,
    3,  // 3 tokens for priming reply
  );
}

// Cloudflare Workers AI — no tiktoken; approximate:
function approxTokens(text: string): number {
  return Math.ceil(text.length / 4);
}
```

Always count *before* calling the API, not after; you cannot
recover a 400 error cheaply.

## 2  Sliding window truncation

```typescript
const SYSTEM_RESERVE = 512;   // tokens for system prompt
const REPLY_RESERVE  = 1_024; // expected reply headroom
const MODEL_LIMIT    = 128_000;
const MAX_HISTORY    = MODEL_LIMIT - SYSTEM_RESERVE - REPLY_RESERVE;

function slidingWindow(
  history: ChatMessage[],
  systemMsg: ChatMessage,
): ChatMessage[] {
  const kept: ChatMessage[] = [];
  let used = countTokens([systemMsg]);

  // Walk newest-first; always keep the most recent turn
  for (let i = history.length - 1; i >= 0; i--) {
    const cost = countTokens([history[i]]);
    if (used + cost > MAX_HISTORY) break;
    kept.unshift(history[i]);
    used += cost;
  }
  return [systemMsg, ...kept];
}
```

## 3  Summarisation of old turns

```typescript
async function summariseOldTurns(
  turns: ChatMessage[],
): Promise<ChatMessage> {
  const joined = turns
    .map((m) => `${m.role}: ${m.content}`)
    .join("\n");
  const res = await llm.complete({
    messages: [
      {
        role: "system",
        content: "Summarise the following conversation excerpt "
                 + "in ≤ 150 words, preserving key facts.",
      },
      { role: "user", content: joined },
    ],
    max_tokens: 200,
  });
  return {
    role: "system",
    content: "[Earlier conversation summary]\n"
             + res.choices[0].message.content,
  };
}
```

Strategy: when `countTokens(history) > SOFT_LIMIT`, summarise
the oldest 50 % of turns into a single synthetic system message,
then continue appending new turns normally.

## 4  KV cache efficiency

KV cache reuse cuts latency by 50–80 % on long static prefixes.
Rules:
1. Put the system prompt first and keep it byte-for-byte
   identical across requests — even a trailing space breaks
   the cache.
2. Place retrieved RAG context after the system prompt and
   before the user turn; if the retrieved docs are the same,
   the cache hit covers them.
3. Never interleave static and dynamic content; the cache
   is a prefix match, not a diff.

```
Request layout for best cache hit rate:
  [system prompt — static]          <- cached
  [retrieved context — often static] <- cached if same docs
  [conversation history — dynamic]   <- not cached
  [current user turn — dynamic]      <- not cached
```

## 5  Prompt compression

```typescript
// LLMLingua-style compression: keep salient tokens,
// drop filler words — target 50 % ratio
import { PromptCompressor } from "llmlingua";

const compressor = new PromptCompressor();

async function compressContext(
  docs: string[],
  targetRatio = 0.5,
): Promise<string> {
  const { compressed_prompt } = await compressor.compress_prompt(
    docs,
    { ratio: targetRatio, condition_compare: true },
  );
  return compressed_prompt;
}
```

Use compression only on the retrieved RAG context, not on the
conversation history — compressing user turns degrades model
understanding of the user's intent.

## Anti-patterns

- Dropping messages from the *beginning* without summarising —
  the model loses system instructions and initial user intent.
- Counting characters instead of tokens — off by 2–4× for
  code or non-Latin text.
- Storing full conversation history in a Worker's module-scope
  variable — resets on every Worker spawn; use KV or D1.
- Trusting `max_tokens` to prevent overflows — it controls
  the *output* length, not the input context.

## Gotchas

- Token count differs per model family; a GPT-4 token count is
  not portable to a Workers AI model. Use the correct encoder.
- The AI Gateway session ID in Cloudflare does not persist
  history; it is a routing and caching key only. You must
  store `messages[]` yourself in KV or Durable Objects.
- Models with very large context windows (>100 k tokens) still
  show the "lost in the middle" effect — retrieval accuracy
  drops for content placed in the centre of the window.
- Tiktoken is not available in the Cloudflare Workers runtime;
  bundle a character-based approximation or a WASM tokeniser.

## Verification

- Assert `countTokens([systemMsg, ...history]) < MODEL_LIMIT`
  in a pre-flight check before every API call.
- In tests, fill history to 110 % of `MAX_HISTORY` and confirm
  `slidingWindow` drops the oldest turns correctly.
- Measure KV cache hit rate in AI Gateway logs; expect ≥ 80 %
  hit rate for the static system prompt prefix.

## Related

- `ai-ml/llm-token-counting.md`
- `ai-ml/context-engineering-systems.md`
- `ai-ml/ai-gateway-caching.md`

## Source URLs (verified 2026-08-17)

- https://developers.cloudflare.com/ai-gateway/
- https://developers.cloudflare.com/kv/
- https://github.com/openai/tiktoken
- https://arxiv.org/abs/2310.05736  (LLMLingua)
- https://arxiv.org/abs/2307.03172  (Lost in the Middle)
