# feature-cookbook-ai-ml-detail

**Issue:** AI/ML — inference, fine-tuning, evaluation
**Date:** 2026-08-09
**Status:** documented

## Symptom
You integrate an LLM. The model hallucinates. The
response is wrong. The user complains. You wish the
model was better.

## Root cause
**LLMs hallucinate.** Use guardrails + evaluation.

**Source:** Various AI/ML guides.

## The "prompt" pattern

For a prompt:
```ts
const prompt = `You are a helpful assistant. Answer the question based on the context.

Context: ${context}

Question: ${question}

Answer:`;

const response = await env.AI.run('@cf/meta/llama-2-7b-chat-int8', {
  prompt,
  max_tokens: 256,
});
```

The prompt is structured.

## The "system prompt" pattern

For a system prompt:
```ts
const response = await env.AI.run('@cf/meta/llama-2-7b-chat-int8', {
  messages: [
    { role: 'system', content: 'You are a customer support agent. Be concise and helpful.' },
    { role: 'user', content: question },
  ],
});
```

The system prompt is separate.

## The "few-shot" pattern

For few-shot:
```ts
const response = await env.AI.run('@cf/meta/llama-2-7b-chat-int8', {
  messages: [
    { role: 'system', content: 'You are a sentiment classifier. Output "positive" or "negative".' },
    { role: 'user', content: 'I love this product!' },
    { role: 'assistant', content: 'positive' },
    { role: 'user', content: 'This is terrible.' },
    { role: 'assistant', content: 'negative' },
    { role: 'user', content: text },
  ],
});
```

Few-shot examples are included.

## The "RAG" pattern

For Retrieval-Augmented Generation:
```ts
async function rag(query: string, env: Env): Promise<string> {
  // 1. Embed the query
  const queryEmbedding = await env.AI.run('@cf/baai/bge-base-en-v1.5', { text: query });

  // 2. Find similar docs
  const docs = await env.VECTORIZE!.query(queryEmbedding.data[0], { topK: 5 });

  // 3. Build the prompt
  const context = docs.matches.map(d => d.metadata.text).join('\n');
  const prompt = `Use the context to answer:\n\n${context}\n\nQ: ${query}\nA:`;

  // 4. Generate
  const response = await env.AI.run('@cf/meta/llama-2-7b-chat-int8', { prompt });
  return response.response;
}
```

The model is grounded in retrieved docs.

**Source:** RAG:
https://docs.llamaindex.ai/en/stable/getting_started/concepts/

## The "model selection" pattern

For model selection:
- **LLaMA 2 7B:** Fast, cheap, OK
- **LLaMA 2 13B:** Slower, more accurate
- **Mistral 7B:** Fast, good
- **OpenAI GPT-4o:** Most accurate, expensive
- **Anthropic Claude:** Quality, long context

For most apps, **LLaMA 2 7B** is enough.

## The "streaming" pattern

For streaming:
```ts
const response = await env.AI.run('@cf/meta/llama-2-7b-chat-int8', {
  prompt,
  stream: true,
});

// Read the stream
const reader = response.getReader();
const decoder = new TextDecoder();
let text = '';
while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  text += decoder.decode(value, { stream: true });
}
```

The response is streamed.

## The "AI cost" pattern

For cost:
- **LLaMA 2 7B:** ~$0.005 / 1M tokens
- **OpenAI GPT-4o:** ~$5 / 1M tokens
- **Cost = tokens:** Reduce tokens to reduce cost

```ts
// Truncate the input
const truncated = text.slice(0, 2000);
```

The cost is reduced.

## The "AI guardrail" pattern

For guardrails:
- **Input validation:** Block bad input
- **Output validation:** Block bad output
- **Rate limit:** Per user
- **Cost limit:** Per user

```ts
async function isInputSafe(text: string, env: Env): Promise<boolean> {
  // Use a moderation API or simple check
  if (text.includes('hack')) return false;
  return true;
}
```

The input is validated.

## The "AI observability" pattern

For observability:
- **Tokens:** Input + output
- **Latency:** Per request
- **Cost:** Per request
- **Quality:** User feedback
- **Hallucination rate:** Eval set

```ts
metrics.histogram('ai.tokens', tokens, { direction: 'input' });
metrics.histogram('ai.latency_ms', latency);
```

The AI is monitored.

## The "AI evaluation" pattern

For evaluation:
- **Test set:** Known questions + answers
- **Automated:** Run the test set on every change
- **Human:** Periodic review

```ts
async function evaluate(env: Env): Promise<void> {
  for (const test of TEST_SET) {
    const response = await rag(test.question, env);
    const score = await compareToExpected(response, test.expected, env);
    logEvent('ai.eval', 'info', { question: test.question, score });
  }
}
```

The AI is evaluated.

## The "AI caching" pattern

For caching:
- **Identical input:** Same output (sometimes)
- **Embed + cache:** By embedding

```ts
async function cachedAI(prompt: string, env: Env): Promise<string> {
  const cacheKey = `ai:${hash(prompt)}`;
  const cached = await env.KV!.get(cacheKey);
  if (cached) return cached;

  const response = await env.AI.run('@cf/meta/llama-2-7b-chat-int8', { prompt });
  await env.KV!.put(cacheKey, response.response, { expirationTtl: 86400 });
  return response.response;
}
```

The response is cached.

## The "AI observability - safety" pattern

For safety:
- **PII detection:** Don't include PII
- **Toxicity filter:** Block toxic output
- **Bias check:** Periodic audit
- **Rate limit:** Per user

The AI is safe.

## The "AI fallback" pattern

For fallback (vendor down):
```ts
async function aiWithFallback(prompt: string, env: Env): Promise<string> {
  try {
    return await env.AI.run('@cf/meta/llama-2-7b-chat-int8', { prompt });
  } catch (err) {
    // Fallback to OpenAI
    return await callOpenAI(prompt, env);
  }
}
```

The fallback is in place.

## The "AI anti-pattern" anti-patterns

### 1. No guardrails
- **Issue:** Bad input / output
- **Fix:** Validate

### 2. No evaluation
- **Issue:** Quality drifts
- **Fix:** Eval set

### 3. Too large model
- **Issue:** Cost
- **Fix:** Smallest model

### 4. No caching
- **Issue:** Repeat work
- **Fix:** Cache by prompt

### 5. Hallucination
- **Issue:** Wrong answers
- **Fix:** RAG + citations

## Verification
- **Test:** Prompt returns correct
- **Test:** Cost is acceptable
- **Test:** Latency is acceptable
- **Live:** AI metrics monitored
- **Audit:** Quarterly AI review

## Gotchas
- **The "no guardrails" anti-pattern.** Validate.
- **The "no evaluation" anti-pattern.** Eval set.
- **The "too large" anti-pattern.** Smallest model.

## Related
- `feature-cookbook-ai.md`
- `feature-cookbook-rag.md` (planned)
- `feature-cookbook-frontend.md`
- `feature-cookbook-cost-optimization.md`
- `cloudflare/workers-ai.md` (planned)
- CF AI: https://developers.cloudflare.com/workers-ai/
- OpenAI: https://platform.openai.com/
- RAG: https://docs.llamaindex.ai/en/stable/
