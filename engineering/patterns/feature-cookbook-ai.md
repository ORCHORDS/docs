# feature-cookbook-ai

**Issue:** Common AI/ML patterns — chat, embeddings, classification
**Date:** 2026-08-09
**Status:** documented

## Symptom
You want to add a chatbot. You call OpenAI directly. The
bill is huge. The latency is 2s. The user waits. You want
to use Workers AI, but the model is small. You want to
fine-tune, but you don't have data. You want to cache, but
the responses are unique.

## Root cause
**AI features have tradeoffs.** Cost, latency, quality,
privacy all matter.

**Source:** Various AI/ML guides.

## The "chat" pattern with OpenAI

```ts
import OpenAI from 'openai';

const openai = new OpenAI({ apiKey: env.OPENAI_API_KEY });

async function chat(messages: Message[]): Promise<string> {
  const response = await openai.chat.completions.create({
    model: 'gpt-4',
    messages,
    temperature: 0.7,
  });

  return response.choices[0].message.content;
}
```

Simple, expensive, accurate.

## The "chat" pattern with Workers AI

```ts
async function chat(messages: Message[]): Promise<string> {
  const response = await env.AI.run('@cf/meta/llama-2-7b-chat-int8', {
    messages,
  });

  return response.response;
}
```

Cheap, fast, less accurate.

## The "embeddings" pattern

For semantic search or similarity:
```ts
async function getEmbedding(text: string, env: Env): Promise<number[]> {
  const response = await env.AI.run('@cf/google/embedding-gecko-300m', {
    text,
  });

  return response.data[0];
}
```

The embedding is a 768-dim vector.

## The "RAG" pattern

For Q&A with knowledge base:
```ts
async function ragAnswer(query: string, env: Env): Promise<string> {
  // 1. Embed the query
  const queryEmbedding = await getEmbedding(query, env);

  // 2. Find similar documents
  const docs = await env.VECTORIZE.query(queryEmbedding, {
    topK: 5,
    filter: { tenantId: 't_123' },
  });

  // 3. Build the context
  const context = docs.matches.map((m) => m.metadata.text).join('\n\n');

  // 4. Generate the answer
  const response = await env.AI.run('@cf/meta/llama-2-7b-chat-int8', {
    messages: [
      { role: 'system', content: `Answer based on:\n${context}` },
      { role: 'user', content: query },
    ],
  });

  return response.response;
}
```

The RAG pattern grounds the answer in your data.

## The "streaming" pattern

For long responses, stream:
```ts
export async function streamingChat(messages: Message[]): Promise<Response> {
  const stream = await env.AI.run('@cf/meta/llama-2-7b-chat-int8', {
    messages,
    stream: true,
  });

  return new Response(stream, {
    headers: { 'content-type': 'text/event-stream' },
  });
}
```

The user sees the response as it's generated.

## The "classification" pattern

For categorization (spam, sentiment, etc.):
```ts
async function classifySentiment(text: string, env: Env): Promise<'positive' | 'negative' | 'neutral'> {
  const response = await env.AI.run('@cf/huggingface/distilbert-sst-2-int8', {
    text,
  });

  // response: [{ label: 'POSITIVE', score: 0.9 }, { label: 'NEGATIVE', score: 0.1 }]
  return response[0].label === 'POSITIVE' ? 'positive' : 'negative';
}
```

The model returns a label + score.

## The "image generation" pattern

For text-to-image:
```ts
async function generateImage(prompt: string, env: Env): Promise<string> {
  const response = await env.AI.run('@cf/stabilityai/stable-diffusion-xl-base-1.0', {
    prompt,
  });

  // response: ReadableStream (binary)
  return response;
}
```

The model generates an image from text.

## The "speech-to-text" pattern

For transcription:
```ts
async function transcribe(audio: ArrayBuffer, env: Env): Promise<string> {
  const response = await env.AI.run('@cf/openai/whisper', {
    audio: [...new Uint8Array(audio)],
  });

  return response.text;
}
```

The model transcribes the audio.

## The "caching" pattern for AI

For repeated queries, cache the response:
```ts
async function chatWithCache(messages: Message[], env: Env): Promise<string> {
  // 1. Generate a cache key
  const key = `chat:${crypto.subtle.digest('SHA-256', new TextEncoder().encode(JSON.stringify(messages))).then(b => Buffer.from(b).toString('hex'))}`;

  // 2. Check the cache
  const cached = await env.KV.get(key);
  if (cached) return cached;

  // 3. Generate
  const response = await chat(messages, env);

  // 4. Cache
  await env.KV.put(key, response, { expirationTtl: 86400 });  // 1 day

  return response;
}
```

For identical queries, the response is cached.

## The "rate limiting" pattern for AI

For OpenAI's rate limits:
```ts
class OpenAIRateLimiter {
  private inflight = 0;
  private maxInflight = 10;

  async execute<T>(fn: () => Promise<T>): Promise<T> {
    while (this.inflight >= this.maxInflight) {
      await sleep(100);
    }
    this.inflight++;
    try {
      return await fn();
    } finally {
      this.inflight--;
    }
  }
}
```

The limiter ensures you don't exceed the rate limit.

## The "cost" pattern

For OpenAI:
- **gpt-4:** $0.03/1k input tokens, $0.06/1k output tokens
- **gpt-3.5-turbo:** $0.0005/1k input, $0.0015/1k output

For Workers AI:
- **llama-2-7b:** $0.005/1k tokens
- **mistral-7b:** $0.005/1k tokens

For 1M requests/day with 1k input + 500 output tokens:
- **gpt-4:** $30k/month (input) + $30k/month (output) = $60k/month
- **gpt-3.5-turbo:** $500/month (input) + $750/month (output) = $1.25k/month
- **Workers AI:** $5/month (input) + $5/month (output) = $10/month

Workers AI is 1000x cheaper than gpt-3.5, 6000x cheaper
than gpt-4.

## The "prompt engineering" pattern

For better results, use structured prompts:
```ts
const systemPrompt = `You are a helpful assistant. Use the following guidelines:

1. Be concise.
2. Use formal language.
3. If you don't know, say so.

Format your response as:
- Summary: <summary>
- Details: <details>
- Action items: <list>
`;

const response = await openai.chat.completions.create({
  model: 'gpt-4',
  messages: [
    { role: 'system', content: systemPrompt },
    { role: 'user', content: query },
  ],
});
```

A good system prompt is the difference between good and
bad results.

## The "evaluation" pattern

For measuring quality:
```ts
async function evaluateModel(prompts: Prompt[], expectedAnswers: string[]): Promise<{ accuracy: number }> {
  let correct = 0;
  for (let i = 0; i < prompts.length; i++) {
    const response = await chat(prompts[i]);
    if (response === expectedAnswers[i]) correct++;
  }
  return { accuracy: correct / prompts.length };
}
```

Evaluate the model on a test set.

## The "fine-tuning" pattern

For domain-specific models:
1. Collect training data (prompt + completion pairs)
2. Fine-tune a base model
3. Deploy + evaluate

```ts
const fineTune = await openai.fineTuning.jobs.create({
  training_file: 'file-abc',
  model: 'gpt-3.5-turbo',
});
```

Fine-tuning is expensive; use it for proven use cases.

## The "guardrails" pattern

For safety, use guardrails:
```ts
const blocked = ['harmful', 'illegal', 'unethical'];

function isSafe(text: string): boolean {
  return !blocked.some((word) => text.toLowerCase().includes(word));
}

// Use as a check
if (!isSafe(userInput)) {
  return new Response('Input blocked', { status: 400 });
}
```

Or use OpenAI's moderation API:
```ts
const moderation = await openai.moderations.create({ input: userInput });
if (moderation.results[0].flagged) {
  return new Response('Input blocked', { status: 400 });
}
```

## Verification
- **Test:** AI returns the expected output
- **Live:** AI latency is monitored
- **Audit:** Monthly cost review

## Gotchas
- **The "AI for everything" anti-pattern.** Not every
  feature needs AI. Use it where it adds value.
- **The "AI without grounding" anti-pattern.** A model that
  hallucinates is worse than no AI. Use RAG.
- **The "AI without rate limit" anti-pattern.** The bill
  can spike. Rate limit per user.
- **The "AI without cost monitoring" anti-pattern.** Costs
  add up. Monitor daily.
- **The "AI without fallback" anti-pattern.** If the AI is
  down, the feature is broken. Have a fallback.

## Related
- `ml-inference-edge.md`
- `feature-store-vs-cache.md`
- `cost-optimization-cloudflare.md`
- `rate-limiting-strategies.md`
- Workers AI: https://developers.cloudflare.com/workers-ai/
- Vectorize: https://developers.cloudflare.com/vectorize/
- OpenAI: https://platform.openai.com/docs
