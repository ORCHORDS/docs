# Sentiment Analysis for User Feedback Pipeline

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Your product collects user feedback through multiple channels: in-app ratings, support
tickets, app store reviews, survey responses, and community posts. You need to:

1. Classify sentiment (positive / negative / neutral / mixed) without manual labelling.
2. Identify the emotional category (satisfaction, frustration, confusion, delight) to
   route feedback to the right team.
3. Extract the feature or topic the feedback refers to (checkout flow, search, onboarding).
4. Aggregate scores over time to detect regressions and improvements.

Traditional VADER/TextBlob sentiment analysis breaks on sarcasm, short text, and domain-
specific language. LLM-based sentiment analysis handles nuance, context, and aspect-level
sentiment with high accuracy on first inference.

## Context

Sentiment analysis pipelines differ from real-time moderation. Feedback is:

- **Typically asynchronous.** A user submits a ticket; processing can happen over the
  next few seconds without blocking the response.
- **High volume but low urgency.** Thousands of feedback items per day, but a 5-minute
  delay in sentiment labelling is acceptable.
- **Multi-dimensional.** A review can be positive about price but negative about UX.
  Aspect-based sentiment analysis (ABSA) extracts per-topic sentiment.

The recommended architecture: submit feedback to a Cloudflare Queue → consumer Worker
calls Workers AI → results stored in D1 → aggregated views surfaced to a dashboard.

For real-time cases (in-app thumbs up/down with a comment), sentiment can be computed
synchronously if the comment is < 200 tokens.

## Basic Sentiment Classification

```typescript
type SentimentLabel = "positive" | "negative" | "neutral" | "mixed";
type EmotionLabel = "satisfaction" | "frustration" | "confusion" | "delight" |
                   "anger" | "disappointment" | "excitement" | "indifference";

interface SentimentResult {
  label: SentimentLabel;
  emotion: EmotionLabel;
  score: number;             // -1.0 (very negative) to 1.0 (very positive)
  confidence: number;        // 0.0–1.0
  summary: string;           // One-sentence summary of the feedback
}

async function analyzeSentiment(
  ai: Ai,
  text: string
): Promise<SentimentResult> {
  const systemPrompt = `
You are a sentiment analysis model for product feedback. Analyze the user feedback and return JSON.

Sentiment labels: positive, negative, neutral, mixed
Emotion labels: satisfaction, frustration, confusion, delight, anger, disappointment, excitement, indifference

Return this exact JSON schema:
{
  "label": "<sentiment label>",
  "emotion": "<emotion label>",
  "score": <number from -1.0 to 1.0>,
  "confidence": <number from 0.0 to 1.0>,
  "summary": "<one sentence describing the feedback>"
}

Scoring guide:
- 1.0 = ecstatically positive ("this is the best product ever!")
- 0.5 = moderately positive ("pretty good, works as expected")
- 0.0 = neutral ("I received my order")
- -0.5 = moderately negative ("the app crashes sometimes")
- -1.0 = severely negative ("this ruined my business, worst product")

Set confidence low when the text is ambiguous, sarcastic, or very short.
`.trim();

  const response = await ai.run("@cf/meta/llama-3.1-8b-instruct", {
    messages: [
      { role: "system", content: systemPrompt },
      { role: "user", content: `Analyze this feedback:\n\n"${text.slice(0, 1500)}"` },
    ],
    response_format: { type: "json_object" },
    max_tokens: 256,
    temperature: 0.1,
  });

  try {
    const parsed = JSON.parse((response as { response: string }).response) as SentimentResult;
    // Clamp numeric fields
    parsed.score = Math.max(-1.0, Math.min(1.0, parsed.score ?? 0));
    parsed.confidence = Math.max(0.0, Math.min(1.0, parsed.confidence ?? 0.5));
    return parsed;
  } catch {
    return {
      label: "neutral",
      emotion: "indifference",
      score: 0,
      confidence: 0.1,
      summary: "Unable to analyze feedback.",
    };
  }
}
```

## Aspect-Based Sentiment Analysis (ABSA)

Extract per-feature sentiment from a single feedback item:

```typescript
interface AspectSentiment {
  aspect: string;     // Feature or topic mentioned
  sentiment: SentimentLabel;
  score: number;      // -1.0 to 1.0
  quote: string;      // Relevant excerpt from the text
}

interface ABSAResult {
  aspects: AspectSentiment[];
  overall: SentimentLabel;
  overall_score: number;
}

const PRODUCT_ASPECTS = [
  "search", "checkout", "pricing", "performance", "onboarding", "support",
  "ui_design", "mobile_app", "notifications", "integrations", "documentation",
];

async function extractAspectSentiment(
  ai: Ai,
  text: string,
  aspects: string[] = PRODUCT_ASPECTS
): Promise<ABSAResult> {
  const prompt =
    `Analyze the sentiment expressed toward each product aspect in the following feedback.\n` +
    `Only include aspects explicitly mentioned in the text.\n` +
    `Product aspects to look for: ${aspects.join(", ")}\n\n` +
    `Feedback: "${text.slice(0, 1200)}"\n\n` +
    `Return JSON:\n` +
    `{"aspects":[{"aspect":"...","sentiment":"positive|negative|neutral|mixed","score":<-1 to 1>,"quote":"..."}],"overall":"positive|negative|neutral|mixed","overall_score":<-1 to 1>}`;

  const response = await ai.run("@cf/meta/llama-3.1-8b-instruct", {
    messages: [{ role: "user", content: prompt }],
    response_format: { type: "json_object" },
    max_tokens: 512,
    temperature: 0.1,
  });

  try {
    return JSON.parse((response as { response: string }).response) as ABSAResult;
  } catch {
    return { aspects: [], overall: "neutral", overall_score: 0 };
  }
}
```

## Queue-Based Async Pipeline

```typescript
// wrangler.toml
// [[queues.producers]]
// binding = "FEEDBACK_QUEUE"
// queue = "feedback-sentiment"
//
// [[queues.consumers]]
// queue = "feedback-sentiment"
// max_batch_size = 20
// max_batch_timeout = 10
// max_retries = 3
// max_concurrency = 3

// Producer: API handler receiving feedback submissions
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const body = await request.json<{
      id: string;
      source: string;   // "in-app" | "app-store" | "support" | "survey"
      text: string;
      user_id?: string;
      rating?: number;  // Optional numeric rating (1-5)
    }>();

    await env.DB.prepare(
      "INSERT INTO feedback (id, source, text, user_id, rating, sentiment_status) VALUES (?,?,?,?,?,'pending')"
    )
      .bind(body.id, body.source, body.text, body.user_id ?? null, body.rating ?? null)
      .run();

    await env.FEEDBACK_QUEUE.send({ feedbackId: body.id });

    return Response.json({ id: body.id, status: "received" }, { status: 202 });
  },
};
```

```typescript
// Consumer Worker
export default {
  async queue(
    batch: MessageBatch<{ feedbackId: string }>,
    env: Env
  ): Promise<void> {
    for (const msg of batch.messages) {
      try {
        const row = await env.DB.prepare(
          "SELECT text, source FROM feedback WHERE id = ?"
        )
          .bind(msg.body.feedbackId)
          .first<{ text: string; source: string }>();

        if (!row) { msg.ack(); continue; }

        const [sentiment, absa] = await Promise.all([
          analyzeSentiment(env.AI, row.text),
          extractAspectSentiment(env.AI, row.text),
        ]);

        await env.DB.prepare(
          `UPDATE feedback SET
            sentiment_label = ?,
            sentiment_score = ?,
            emotion = ?,
            sentiment_confidence = ?,
            sentiment_summary = ?,
            aspect_sentiments = ?,
            sentiment_status = 'done'
          WHERE id = ?`
        )
          .bind(
            sentiment.label,
            sentiment.score,
            sentiment.emotion,
            sentiment.confidence,
            sentiment.summary,
            JSON.stringify(absa.aspects),
            msg.body.feedbackId
          )
          .run();

        // Store per-aspect rows for aggregation queries
        if (absa.aspects.length > 0) {
          const stmts = absa.aspects.map((a) =>
            env.DB.prepare(
              "INSERT INTO feedback_aspects (feedback_id, aspect, sentiment, score) VALUES (?,?,?,?)"
            ).bind(msg.body.feedbackId, a.aspect, a.sentiment, a.score)
          );
          await env.DB.batch(stmts);
        }

        msg.ack();
      } catch {
        msg.retry();
      }
    }
  },
};
```

## Aggregation and Dashboard Queries

```sql
-- Average sentiment score by source over the last 30 days
SELECT
  source,
  COUNT(*) AS total,
  ROUND(AVG(sentiment_score), 3) AS avg_score,
  SUM(CASE WHEN sentiment_label = 'positive' THEN 1 ELSE 0 END) AS positive_count,
  SUM(CASE WHEN sentiment_label = 'negative' THEN 1 ELSE 0 END) AS negative_count
FROM feedback
WHERE sentiment_status = 'done'
  AND created_at > unixepoch('now', '-30 days')
GROUP BY source
ORDER BY avg_score DESC;

-- Worst-rated aspects (targets for product investment)
SELECT
  aspect,
  ROUND(AVG(score), 3) AS avg_score,
  COUNT(*) AS mentions,
  SUM(CASE WHEN sentiment = 'negative' THEN 1 ELSE 0 END) AS negative_mentions
FROM feedback_aspects
WHERE created_at > unixepoch('now', '-7 days')
GROUP BY aspect
HAVING mentions >= 5
ORDER BY avg_score ASC
LIMIT 10;

-- Daily sentiment trend (detect regressions after deploys)
SELECT
  DATE(created_at, 'unixepoch') AS day,
  ROUND(AVG(sentiment_score), 3) AS avg_score,
  COUNT(*) AS count
FROM feedback
WHERE sentiment_status = 'done'
  AND created_at > unixepoch('now', '-90 days')
GROUP BY day
ORDER BY day;
```

## Alert on Sentiment Regression

Trigger an alert when the rolling 24-hour average drops below a threshold:

```typescript
async function checkSentimentRegression(
  db: D1Database
): Promise<{ alert: boolean; score: number }> {
  const THRESHOLD = -0.2; // Adjust for your baseline

  const row = await db
    .prepare(
      `SELECT AVG(sentiment_score) AS avg_score
       FROM feedback
       WHERE sentiment_status = 'done'
         AND created_at > unixepoch('now', '-1 day')`
    )
    .first<{ avg_score: number }>();

  const score = row?.avg_score ?? 0;
  return { alert: score < THRESHOLD, score };
}
```

Schedule this check as a Cron Trigger in `wrangler.toml`:

```toml
[triggers]
crons = ["0 * * * *"]   # Hourly
```

## Anti-patterns

- **Using sentiment score as a proxy for product quality.** Sentiment reflects language
  tone, not objective quality. A 5-star review written in dry language scores lower than
  an enthusiastic 3-star review. Combine sentiment score with numeric rating when available.
- **Blocking user feedback from publishing based on sentiment.** Negative feedback is
  valuable signal. Flag for review, never silently suppress.
- **Aggregating without controlling for volume.** A feature with 3 negative reviews
  should rank differently from one with 300. Weight by mention count.
- **Running ABSA on every feedback item.** ABSA is 2× the inference cost of basic
  sentiment. Use a cheap model for basic sentiment on all items; run ABSA only on items
  with low confidence or specific keywords.
- **Interpreting "neutral" as "no signal."** Neutral sentiment often reflects factual
  descriptions or feature requests. Use a secondary intent classifier to distinguish.
- **Storing raw LLM summaries without review.** Summaries can misrepresent content.
  Flag summaries generated from low-confidence analyses for human review.

## Gotchas

- Sarcasm and irony ("Great, another crash. Love this app.") will score positive with
  naive prompt wording. Add explicit sarcasm detection instructions to the system prompt,
  or run a secondary sarcasm check for high-score items that contain negative vocabulary.
- Short feedback ("👍", "ok", "meh") has high ambiguity. Scores for these will cluster
  near 0 with low confidence; treat low-confidence results as effectively unlabelled.
- Workers AI `@cf/meta/llama-3.1-8b-instruct` returns sentiment that skews slightly
  positive on short, neutral text. Calibrate your thresholds on a held-out labelled
  sample from your own data before setting production alerts.
- Aspect detection hallucinates aspects not in the text at low frequencies. Always
  validate that the detected aspect's `quote` field contains words from the original
  text before storing.
- Queue `max_concurrency = 3` means at most 3 Workers AI calls run simultaneously per
  consumer. Tune this against your Workers AI plan's rate limits to avoid 429s.
- D1 `AVG()` on floating-point columns can return NULL when no rows match. Always
  use `?? 0` or COALESCE in queries used for alerting.

## Verification

```bash
# Submit feedback and check sentiment result
curl -X POST https://api.example.com/feedback \
  -H "Content-Type: application/json" \
  -d '{"id":"fb-001","source":"in-app","text":"The search is incredibly fast now! Checkout still breaks on mobile though."}'

# Wait a few seconds for queue processing, then check result
curl https://api.example.com/feedback/fb-001 | jq '{sentiment_label, sentiment_score, emotion, aspect_sentiments}'
# Expected:
# {
#   "sentiment_label": "mixed",
#   "sentiment_score": 0.2,
#   "emotion": "satisfaction",  // dominated by the positive opening
#   "aspect_sentiments": [
#     {"aspect":"search","sentiment":"positive","score":0.9},
#     {"aspect":"checkout","sentiment":"negative","score":-0.7}
#   ]
# }

# Check aggregation query
wrangler d1 execute my-db --command \
  "SELECT aspect, ROUND(AVG(score),3) as avg_score, COUNT(*) as mentions FROM feedback_aspects GROUP BY aspect ORDER BY avg_score ASC LIMIT 5;"
```

## Related

- `llm-for-classification.md` — general LLM classification patterns
- `llm-batch-processing.md` — batch processing large feedback archives
- `llm-quality-scoring-pipeline-d1.md` — storing LLM-generated scores in D1
- `llm-structured-output-json-mode.md` — JSON mode for structured LLM responses
- `ai-content-moderation-pipeline.md` — combining sentiment with moderation signals

## Sources

- Cloudflare Workers AI: https://developers.cloudflare.com/workers-ai/
- Cloudflare Queues: https://developers.cloudflare.com/queues/
- Aspect-Based Sentiment Analysis survey: https://arxiv.org/abs/2203.01054
- SemEval-2014 Task 4 ABSA benchmark: https://aclanthology.org/S14-2004/
- Cloudflare D1 SQL reference: https://developers.cloudflare.com/d1/platform/sql-statements/
