# llamacpp-streaming-fetch-undici-timeout

**Issue:** long-generation-empty-response / undici-headers-timeout
**Date:** 2026-08-14
**Status:** verified-live

## Symptom
A harness or client calling `llama-server`'s `/v1/chat/completions` in
**non-streaming mode** for a long generation (reasoning models, 5000+ tokens)
returns an empty response after exactly **5 minutes**, with `finish_reason: stop`
and no error. The model was healthy and generating — the client never got the
text.

## Root cause
Node's `fetch` (undici) has a default **`headersTimeout: 300000`** (5 min). In
non-streaming mode, the response headers are only emitted at *completion*.
A 5+ minute generation exceeds the timer → the request is terminated → the
caller sees an empty body. Streaming responses send headers immediately and
drip deltas, so the timer never arms against them.

## Fix
Always request **`stream: true`** from `llama-server` for any generation that
might exceed a few minutes (reasoning/thinking models, long code, agentic
loops). Parse SSE `data:` lines and accumulate `delta.content` (and
`delta.tool_calls[i].function.arguments` fragments by index for tool calls).

```js
const res = await fetch(URL, { method:'POST', body: JSON.stringify({ ..., stream:true }) });
const reader = res.body.getReader();
let buf='', text='';
for (;;) {
  const { done, value } = await reader.read();
  if (done) break;
  buf += new TextDecoder().decode(value, { stream:true });
  const lines = buf.split('\n'); buf = lines.pop();
  for (const line of lines) {
    if (!line.startsWith('data: ')) continue;
    const p = line.slice(6).trim();
    if (p === '[DONE]') continue;
    const ch = JSON.parse(p);
    const d = ch.choices?.[0]?.delta;
    if (d?.content) text += d.content;
  }
}
```

## Verification
- Non-streaming 6k-token generation: empty after 300s.
- Same prompt streaming: full text returned.

## Gotchas
- Reasoning models that put their thinking in `reasoning_content` will burn
  the whole budget thinking and never emit `content`. Either raise `max_tokens`
  generously (6000+) or control the thinking budget via the model's system
  directive (e.g. Muse Glimmer: `Reasoning: low`) before relying on streaming.
- Anthropic-format proxies that wrap an OpenAI streaming upstream must also
  **surface upstream 5xx as errors**, not convert them into empty SSE streams —
  otherwise a backend outage looks identical to "model returned nothing."

## Related
- `ollama-corrupts-local-chatglm-gguf`
