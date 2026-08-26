# Machine Translation via Workers AI with Quality Scoring

- Date: 2026-08-22
- Author: example.com
- Status: production

## Problem: Running MT at the Edge and Catching Low-Confidence Segments Before They Reach Users

Calling a third-party MT API from every Workers request adds latency and egress cost. Workers AI
lets you run inference in the same network as your Worker, but raw model output gives no indication
of translation quality. Segments with unusual terminology, code-switching, or rare syntax can
silently produce wrong output. This article covers the full pipeline: translate with Workers AI,
estimate quality with lightweight heuristics, store confidence in D1, and route low-confidence
segments to a human review queue.

## Context

Workers AI exposes translation models (`@cf/meta/m2m100-1.2b`) that accept `{text, source_lang,
target_lang}` and return `{translated_text}`. Quality estimation (QE) is typically a separate
model (e.g. CometKiwi) but running a full QE model at the edge is impractical. A practical
alternative is a feature-based confidence heuristic: length ratio, unknown-word rate, and
repetition score correlate well enough with human judgements for routing decisions.

## Workers AI Translation

```typescript
// src/translate.ts
export interface TranslationResult {
  translatedText: string;
  confidenceScore: number; // 0–1
  flags: string[];
}

export async function translateSegment(
  ai: Ai,
  text: string,
  sourceLang: string,
  targetLang: string
): Promise<TranslationResult> {
  const result = await ai.run('@cf/meta/m2m100-1.2b', {
    text,
    source_lang: sourceLang,
    target_lang: targetLang,
  }) as { translated_text: string };

  const { score, flags } = estimateQuality(text, result.translated_text, sourceLang, targetLang);

  return {
    translatedText: result.translated_text,
    confidenceScore: score,
    flags,
  };
}
```

## Quality Heuristics

```typescript
// src/quality.ts
const SUSPICIOUS_LENGTH_RATIO = { min: 0.4, max: 2.8 };

function lengthRatioScore(src: string, tgt: string): number {
  const ratio = tgt.length / Math.max(src.length, 1);
  if (ratio < SUSPICIOUS_LENGTH_RATIO.min || ratio > SUSPICIOUS_LENGTH_RATIO.max) return 0;
  // score peaks at ratio 1.0, degrades linearly toward the boundaries
  const center = 1.1;
  const distance = Math.abs(ratio - center) / (SUSPICIOUS_LENGTH_RATIO.max - center);
  return Math.max(0, 1 - distance * 0.6);
}

function repetitionScore(text: string): number {
  const words = text.toLowerCase().split(/\s+/);
  const unique = new Set(words).size;
  const ratio = unique / Math.max(words.length, 1);
  return ratio < 0.4 ? 0.2 : 1; // heavy repetition → low score
}

export function estimateQuality(
  src: string,
  tgt: string,
  _srcLang: string,
  tgtLang: string
): { score: number; flags: string[] } {
  const flags: string[] = [];
  let score = 1.0;

  const lrScore = lengthRatioScore(src, tgt);
  if (lrScore < 0.6) flags.push('length_ratio');
  score *= lrScore;

  const repScore = repetitionScore(tgt);
  if (repScore < 0.5) flags.push('repetition');
  score *= repScore;

  // RTL targets: check that direction-sensitive punctuation hasn't been mirrored
  if (['ar', 'he', 'fa', 'ur'].includes(tgtLang)) {
    if (/[<>]{2,}/.test(tgt)) { flags.push('bidi_artifact'); score *= 0.5; }
  }

  // Numeric preservation: numbers in source should appear in target
  const srcNums = (src.match(/\d+/g) ?? []).sort().join(',');
  const tgtNums = (tgt.match(/\d+/g) ?? []).sort().join(',');
  if (srcNums && srcNums !== tgtNums) { flags.push('number_mismatch'); score *= 0.7; }

  return { score: Math.max(0, Math.min(1, score)), flags };
}
```

## D1 Schema and Confidence Storage

```sql
-- migrations/0010_mt_quality.sql
CREATE TABLE IF NOT EXISTS mt_translations (
  id          TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  segment_key TEXT NOT NULL,
  source_lang TEXT NOT NULL,
  target_lang TEXT NOT NULL,
  source_text TEXT NOT NULL,
  translated_text TEXT NOT NULL,
  confidence  REAL NOT NULL,
  flags       TEXT NOT NULL DEFAULT '[]',   -- JSON array
  reviewed    INTEGER NOT NULL DEFAULT 0,   -- 0 = pending, 1 = approved, 2 = rejected
  reviewer_id TEXT,
  created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX idx_mt_low_confidence ON mt_translations (confidence)
  WHERE reviewed = 0;
CREATE INDEX idx_mt_segment ON mt_translations (segment_key, target_lang);
```

```typescript
// src/store.ts
import type { D1Database } from '@cloudflare/workers-types';
import type { TranslationResult } from './translate';

const HUMAN_REVIEW_THRESHOLD = 0.65;

export async function storeTranslation(
  db: D1Database,
  segmentKey: string,
  sourceLang: string,
  targetLang: string,
  sourceText: string,
  result: TranslationResult
): Promise<{ needsReview: boolean }> {
  await db
    .prepare(
      `INSERT INTO mt_translations
         (segment_key, source_lang, target_lang, source_text, translated_text, confidence, flags)
       VALUES (?, ?, ?, ?, ?, ?, ?)`
    )
    .bind(
      segmentKey,
      sourceLang,
      targetLang,
      sourceText,
      result.translatedText,
      result.confidenceScore,
      JSON.stringify(result.flags)
    )
    .run();

  return { needsReview: result.confidenceScore < HUMAN_REVIEW_THRESHOLD };
}

export async function fetchApprovedTranslation(
  db: D1Database,
  segmentKey: string,
  targetLang: string
): Promise<string | null> {
  const row = await db
    .prepare(
      `SELECT translated_text FROM mt_translations
       WHERE segment_key = ? AND target_lang = ? AND reviewed = 1
       ORDER BY created_at DESC LIMIT 1`
    )
    .bind(segmentKey, targetLang)
    .first<{ translated_text: string }>();
  return row?.translated_text ?? null;
}
```

## Human Review Queue

```typescript
// src/review-queue.ts
import type { Queue } from '@cloudflare/workers-types';

export interface ReviewTask {
  segmentKey: string;
  targetLang: string;
  sourceText: string;
  translatedText: string;
  confidenceScore: number;
  flags: string[];
}

export async function enqueueReview(queue: Queue, task: ReviewTask): Promise<void> {
  await queue.send(task, { contentType: 'json' });
}

// In your Worker handler:
export async function handleTranslationRequest(
  req: Request,
  env: { AI: Ai; DB: D1Database; REVIEW_QUEUE: Queue }
): Promise<Response> {
  const { segmentKey, text, sourceLang, targetLang } = await req.json<{
    segmentKey: string; text: string; sourceLang: string; targetLang: string;
  }>();

  // Check approved cache first
  const approved = await fetchApprovedTranslation(env.DB, segmentKey, targetLang);
  if (approved) return Response.json({ text: approved, source: 'approved' });

  const { translateSegment } = await import('./translate');
  const { storeTranslation } = await import('./store');
  const { enqueueReview } = await import('./review-queue');

  const result = await translateSegment(env.AI, text, sourceLang, targetLang);
  const { needsReview } = await storeTranslation(env.DB, segmentKey, sourceLang, targetLang, text, result);

  if (needsReview) {
    await enqueueReview(env.REVIEW_QUEUE, {
      segmentKey, targetLang, sourceText: text,
      translatedText: result.translatedText,
      confidenceScore: result.confidenceScore,
      flags: result.flags,
    });
  }

  return Response.json({
    text: result.translatedText,
    confidence: result.confidenceScore,
    needsReview,
    source: 'mt',
  });
}
```

## Anti-patterns

- Running a full CometKiwi QE model inside a Worker CPU budget — the heuristics above are good enough for routing; reserve heavy QE for the review-queue consumer.
- Trusting MT output for medical, legal, or financial content without a mandatory human review gate regardless of confidence score.
- Indexing `mt_translations` on `translated_text` — this column is large and queried only by `segment_key`.
- Using a single `reviewed = 0` pass without differentiating "never seen" from "seen and pending" — add a `review_status` enum if the queue grows large.

## Gotchas

- `@cf/meta/m2m100-1.2b` uses ISO 639-1 two-letter codes (`en`, `fr`) not BCP 47 subtags; strip region before sending.
- Workers AI inference counts against your Workers AI units even for cached hits — cache approved translations in KV or D1 before hitting the model.
- The length-ratio heuristic breaks for language pairs with very different morphology (Finnish vs. English can legitimately hit 2.5×). Tune `SUSPICIOUS_LENGTH_RATIO` per language pair.
- D1 `REAL` stores IEEE 754 doubles; confidence `0.9999999` rounds fine but avoid comparing with `= 1.0` in SQL.

## Verification

```bash
# Insert a test segment and confirm confidence is stored
curl -X POST https://your-worker.example.com/translate \
  -H 'Content-Type: application/json' \
  -d '{"segmentKey":"home.hero.title","text":"Welcome","sourceLang":"en","targetLang":"fr"}'

# Query D1 for low-confidence rows
wrangler d1 execute MY_DB --command \
  "SELECT segment_key, confidence, flags FROM mt_translations WHERE confidence < 0.65 LIMIT 10"
```

## Related

- `workers-queues-async-translation-pipeline.md`
- `translation-kv-caching-ttl-strategy.md`
- `mt-quality-evaluation-2026.md`
- `deepl-google-mt-quality-gates-ci.md`

## Sources

- https://developers.cloudflare.com/workers-ai/models/translation/
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/queues/
- https://machinetranslate.org/quality-estimation
