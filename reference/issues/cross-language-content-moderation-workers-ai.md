# Cross-Language Content Moderation Workers AI

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

example project (example.com) is used globally. Policy violations submitted in Arabic, Portuguese, Turkish, or Tagalog bypass English-trained keyword filters and reach human moderators without context. The moderation queue backs up, false-negative rates spike for non-English content, and moderators unfamiliar with the source language cannot act confidently.

## Context

Workers AI provides multilingual LLM inference at the edge with no cold-start penalty. The pipeline detects the post's language, translates to a pivot language (English) for policy classification, runs the classifier on the translated text, and stores the original + translation + classification in D1. For high-confidence detections the action is automated; for low-confidence cases the translation gives human moderators the context they need.

---

## Language Detection

```typescript
interface LangDetectResult {
  language: string;   // BCP-47, e.g. "ar", "pt-BR"
  confidence: number; // 0–1
}

async function detectLanguage(
  ai: Ai,
  text: string,
): Promise<LangDetectResult> {
  // Use a lightweight classification model
  const result = await ai.run('@cf/meta/m2m100-1.2b', {
    text,
    source_lang: 'detect',
    target_lang: 'en',
  }) as { detected_source_lang: string; translated_text: string };

  // m2m100 returns detected lang in its output metadata
  return {
    language: result.detected_source_lang ?? 'en',
    confidence: 0.9, // m2m100 does not surface a confidence score; treat detection as high-confidence
  };
}
```

## Translation to Pivot Language

```typescript
async function translateToPivot(
  ai: Ai,
  text: string,
  sourceLang: string,
  targetLang = 'en',
): Promise<string> {
  if (sourceLang === targetLang) return text;

  const result = await ai.run('@cf/meta/m2m100-1.2b', {
    text,
    source_lang: sourceLang,
    target_lang: targetLang,
  }) as { translated_text: string };

  return result.translated_text;
}
```

## Policy Classification on Translated Text

```typescript
type PolicyCategory =
  | 'hate_speech'
  | 'harassment'
  | 'violence'
  | 'spam'
  | 'misinformation'
  | 'safe';

interface ClassificationResult {
  category: PolicyCategory;
  confidence: number;
  action: 'allow' | 'queue_review' | 'auto_remove';
}

const CONFIDENCE_THRESHOLDS = {
  auto_remove: 0.92,
  queue_review: 0.65,
};

async function classifyContent(
  ai: Ai,
  translatedText: string,
): Promise<ClassificationResult> {
  const result = await ai.run('@cf/facebook/bart-large-mnli', {
    text: translatedText,
    candidate_labels: [
      'hate speech',
      'harassment',
      'violence',
      'spam',
      'misinformation',
      'safe content',
    ],
  }) as { labels: string[]; scores: number[] };

  const topLabel = result.labels[0];
  const topScore = result.scores[0];

  const category = topLabel.replace(' content', '').replace(' ', '_') as PolicyCategory;
  const action =
    topScore >= CONFIDENCE_THRESHOLDS.auto_remove  ? 'auto_remove'  :
    topScore >= CONFIDENCE_THRESHOLDS.queue_review ? 'queue_review' :
    'allow';

  return { category, confidence: topScore, action };
}
```

## Full Moderation Pipeline

```typescript
interface ModerationRecord {
  postId: string;
  originalText: string;
  detectedLang: string;
  translatedText: string;
  category: string;
  confidence: number;
  action: string;
  processedAt: number;
}

async function moderatePost(
  ai: Ai,
  db: D1Database,
  queue: Queue,
  postId: string,
  text: string,
): Promise<{ action: string }> {
  // Step 1: Detect and translate
  const { language } = await detectLanguage(ai, text);
  const translated = await translateToPivot(ai, text, language);

  // Step 2: Classify
  const { category, confidence, action } = await classifyContent(ai, translated);

  // Step 3: Persist
  const record: ModerationRecord = {
    postId, originalText: text, detectedLang: language,
    translatedText: translated, category, confidence,
    action, processedAt: Date.now(),
  };

  await db.prepare(
    `INSERT INTO moderation_records
       (post_id, original_text, detected_lang, translated_text, category, confidence, action, processed_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
  ).bind(
    record.postId, record.originalText, record.detectedLang,
    record.translatedText, record.category, record.confidence,
    record.action, record.processedAt,
  ).run();

  // Step 4: Dispatch
  if (action === 'auto_remove') {
    await db.prepare(`UPDATE posts SET status = 'removed' WHERE id = ?`).bind(postId).run();
  } else if (action === 'queue_review') {
    await queue.send({
      type: 'moderation_review',
      postId,
      detectedLang: language,
      translatedText: translated,
      category,
      confidence,
    });
  }

  return { action };
}
```

## Moderator Queue Enrichment

When a post enters the human review queue, the moderator sees original text, detected language, and translation side-by-side.

```typescript
interface ModeratorQueueItem {
  postId: string;
  originalText: string;
  detectedLang: string;      // shown as flag + BCP-47 label
  translatedText: string;    // pivot English
  category: string;
  confidence: number;
}

async function getReviewQueue(
  db: D1Database,
  limit = 50,
): Promise<ModeratorQueueItem[]> {
  const rows = await db.prepare(
    `SELECT r.post_id as postId, r.original_text as originalText,
            r.detected_lang as detectedLang, r.translated_text as translatedText,
            r.category, r.confidence
     FROM moderation_records r
     JOIN posts p ON p.id = r.post_id
     WHERE r.action = 'queue_review' AND p.status = 'pending_review'
     ORDER BY r.confidence DESC, r.processed_at ASC
     LIMIT ?`,
  ).bind(limit).all<ModeratorQueueItem>();

  return rows.results;
}
```

## Language Coverage Analytics

Track false-negative rates by language to identify models underperforming on specific language families.

```typescript
async function getLanguageCoverageStats(
  db: D1Database,
): Promise<Array<{ lang: string; total: number; autoRemoved: number; queued: number; allowed: number }>> {
  const rows = await db.prepare(
    `SELECT detected_lang as lang,
            COUNT(*) as total,
            SUM(CASE WHEN action = 'auto_remove'  THEN 1 ELSE 0 END) as autoRemoved,
            SUM(CASE WHEN action = 'queue_review' THEN 1 ELSE 0 END) as queued,
            SUM(CASE WHEN action = 'allow'        THEN 1 ELSE 0 END) as allowed
     FROM moderation_records
     WHERE processed_at > ?
     GROUP BY detected_lang
     ORDER BY total DESC`,
  ).bind(Date.now() - 7 * 24 * 60 * 60 * 1000).all();

  return rows.results as typeof getLanguageCoverageStats extends (...a: any) => Promise<infer R> ? R : never;
}
```

---

## Anti-patterns

- Translating first and only storing the translation — loses the original for appeals, legal holds, and model retraining.
- Using a single English keyword blocklist for all languages — effective bypass rate >80% for Arabic and CJK script content.
- Blocking all non-English content pending human review — destroys platform utility for non-English speakers and creates moderator burnout.
- Treating m2m100 detections as perfect — very short texts (< 10 tokens) have unreliable language detection; fall back to `Accept-Language` header.

## Gotchas

- Workers AI `@cf/meta/m2m100-1.2b` combines detection and translation in a single inference call. Pass `source_lang: 'detect'` to trigger auto-detection.
- The model returns `detected_source_lang` only when `source_lang` is `'detect'` — not on explicit source-lang calls.
- Translation quality for low-resource languages (Tagalog, Yoruba, Swahili) is lower than for high-resource ones; confidence thresholds should be raised for those languages.
- BART MNLI labels are free-form strings — normalize them before inserting into D1 enum columns.
- Workers AI requests count against the account's AI token budget. A post processed with two model calls (translation + classification) costs roughly 2× inference units.

## Verification

```bash
# Submit an Arabic test post and confirm translation + classification stored
curl -s -X POST https://example.com/api/posts \
  -H "Content-Type: application/json" \
  -d '{"content":"هذا محتوى اختباري للمشكلات"}' | jq .

# Query D1 for the moderation record
wrangler d1 execute example project-db --command \
  "SELECT post_id, detected_lang, translated_text, category, action
   FROM moderation_records ORDER BY processed_at DESC LIMIT 1"

# Language coverage stats (last 7 days)
wrangler d1 execute example project-db --command \
  "SELECT detected_lang, COUNT(*) as n, action FROM moderation_records
   WHERE processed_at > (unixepoch('now') - 604800) * 1000
   GROUP BY detected_lang, action ORDER BY n DESC"
```

---

## Related

- `hate-speech-detection-multilingual-workers-ai.md`
- `real-time-toxic-content-scoring-workers-ai.md`
- `dog-whistle-coded-language-detection-workers-ai.md`
- `report-queue-prioritization-workers-queues-ai.md`
- `misinformation-labeling-pipeline-ugc.md`

## Sources

- Cloudflare Workers AI model catalog — https://developers.cloudflare.com/workers-ai/models/
- M2M100 paper (multilingual machine translation) — https://arxiv.org/abs/2010.11125
- DSA Annex I (reporting obligations for harmful content by language) — https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32022R2065
- GIFCT Cross-Platform Content Policies — https://gifct.org/
