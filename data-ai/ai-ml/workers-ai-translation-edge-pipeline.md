# Workers AI Translation Edge Pipeline

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
You need real-time multilingual translation for user-generated content, UI strings, or chat messages at the edge — with sub-100 ms p50 latency — without round-tripping to a third-party translation API.

## Context
Cloudflare Workers AI hosts the `@cf/meta/m2m100-1.2b` model (multilingual NMT, 100 languages) directly on Cloudflare's edge network. Combined with KV caching for repeated phrases and language-detection heuristics, you can build a translation pipeline that processes most requests from cache and falls back to inference for novel content. The `m2m100` model accepts explicit `source_lang` and `target_lang` codes (ISO 639-1) and returns a translated string in the `translated_text` field.

## Language Detection via Trigram Heuristics

Run a lightweight trigram-based language detector in the Worker before invoking the model. This avoids a round-trip to the AI model when the source language is already known from context (e.g., `Accept-Language` header) or when the text is already in the target language.

```typescript
// src/translation/detect-language.ts
const COMMON_TRIGRAMS: Record<string, string[]> = {
  en: ['the', 'and', 'ing', 'ion', 'ent'],
  es: ['que', 'de ', ' de', 'los', 'las'],
  fr: ['les', 'des', ' de', 'ent', 'que'],
  de: ['der', 'die', 'und', 'ein', 'ich'],
  pt: ['que', 'de ', 'os ', 'as ', 'do '],
  it: ['che', ' di', 'di ', 'ion', 'del'],
  zh: ['的', '是', '了', '在', '不'],
  ja: ['し', 'の', 'て', 'い', 'を'],
};

export function detectLanguage(text: string): string | null {
  const lower = text.toLowerCase();
  let bestLang = null;
  let bestScore = -Infinity;
  for (const [lang, trigrams] of Object.entries(COMMON_TRIGRAMS)) {
    const score = trigrams.reduce((s, t) => s + (lower.includes(t) ? 1 : 0), 0);
    if (score > bestScore) { bestScore = score; bestLang = lang; }
  }
  return bestScore >= 2 ? bestLang : null;
}
```

## KV-Backed Translation Cache

Cache translations keyed by `{sourceLang}:{targetLang}:{sha256(normalizedText)}`. Use a 24-hour TTL for static UI strings and a 5-minute TTL for dynamic content.

```typescript
// src/translation/cache.ts
interface Env {
  TRANSLATION_CACHE: KVNamespace;
}

export async function getCachedTranslation(
  env: Env,
  text: string,
  sourceLang: string,
  targetLang: string
): Promise<string | null> {
  const key = await buildCacheKey(text, sourceLang, targetLang);
  return env.TRANSLATION_CACHE.get(key);
}

export async function setCachedTranslation(
  env: Env,
  text: string,
  sourceLang: string,
  targetLang: string,
  translated: string,
  ttlSeconds = 86400
): Promise<void> {
  const key = await buildCacheKey(text, sourceLang, targetLang);
  await env.TRANSLATION_CACHE.put(key, translated, { expirationTtl: ttlSeconds });
}

async function buildCacheKey(text: string, src: string, tgt: string): Promise<string> {
  const normalized = text.trim().toLowerCase();
  const hashBuffer = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(normalized));
  const hashHex = Array.from(new Uint8Array(hashBuffer))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
  return `tx:${src}:${tgt}:${hashHex.slice(0, 16)}`;
}
```

## Calling the Workers AI M2M100 Model

Use the `AI` binding to run inference. Chunk long texts at sentence boundaries since M2M100 performs poorly on inputs exceeding ~512 tokens.

```typescript
// src/translation/translate.ts
interface Env {
  AI: Ai;
  TRANSLATION_CACHE: KVNamespace;
}

interface TranslationResult {
  translated_text: string;
}

export async function translateText(
  env: Env,
  text: string,
  sourceLang: string,
  targetLang: string
): Promise<string> {
  if (sourceLang === targetLang) return text;

  const cached = await getCachedTranslation(env, text, sourceLang, targetLang);
  if (cached) return cached;

  const result = await env.AI.run('@cf/meta/m2m100-1.2b', {
    text,
    source_lang: sourceLang,
    target_lang: targetLang,
  }) as TranslationResult;

  const translated = result.translated_text;
  await setCachedTranslation(env, text, sourceLang, targetLang, translated);
  return translated;
}

// Re-export cache helpers used above
import { getCachedTranslation, setCachedTranslation } from './cache';
```

## Batch Translation of Multiple Strings

Translate multiple UI strings in parallel with `Promise.all`. Use a concurrency limiter to avoid saturating the AI binding with too many simultaneous inference calls.

```typescript
// src/translation/batch-translate.ts
interface Env {
  AI: Ai;
  TRANSLATION_CACHE: KVNamespace;
}

async function translateBatch(
  env: Env,
  texts: string[],
  sourceLang: string,
  targetLang: string,
  concurrency = 5
): Promise<string[]> {
  const results: string[] = new Array(texts.length);
  const queue = texts.map((text, i) => ({ text, i }));
  const inFlight: Promise<void>[] = [];

  async function processOne(item: { text: string; i: number }): Promise<void> {
    results[item.i] = await translateText(env, item.text, sourceLang, targetLang);
  }

  while (queue.length > 0 || inFlight.length > 0) {
    while (inFlight.length < concurrency && queue.length > 0) {
      const item = queue.shift()!;
      const p = processOne(item).then(() => {
        inFlight.splice(inFlight.indexOf(p), 1);
      });
      inFlight.push(p);
    }
    if (inFlight.length > 0) await Promise.race(inFlight);
  }

  return results;
}

import { translateText } from './translate';
```

## Full Worker Request Handler

Wire language detection, cache lookup, model inference, and response together in a single fetch handler.

```typescript
// src/index.ts
interface Env {
  AI: Ai;
  TRANSLATION_CACHE: KVNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('POST only', { status: 405 });

    const { text, source_lang, target_lang } = await request.json<{
      text: string;
      source_lang?: string;
      target_lang: string;
    }>();

    if (!text || !target_lang) {
      return Response.json({ error: 'text and target_lang are required' }, { status: 400 });
    }

    const sourceLang = source_lang ?? detectLanguage(text) ?? 'en';
    const translated = await translateText(env, text, sourceLang, target_lang);

    return Response.json({ translated_text: translated, source_lang: sourceLang });
  },
};

import { detectLanguage } from './translation/detect-language';
import { translateText } from './translation/translate';
```

## Anti-patterns
- Sending the entire page HTML to the translation model — translate only visible strings
- Using a single global cache key for multi-tenant content — different customers may have custom overrides
- Ignoring the model's 512-token limit — truncated inputs produce nonsensical partial translations
- Calling `AI.run` serially in a loop rather than batching with concurrency limiting
- Caching translations indefinitely without TTL — promotional copy changes after campaigns end

## Gotchas
- `@cf/meta/m2m100-1.2b` uses BCP-47 short codes (e.g., `zh` for Chinese), not the full locale tag
- The model does not handle code-mixed text well — detect and skip translation for strings containing >30% non-alphabetic characters
- Workers AI inference cold-start adds ~200 ms on the first request to a PoP; subsequent requests are warm
- KV `get` counts toward KV read limits — use the `cacheTtl` option to serve from the edge cache tier for hot keys
- Long texts benefit from splitting at sentence boundaries (`. `, `? `, `! `) before inference to improve quality

## Verification
1. POST `{"text": "Hello world", "target_lang": "es"}` and assert `translated_text` is `"Hola mundo"`.
2. Send the same request twice and assert the second response has `X-Cache-Hit: true` (add this header in handler).
3. Send a 600-word input and confirm no truncation artifacts appear in the output.
4. Load-test 50 concurrent translation requests with `wrk` and confirm p99 < 800 ms.

## Related
- [LLM For Translation](llm-for-translation.md)
- [Automatic Language Detection I18n Routing](automatic-language-detection-i18n-routing.md)
- [Workers AI Queue Batch Processing](workers-ai-queue-batch-processing.md)
- [Semantic Caching Patterns](semantic-caching-patterns.md)

## Sources
- https://developers.cloudflare.com/workers-ai/models/m2m100-1.2b/
- https://developers.cloudflare.com/kv/api/read-key-value-pairs/#cache-ttl
- https://developers.cloudflare.com/workers-ai/get-started/workers-wrangler/
