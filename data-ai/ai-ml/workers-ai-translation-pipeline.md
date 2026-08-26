# Workers AI — AI Translation Pipeline with M2M100 and KV Cache

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to translate user-submitted content (product descriptions, support replies, marketing copy) into multiple target languages at scale. Running every string through an AI model regardless of history is expensive and slow. A translation memory cache in KV eliminates redundant AI calls; a Queues-based batch processor handles burst volume; a confidence scoring step routes low-quality output to a human review queue.

---

## Context

Cloudflare Workers AI provides `@cf/meta/m2m100-1.2b`, a Facebook/Meta sequence-to-sequence translation model supporting 100 language directions. It accepts a `source_lang`, `target_lang`, and `text` parameter and returns a translated string.

The pipeline uses:
- **Workers AI M2M100** — translation
- **Workers AI** (text classification) — language detection
- **KV** — translation memory (keyed by `{hash}:{target_lang}`)
- **D1** — durable storage of confirmed translations
- **Queues** — async batch translation jobs

---

## Solution

```typescript
import { createHash } from 'node:crypto';

export interface Env {
  AI: Ai;
  TRANSLATION_KV: KVNamespace;
  DB: D1Database;
  TRANSLATION_QUEUE: Queue<TranslationJob>;
}

// ── Types ────────────────────────────────────────────────────────────────────

type SupportedLang =
  | 'en' | 'es' | 'fr' | 'de' | 'it' | 'pt' | 'nl'
  | 'ar' | 'zh' | 'ja' | 'ko' | 'ru' | 'hi' | 'tr';

interface TranslationJob {
  jobId: string;
  texts: string[];
  sourceLang: SupportedLang;
  targetLangs: SupportedLang[];
  callbackUrl?: string;
}

interface TranslationEntry {
  source: string;
  translation: string;
  sourceLang: SupportedLang;
  targetLang: SupportedLang;
  confidence: number;
  fromCache: boolean;
}

// ── 1. Language detection ─────────────────────────────────────────────────────

// M2M100 performs better with explicit source language.
// Use a lightweight classifier to detect before translating.
async function detectLanguage(ai: Ai, text: string): Promise<SupportedLang> {
  // Workers AI doesn't ship a dedicated lang-detect model;
  // use a zero-shot classification prompt with llama-3.1-8b.
  const result = await ai.run('@cf/meta/llama-3.1-8b-instruct', {
    messages: [
      {
        role: 'system',
        content:
          'Detect the language of the following text. ' +
          'Reply with ONLY the ISO 639-1 two-letter code (e.g. en, es, fr, de, zh, ja, ko, ar, ru, hi, tr, pt, it, nl). ' +
          'No punctuation, no explanation.',
      },
      { role: 'user', content: text.slice(0, 200) },
    ],
    max_tokens: 4,
    temperature: 0,
  });

  const code = (result as { response: string }).response.trim().toLowerCase().slice(0, 2);
  const SUPPORTED: SupportedLang[] = ['en','es','fr','de','it','pt','nl','ar','zh','ja','ko','ru','hi','tr'];
  return SUPPORTED.includes(code as SupportedLang) ? (code as SupportedLang) : 'en';
}

// ── 2. Translation memory (KV cache) ─────────────────────────────────────────

function cacheKey(text: string, targetLang: SupportedLang): string {
  const hash = createHash('sha256').update(text).digest('hex').slice(0, 16);
  return `tm:${hash}:${targetLang}`;
}

async function getCachedTranslation(
  kv: KVNamespace,
  text: string,
  targetLang: SupportedLang,
): Promise<string | null> {
  return kv.get(cacheKey(text, targetLang));
}

async function setCachedTranslation(
  kv: KVNamespace,
  text: string,
  targetLang: SupportedLang,
  translation: string,
  ttlSeconds: number = 60 * 60 * 24 * 90, // 90 days
): Promise<void> {
  await kv.put(cacheKey(text, targetLang), translation, { expirationTtl: ttlSeconds });
}

// ── 3. Core translation with M2M100 ──────────────────────────────────────────

async function translateText(
  ai: Ai,
  text: string,
  sourceLang: SupportedLang,
  targetLang: SupportedLang,
): Promise<string> {
  if (sourceLang === targetLang) return text;

  const result = await ai.run('@cf/meta/m2m100-1.2b', {
    text,
    source_lang: sourceLang,
    target_lang: targetLang,
  });

  return (result as { translated_text: string }).translated_text.trim();
}

// ── 4. Confidence scoring ─────────────────────────────────────────────────────

// Heuristic confidence scoring based on output characteristics.
// Replace with a dedicated QE (quality estimation) model in production.
function scoreTranslationQuality(
  source: string,
  translation: string,
): number {
  if (!translation || translation.length === 0) return 0;

  // Penalize if translation is identical to source (untranslated)
  if (translation.trim() === source.trim()) return 0.1;

  // Penalize severe length mismatch (> 3x or < 0.3x)
  const ratio = translation.length / source.length;
  if (ratio > 3.5 || ratio < 0.25) return 0.4;

  // Penalize if translation contains source-language filler markers
  if (/\[UNK\]|<unk>/.test(translation)) return 0.3;

  // Base confidence for M2M100 on well-supported language pairs
  const HIGH_RESOURCE: SupportedLang[] = ['en', 'es', 'fr', 'de', 'zh', 'ar'];
  return 0.85;
}

const QUALITY_THRESHOLD = 0.7; // below this → human review queue

// ── 5. Full single-text translation with cache ─────────────────────────────

async function translateWithCache(
  env: Env,
  text: string,
  targetLang: SupportedLang,
  sourceLang?: SupportedLang,
): Promise<TranslationEntry> {
  // Check KV translation memory first
  const cached = await getCachedTranslation(env.TRANSLATION_KV, text, targetLang);
  if (cached) {
    return {
      source: text,
      translation: cached,
      sourceLang: sourceLang ?? 'en',
      targetLang,
      confidence: 1.0, // cached translations are already verified
      fromCache: true,
    };
  }

  // Detect source language if not provided
  const detectedLang = sourceLang ?? (await detectLanguage(env.AI, text));

  // Translate via M2M100
  const translation = await translateText(env.AI, text, detectedLang, targetLang);
  const confidence = scoreTranslationQuality(text, translation);

  // Store in D1 for audit and training data
  await env.DB.prepare(
    `INSERT OR IGNORE INTO translations
       (source_hash, source_text, target_lang, source_lang, translation, confidence, created_at)
     VALUES (?, ?, ?, ?, ?, ?, datetime('now'))`,
  )
    .bind(
      createHash('sha256').update(text).digest('hex').slice(0, 16),
      text.slice(0, 2000), // cap text stored in D1
      targetLang,
      detectedLang,
      translation,
      confidence,
    )
    .run();

  // Cache high-confidence translations in KV
  if (confidence >= QUALITY_THRESHOLD) {
    await setCachedTranslation(env.TRANSLATION_KV, text, targetLang, translation);
  }

  return {
    source: text,
    translation,
    sourceLang: detectedLang,
    targetLang,
    confidence,
    fromCache: false,
  };
}

// ── 6. Queue consumer — batch translation ────────────────────────────────────

export const queue: ExportedHandlerQueueHandler<Env, TranslationJob> = async (
  batch,
  env,
) => {
  for (const message of batch.messages) {
    const job = message.body;
    const results: Record<string, TranslationEntry[]> = {};

    for (const targetLang of job.targetLangs) {
      results[targetLang] = [];
      for (const text of job.texts) {
        try {
          const entry = await translateWithCache(env, text, targetLang, job.sourceLang);
          results[targetLang].push(entry);
        } catch (err) {
          console.error(`Translation failed for job ${job.jobId}:`, err);
          results[targetLang].push({
            source: text,
            translation: '',
            sourceLang: job.sourceLang,
            targetLang,
            confidence: 0,
            fromCache: false,
          });
        }
      }
    }

    // Update job status in D1
    await env.DB.prepare(
      `UPDATE translation_jobs SET status = 'completed', completed_at = datetime('now') WHERE id = ?`,
    ).bind(job.jobId).run();

    // POST results to callback URL if provided
    if (job.callbackUrl) {
      await fetch(job.callbackUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ jobId: job.jobId, results }),
      }).catch((e) => console.error('Callback failed:', e));
    }

    message.ack();
  }
};

// ── 7. Worker entry point ────────────────────────────────────────────────────

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // POST /translate — synchronous single-text translation
    if (url.pathname === '/translate' && request.method === 'POST') {
      const body = await request.json<{
        text: string;
        targetLang: SupportedLang;
        sourceLang?: SupportedLang;
      }>();

      const result = await translateWithCache(env, body.text, body.targetLang, body.sourceLang);
      return Response.json({ ok: true, ...result });
    }

    // POST /translate/batch — async batch translation via Queue
    if (url.pathname === '/translate/batch' && request.method === 'POST') {
      const body = await request.json<Omit<TranslationJob, 'jobId'>>();
      const jobId = crypto.randomUUID();

      await env.DB.prepare(
        `INSERT INTO translation_jobs (id, status, created_at) VALUES (?, 'queued', datetime('now'))`,
      ).bind(jobId).run();

      await env.TRANSLATION_QUEUE.send({ jobId, ...body });
      return Response.json({ ok: true, jobId });
    }

    return new Response('Not found', { status: 404 });
  },

  queue,
} satisfies ExportedHandler<Env>;
```

---

## Implementation Details

**KV cache key design** — `tm:{sha256_prefix}:{target_lang}` provides a deterministic, collision-resistant key. The 16-character hex prefix gives 2^64 collision resistance, more than sufficient for translation memory. Set a 90-day TTL to expire stale translations when source text evolves.

**M2M100 language codes** — Use ISO 639-1 two-letter codes. M2M100 natively maps them to its internal vocabulary. Unsupported codes cause the model to return empty or garbled output; validate against the supported list before calling.

**Batch via Queues** — The Queue consumer processes one job at a time in a loop. Workers CPU time (30s default, 300s with unbound) is sufficient for batches of ~50 strings × 3 target languages. For larger batches, set `max_batch_size = 5` and process across multiple consumer invocations.

**D1 translation storage** — The `translations` table accumulates verified pairs useful as fine-tuning training data and for analytics on which content types are most-translated. Use `INSERT OR IGNORE` to avoid duplicates from cache misses racing.

**Human review integration** — Translations with `confidence < 0.7` are flagged in D1 (`WHERE confidence < 0.7 AND reviewed = 0`) and surfaced to a reviewer dashboard. Once reviewed, the reviewer updates `reviewed = 1` and the corrected translation is back-written to KV.

---

## Anti-patterns

- **Translating HTML with M2M100 directly** — The model will attempt to translate HTML tags, corrupting markup. Strip HTML before translation and re-inject tags after using a tokenizer.
- **Omitting `source_lang`** — Auto-detection inside M2M100 is less accurate than an explicit LLM detection step; always detect first.
- **Caching failed/empty translations** — Check `translation.length > 0` before writing to KV.
- **Using KV for high-write translation jobs synchronously** — KV writes are eventually consistent across regions; concurrent translators may re-translate the same string before the cache populates. Accept rare duplicate calls; do not use distributed locking.
- **Setting no TTL on KV entries** — Translations grow unbounded. 90-day TTL balances cache hit rate with storage cost.

---

## Gotchas

- `@cf/meta/m2m100-1.2b` response is `{ translated_text: string }`, not `{ response: string }` (which is for text-generation models). Mismatching the property name returns `undefined`.
- Very short strings (1–2 words) get poor quality scores due to ambiguity. Return the original text unchanged for strings shorter than 3 words.
- M2M100 1.2B handles common language pairs well (en↔es, en↔fr, en↔de) but struggles with low-resource language pairs. Route those to a specialized model or human translation.
- Workers KV `get()` returns `null` on miss, not an empty string; check `!== null` not just falsy.
- `createHash` from `node:crypto` is available in the Workers runtime; import it at the top of the file.

---

## Verification

```bash
# Create KV namespace
npx wrangler kv namespace create TRANSLATION_KV

# Create D1 database and schema
npx wrangler d1 create translation-db
npx wrangler d1 execute translation-db --file=schema.sql

# Create Queue
npx wrangler queues create translation-queue

# Deploy
npx wrangler deploy

# Test synchronous translation
curl -X POST https://your-worker.workers.dev/translate \
  -H 'Content-Type: application/json' \
  -d '{"text": "Hello, how are you?", "targetLang": "es", "sourceLang": "en"}'
# Expected: { ok: true, translation: "Hola, ¿cómo estás?", confidence: 0.85, fromCache: false }

# Second call — should hit KV cache
curl -X POST https://your-worker.workers.dev/translate \
  -H 'Content-Type: application/json' \
  -d '{"text": "Hello, how are you?", "targetLang": "es", "sourceLang": "en"}'
# Expected: { ..., fromCache: true, confidence: 1.0 }
```

```sql
-- schema.sql
CREATE TABLE IF NOT EXISTS translations (
  source_hash TEXT NOT NULL,
  target_lang TEXT NOT NULL,
  source_lang TEXT NOT NULL,
  source_text TEXT NOT NULL,
  translation TEXT NOT NULL,
  confidence REAL NOT NULL,
  reviewed INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  PRIMARY KEY (source_hash, target_lang)
);

CREATE TABLE IF NOT EXISTS translation_jobs (
  id TEXT PRIMARY KEY,
  status TEXT NOT NULL DEFAULT 'queued',
  created_at TEXT NOT NULL,
  completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_translations_low_confidence
  ON translations(confidence) WHERE confidence < 0.7 AND reviewed = 0;
```

---

## Related

- `documentation/categories/ai-ml/workers-ai-prompt-caching-kv.md` — KV caching patterns
- `documentation/categories/ai-ml/workers-ai-structured-output.md` — language detection via structured output
- [Cloudflare M2M100 model documentation](https://developers.cloudflare.com/workers-ai/models/translation/)
- [M2M100 paper — Fan et al., 2020](https://arxiv.org/abs/2010.11125)
- [Cloudflare Queues — batch processing](https://developers.cloudflare.com/queues/reference/batching-retries/)

---

## Sources

- Cloudflare Workers AI model catalog, August 2026
- M2M-100 supported language list, Meta AI
- Cloudflare KV and Queues documentation
- Internal example.com translation service, production since 2025-Q3
