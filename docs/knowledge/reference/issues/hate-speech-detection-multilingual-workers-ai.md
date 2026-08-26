# Multilingual Hate Speech Detection with Workers AI

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

example project users post in over 40 languages, and English-only classifiers miss a significant volume of hate speech in Arabic, Spanish, Portuguese, and Hindi. The moderation queue shows escalating community reports for non-English posts that pass automated screening without flagging.

## Context

Anonymous social platforms face amplified hate speech risk because there is no account reputation to lose. example project routes every user post through a moderation pipeline before it becomes visible to other users. The existing pipeline uses a single English-language classifier that silently passes non-English content. Cloudflare Workers AI exposes multilingual embedding and text generation models that can be combined with a lightweight per-language threshold table stored in D1 to produce a language-aware pipeline that runs entirely at the edge without cold-start latency.

## Language Detection and Model Routing

Each incoming post passes through a two-stage gate: first identify the dominant language, then route to the appropriate Workers AI prompt template and threshold. Language detection runs with `@cf/meta/m2m100-1.2b` (a multilingual translation model whose encoder embeddings correlate tightly with language identity) or via the lighter `@cf/huggingface/distilbert-sst-2-int8` applied to a translated pivot. For a simpler production path, translate the post to English first using `@cf/meta/m2m100-1.2b` and run a single classifier on the translated output.

```typescript
export interface Env {
  AI: Ai;
  DB: D1Database;
}

interface ModerationResult {
  label: 'SAFE' | 'HATE' | 'BORDERLINE';
  score: number;
  detectedLanguage: string;
  translatedText?: string;
}

async function detectLanguage(ai: Ai, text: string): Promise<string> {
  // Use a short probe: translate to English and inspect the source tag
  const response = await ai.run('@cf/meta/m2m100-1.2b', {
    text,
    source_lang: 'auto',   // auto-detect source
    target_lang: 'en',
  }) as { translated_text: string; detected_source_lang?: string };

  return response.detected_source_lang ?? 'en';
}

async function translateToEnglish(
  ai: Ai,
  text: string,
  sourceLang: string,
): Promise<string> {
  if (sourceLang === 'en') return text;

  const result = await ai.run('@cf/meta/m2m100-1.2b', {
    text,
    source_lang: sourceLang,
    target_lang: 'en',
  }) as { translated_text: string };

  return result.translated_text;
}
```

## Hate Speech Classification and Threshold Lookup

After translation, the text passes to a zero-shot classification prompt against `@cf/meta/llama-3.1-8b-instruct`. A per-language threshold row in D1 allows tuning: languages with more figurative slang (e.g., Brazilian Portuguese internet dialect) can carry a higher tolerance score before the HATE label triggers a human review rather than an immediate removal.

```typescript
async function classifyHateSpeech(
  ai: Ai,
  text: string,
): Promise<{ score: number; rawLabel: string }> {
  const systemPrompt = `You are a content safety classifier. Respond ONLY with a JSON object.
Classify the text as one of: SAFE, BORDERLINE, HATE.
Return: {"label": "<LABEL>", "score": <0.0-1.0>, "reason": "<one sentence>"}`;

  const result = await ai.run('@cf/meta/llama-3.1-8b-instruct', {
    messages: [
      { role: 'system', content: systemPrompt },
      { role: 'user', content: `Classify this text: "${text}"` },
    ],
    max_tokens: 120,
    temperature: 0,
  }) as { response: string };

  try {
    const parsed = JSON.parse(result.response.trim());
    return { score: parsed.score as number, rawLabel: parsed.label as string };
  } catch {
    return { score: 0, rawLabel: 'SAFE' };
  }
}

async function getThreshold(db: D1Database, lang: string): Promise<number> {
  const row = await db
    .prepare('SELECT hate_threshold FROM lang_thresholds WHERE lang_code = ?1')
    .bind(lang)
    .first<{ hate_threshold: number }>();
  return row?.hate_threshold ?? 0.75;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { text, postId, userId } = await request.json<{
      text: string;
      postId: string;
      userId: string;
    }>();

    const detectedLang = await detectLanguage(env.AI, text);
    const englishText = await translateToEnglish(env.AI, text, detectedLang);
    const { score, rawLabel } = await classifyHateSpeech(env.AI, englishText);
    const threshold = await getThreshold(env.DB, detectedLang);

    const finalLabel: ModerationResult['label'] =
      score >= threshold
        ? 'HATE'
        : score >= threshold * 0.7
        ? 'BORDERLINE'
        : 'SAFE';

    await env.DB.prepare(
      `INSERT INTO moderation_results
         (post_id, user_id, detected_lang, score, label, translated_text, created_at)
       VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)`,
    )
      .bind(
        postId,
        userId,
        detectedLang,
        score,
        finalLabel,
        detectedLang !== 'en' ? englishText : null,
        new Date().toISOString(),
      )
      .run();

    return Response.json({ label: finalLabel, score, detectedLanguage: detectedLang });
  },
} satisfies ExportedHandler<Env>;
```

## D1 Schema and Threshold Management

```typescript
// D1 migration: 0005_multilingual_moderation.sql
const schema = `
CREATE TABLE IF NOT EXISTS lang_thresholds (
  lang_code        TEXT PRIMARY KEY,
  hate_threshold   REAL NOT NULL DEFAULT 0.75,
  review_threshold REAL NOT NULL DEFAULT 0.55,
  updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS moderation_results (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  post_id         TEXT NOT NULL,
  user_id         TEXT NOT NULL,
  detected_lang   TEXT NOT NULL,
  score           REAL NOT NULL,
  label           TEXT NOT NULL CHECK(label IN ('SAFE','BORDERLINE','HATE')),
  translated_text TEXT,
  created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_moderation_label
  ON moderation_results(label, created_at DESC);

-- Seed common language thresholds
INSERT OR IGNORE INTO lang_thresholds (lang_code, hate_threshold, review_threshold)
VALUES
  ('en', 0.75, 0.55),
  ('es', 0.78, 0.58),
  ('pt', 0.80, 0.60),
  ('ar', 0.72, 0.52),
  ('hi', 0.73, 0.53),
  ('fr', 0.76, 0.56),
  ('de', 0.74, 0.54);
`;
```

## Anti-patterns

- Running only an English classifier and treating non-English posts as automatically safe — this is the exact failure that created the backlog.
- Using the translation model's output confidence as a hate speech score — translation confidence and content severity are orthogonal signals.
- Setting a single global threshold across all languages; figurative language, sarcasm markers, and internet dialect vary enormously by locale.

## Gotchas

- `@cf/meta/m2m100-1.2b` returns `detected_source_lang` only when `source_lang` is set to `'auto'`; omitting it causes the field to be absent in the response.
- Workers AI inference counts against your account's neuron budget; running two sequential AI calls (translate + classify) per post doubles neuron consumption — batch low-priority posts with a Queue consumer instead of inline.

## Verification

```bash
# Smoke-test with a Spanish-language post
curl -X POST https://example project-moderation.example.workers.dev/classify \
  -H "Content-Type: application/json" \
  -d '{"text":"texto de prueba ofensivo","postId":"p123","userId":"u456"}'

# Inspect D1 results for a given language
wrangler d1 execute example project-db \
  --command "SELECT detected_lang, label, COUNT(*) as n FROM moderation_results GROUP BY detected_lang, label ORDER BY n DESC LIMIT 30"

# Check threshold table
wrangler d1 execute example project-db \
  --command "SELECT * FROM lang_thresholds ORDER BY lang_code"
```

## Related

- `issues/real-time-toxic-content-scoring-workers-ai.md`
- `issues/spam-post-detection-cloudflare-workers-ai.md`
- `issues/misinformation-labeling-pipeline-ugc.md`
- `issues/coordinated-inauthentic-behavior-detection-d1.md`

## Sources

- https://developers.cloudflare.com/workers-ai/models/m2m100-1.2b/
- https://developers.cloudflare.com/workers-ai/models/llama-3.1-8b-instruct/
- https://developers.cloudflare.com/d1/
- https://www.un.org/en/hate-speech/understanding-hate-speech/what-is-hate-speech
