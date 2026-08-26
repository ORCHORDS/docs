# Workers AI Multilingual Sentiment Analysis with D1

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You collect user reviews, support tickets, or social comments in 10+ languages and need to score sentiment (positive / neutral / negative + confidence) at ingestion time, store results in D1, and surface per-language aggregate dashboards—without running a language-specific model per locale or a Python ML server.

## Context

Cloudflare Workers AI includes `@cf/cardiffnlp/twitter-roberta-base-sentiment-latest`, a multilingual-capable RoBERTa model fine-tuned on sentiment. For languages outside its training distribution, a two-step approach works: first translate to English via `@cf/meta/m2m100-1.2b`, then classify. D1 stores sentiment scores with language metadata for aggregation. The entire pipeline runs at the edge with zero external dependencies.

---

## 1. Architecture

```
Incoming text (any language)
      │
      ▼
Language detection  ──────────────────────────────────────┐
      │                                                    │
      │ if non-English or low-confidence                   │
      ▼                                                    │
m2m100 translation → English                               │ if English
      │                                                    │
      └────────────────────────────────────────────────────┘
                              │
                              ▼
         twitter-roberta-base-sentiment-latest
                              │
                              ▼
                      D1  sentiment_scores  INSERT
```

---

## 2. Wrangler Configuration

```toml
[ai]
binding = "AI"

[[d1_databases]]
binding = "DB"
database_name = "sentiment-db"
database_id = "YOUR_D1_ID"
```

---

## 3. D1 Schema

```sql
CREATE TABLE IF NOT EXISTS sentiment_scores (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id     TEXT NOT NULL,
  source      TEXT,
  raw_text    TEXT NOT NULL,
  language    TEXT,          -- BCP-47 code detected
  translated  INTEGER DEFAULT 0,  -- 1 if translation was applied
  label       TEXT NOT NULL, -- 'positive' | 'neutral' | 'negative'
  score       REAL NOT NULL, -- confidence [0,1]
  scored_at   INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_lang_label ON sentiment_scores(language, label);
CREATE INDEX IF NOT EXISTS idx_source_scored ON sentiment_scores(source, scored_at);
```

---

## 4. Language Detection (Lightweight Heuristic)

```typescript
// Workers AI does not expose a dedicated language-ID model as of 2026-Q3.
// Use a small BCP-47 heuristic based on script ranges, then fall back to
// translate-everything-to-English for non-Latin scripts.

function detectScript(text: string): "latin" | "cjk" | "arabic" | "cyrillic" | "other" {
  const sample = text.slice(0, 200);
  if (/[一-鿿぀-ヿ]/.test(sample)) return "cjk";
  if (/[؀-ۿ]/.test(sample)) return "arabic";
  if (/[Ѐ-ӿ]/.test(sample)) return "cyrillic";
  if (/[A-Za-zÀ-ÖØ-öø-ÿ]/.test(sample)) return "latin";
  return "other";
}

// For production: replace with a language-id model or Accept-Language header value
function shouldTranslate(text: string, langHint?: string): boolean {
  if (langHint && langHint.startsWith("en")) return false;
  const script = detectScript(text);
  // Translate everything that's not clearly Latin-script (may include French, Spanish, etc.)
  // Accept-Language hint takes precedence
  return script !== "latin";
}
```

---

## 5. Translation Step

```typescript
interface Env {
  AI: Ai;
  DB: D1Database;
}

async function translateToEnglish(text: string, env: Env): Promise<string> {
  // m2m100 supports 100 languages; source_lang "auto" not supported—use "zho" for CJK, etc.
  // Simplest safe option: set source_lang to "auto" equivalent by omitting it and using
  // the model's default behaviour, OR set to detected language.
  const result = await env.AI.run("@cf/meta/m2m100-1.2b", {
    text,
    source_lang: "auto", // supported as of 2026 runtime
    target_lang: "en",
  });
  return (result as { translated_text: string }).translated_text;
}
```

---

## 6. Sentiment Classification

```typescript
type SentimentLabel = "positive" | "neutral" | "negative";

interface SentimentResult {
  label: SentimentLabel;
  score: number;
}

async function classifySentiment(
  text: string,
  env: Env
): Promise<SentimentResult> {
  // Truncate to avoid exceeding model context (512 tokens ≈ ~2000 chars)
  const truncated = text.slice(0, 2000);

  const result = await env.AI.run(
    "@cf/cardiffnlp/twitter-roberta-base-sentiment-latest",
    { text: truncated }
  );

  // Response: { label: string; score: number }[]  (sorted by score desc)
  const scores = result as Array<{ label: string; score: number }>;
  const top = scores.reduce((a, b) => (a.score > b.score ? a : b));

  // Normalise label strings (model may return "LABEL_0/1/2" or "negative/neutral/positive")
  const labelMap: Record<string, SentimentLabel> = {
    LABEL_0: "negative",
    LABEL_1: "neutral",
    LABEL_2: "positive",
    negative: "negative",
    neutral: "neutral",
    positive: "positive",
  };

  return {
    label: labelMap[top.label] ?? "neutral",
    score: top.score,
  };
}
```

---

## 7. Full Pipeline Handler

```typescript
interface TextItem {
  itemId: string;
  text: string;
  source?: string;
  langHint?: string; // BCP-47, e.g. "zh-CN", "ar", "en-US"
}

export async function scoreSentiment(item: TextItem, env: Env): Promise<void> {
  const needsTranslation = shouldTranslate(item.text, item.langHint);
  let textForClassification = item.text;
  let translated = false;

  if (needsTranslation) {
    try {
      textForClassification = await translateToEnglish(item.text, env);
      translated = true;
    } catch (err) {
      // Translation failure: classify raw text anyway, quality may degrade
      console.warn(`Translation failed for item ${item.itemId}, classifying raw.`, err);
    }
  }

  const sentiment = await classifySentiment(textForClassification, env);

  await env.DB.prepare(
    `INSERT INTO sentiment_scores
       (item_id, source, raw_text, language, translated, label, score, scored_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
  ).bind(
    item.itemId,
    item.source ?? null,
    item.text.slice(0, 4000), // cap stored length
    item.langHint ?? detectScript(item.text),
    translated ? 1 : 0,
    sentiment.label,
    sentiment.score,
    Date.now()
  ).run();
}

// HTTP handler
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") return new Response("POST only", { status: 405 });

    const body = (await request.json()) as TextItem | TextItem[];
    const items = Array.isArray(body) ? body : [body];

    await Promise.all(items.map((item) => scoreSentiment(item, env)));

    return Response.json({ status: "ok", count: items.length });
  },
};
```

---

## 8. Aggregate Query Examples

```sql
-- Per-language sentiment breakdown (last 30 days)
SELECT
  language,
  label,
  COUNT(*)                            AS count,
  ROUND(AVG(score), 3)                AS avg_confidence
FROM sentiment_scores
WHERE scored_at > (unixepoch() - 86400 * 30) * 1000
GROUP BY language, label
ORDER BY language, label;

-- Net Sentiment Score per source (positive% - negative%)
SELECT
  source,
  ROUND(
    100.0 * SUM(CASE WHEN label = 'positive' THEN 1 ELSE 0 END) / COUNT(*) -
    100.0 * SUM(CASE WHEN label = 'negative' THEN 1 ELSE 0 END) / COUNT(*),
    1
  ) AS nss
FROM sentiment_scores
GROUP BY source
ORDER BY nss DESC;
```

---

## Anti-patterns

- **Passing non-English text directly to RoBERTa** — twitter-roberta-base-sentiment was primarily trained on English tweets; scores on unseen languages are unreliable.
- **Embedding full conversation threads** — sentiment models are sentence/paragraph-level; split long documents into sentences and aggregate scores.
- **Storing the full translated text** — store only the original to save D1 space; re-translate on demand if the English version is ever needed for debugging.
- **Using a single threshold for "positive"** — confidence scores cluster near 0.5 for ambiguous text; define a "low confidence" band (e.g., 0.45–0.65) and label those as uncertain rather than neutral.

---

## Gotchas

- `@cf/meta/m2m100-1.2b` `source_lang: "auto"` support was added in the 2026 runtime; on older workers runtimes you must provide an explicit BCP-47 language code.
- The RoBERTa model's 512-token limit maps to roughly 350–400 words. Texts longer than that are silently truncated by the model; pre-truncate in your Worker to control which portion is scored.
- Workers AI model availability can vary by region/tier; add a try/catch around every `env.AI.run()` call and fail gracefully.
- D1 `unixepoch()` returns seconds; `Date.now()` returns milliseconds. Use consistent units or your date filters will silently return 0 rows.

---

## Verification

```bash
# Insert a test item
curl -X POST https://your-worker.example.com \
  -H "Content-Type: application/json" \
  -d '{"itemId":"test-1","text":"这个产品非常好！完全满足我的需求。","langHint":"zh-CN","source":"reviews"}'

# Check D1 result
wrangler d1 execute sentiment-db \
  --command "SELECT item_id, language, translated, label, score FROM sentiment_scores WHERE item_id='test-1'"
```

Expected: `translated=1`, `label='positive'`, `score > 0.7`.

---

## Related

- `sentiment-analysis-user-feedback-pipeline.md`
- `automatic-language-detection-i18n-routing.md`
- `workers-ai-translation-edge-pipeline.md`
- `workers-ai-text-classification-moderation.md`
- `llm-for-classification.md`

---

## Sources

- Cardiff NLP Twitter-RoBERTa model: https://huggingface.co/cardiffnlp/twitter-roberta-base-sentiment-latest
- Cloudflare Workers AI translation model: https://developers.cloudflare.com/workers-ai/models/m2m100-1.2b/
- BCP-47 language tags: https://www.rfc-editor.org/rfc/rfc5646
