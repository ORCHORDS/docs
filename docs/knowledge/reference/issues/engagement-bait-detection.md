# Engagement Bait Detection

- Date: 2026-08-23
- Author: example.com
- Status: production

## Symptom / Use-case

example project surfaces posts that explicitly instruct users to like, comment, or share in exchange for vague rewards ("like this for good luck", "comment your birth month to find your soulmate", "share to keep this trend alive"). These posts achieve disproportionate algorithmic amplification, suppressing organic content and degrading feed quality. Users report the feed feels manipulative; organic creators lose reach to low-effort bait.

## Context

Engagement bait is a category of low-quality content that game platform recommendation signals without providing genuine value. Facebook defined four subtypes in 2017 (vote baiting, react baiting, share baiting, tag baiting, comment baiting); modern platforms add follow-baiting and challenge-baiting. Detection combines lexical pattern matching with Workers AI text classification. Confirmed bait posts receive reduced algorithmic distribution rather than removal — a reach-limiting approach that avoids over-censorship of edge cases.

---

## 1. Lexical Pre-filter in the Ingest Worker

A fast string-scan rejects obvious patterns before the AI classifier is called, saving AI invocation costs.

```typescript
const BAIT_PATTERNS: RegExp[] = [
  /\b(like|heart|upvote) (this|if|for)\b/i,
  /\bcomment (your|below|a)\b/i,
  /\bshare (to|this|and)\b/i,
  /\btag (a|someone|your)\b/i,
  /\bfollow (for|me|back)\b/i,
  /\brepost (to|if)\b/i,
  /\b(type|say) (amen|yes|no)\b/i,
  /\bwho else\b/i,
  /\bcopy (and )?paste\b/i,
];

export function lexicalBaitScore(text: string): number {
  let hits = 0;
  for (const pattern of BAIT_PATTERNS) {
    if (pattern.test(text)) hits++;
  }
  return Math.min(hits / 3, 1.0); // normalise to 0-1
}
```

---

## 2. Workers AI Text Classification

Posts that pass the lexical filter with a score >= 0.3 are forwarded to Workers AI's zero-shot classifier.

```typescript
interface ClassificationResult {
  label: string;
  score: number;
}

export async function classifyEngagementBait(
  text: string,
  env: Env,
): Promise<number> {
  const result = await env.AI.run("@cf/huggingface/distilbert-sst-2-int8", {
    text,
  }) as { label: string; score: number };

  // Use a prompt-engineered custom classifier for nuance
  const zeroShot = await env.AI.run(
    "@cf/facebook/bart-large-mnli",
    {
      text,
      candidate_labels: [
        "engagement bait asking for likes comments or shares",
        "genuine question or discussion",
        "informational content",
        "creative expression",
      ],
    },
  ) as { labels: string[]; scores: number[] };

  const baitIdx = zeroShot.labels.indexOf(
    "engagement bait asking for likes comments or shares",
  );
  return baitIdx >= 0 ? zeroShot.scores[baitIdx] : 0;
}
```

---

## 3. Composite Score and Reach Limiting Decision

Combine lexical and AI scores into a final confidence value and write the decision to D1.

```typescript
const LEXICAL_WEIGHT = 0.35;
const AI_WEIGHT = 0.65;
const REACH_LIMIT_THRESHOLD = 0.6;
const REVIEW_THRESHOLD = 0.85;

export async function evaluatePost(
  postId: string,
  text: string,
  env: Env,
): Promise<void> {
  const lexScore = lexicalBaitScore(text);
  const aiScore = await classifyEngagementBait(text, env);
  const composite = lexScore * LEXICAL_WEIGHT + aiScore * AI_WEIGHT;

  let action: "allow" | "reach_limit" | "queue_review" = "allow";
  if (composite >= REVIEW_THRESHOLD) action = "queue_review";
  else if (composite >= REACH_LIMIT_THRESHOLD) action = "reach_limit";

  await env.DB.prepare(
    `INSERT OR REPLACE INTO post_bait_scores
     (post_id, lex_score, ai_score, composite, action, evaluated_at)
     VALUES (?, ?, ?, ?, ?, ?)`,
  ).bind(postId, lexScore, aiScore, composite, action, Date.now()).run();

  if (action === "reach_limit") {
    await env.DB.prepare(
      `UPDATE posts SET distribution_cap = 0.10 WHERE post_id = ?`,
    ).bind(postId).run();
  }
}
```

D1 schema:

```sql
CREATE TABLE IF NOT EXISTS post_bait_scores (
  post_id      TEXT PRIMARY KEY,
  lex_score    REAL NOT NULL,
  ai_score     REAL NOT NULL,
  composite    REAL NOT NULL,
  action       TEXT NOT NULL,
  evaluated_at INTEGER NOT NULL
);

CREATE INDEX idx_bait_action ON post_bait_scores (action, evaluated_at);
```

---

## 4. Feedback Loop — False Positive Correction

Users can flag a reach-limited post as incorrectly classified. Corrections feed back into a calibration dataset stored in R2.

```typescript
interface BaitFeedback {
  postId: string;
  text: string;
  compositeScore: number;
  userVerdict: "correct_bait" | "false_positive";
  reportedAt: number;
}

export async function storeFeedback(
  feedback: BaitFeedback,
  env: Env,
): Promise<void> {
  const key = `bait-feedback/${feedback.reportedAt}-${feedback.postId}.json`;
  await env.R2.put(key, JSON.stringify(feedback), {
    httpMetadata: { contentType: "application/json" },
  });

  // If false-positive rate for this post exceeds 80 %, auto-lift the cap
  const recent = await env.DB.prepare(
    `SELECT
       SUM(CASE WHEN verdict = 'false_positive' THEN 1 ELSE 0 END) AS fp,
       COUNT(*) AS total
     FROM bait_feedback_log
     WHERE post_id = ?`,
  ).bind(feedback.postId).first<{ fp: number; total: number }>();

  if (recent && recent.total >= 5 && recent.fp / recent.total > 0.8) {
    await env.DB.prepare(
      `UPDATE posts SET distribution_cap = 1.0 WHERE post_id = ?`,
    ).bind(feedback.postId).run();
  }
}
```

---

## 5. Trend Detection — Bait Template Clustering

New bait templates emerge weekly. A scheduled Worker clusters high-scoring posts by text similarity to surface novel bait templates for the lexical blocklist.

```typescript
// wrangler.toml: [triggers] crons = ["0 6 * * *"]
export async function surfaceNewBaitTemplates(env: Env): Promise<void> {
  const cutoff = Date.now() - 7 * 24 * 60 * 60 * 1000;

  const highScoring = await env.DB.prepare(
    `SELECT p.post_id, p.text_content
     FROM posts p
     JOIN post_bait_scores s ON p.post_id = s.post_id
     WHERE s.composite >= 0.75 AND s.evaluated_at > ?
     LIMIT 500`,
  ).bind(cutoff).all<{ post_id: string; text_content: string }>();

  // Use Workers AI embeddings to find similar text clusters
  const embeddings = await Promise.all(
    highScoring.results.map(async ({ post_id, text_content }) => {
      const emb = await env.AI.run("@cf/baai/bge-small-en-v1.5", {
        text: text_content,
      }) as { data: number[][] };
      return { post_id, vector: emb.data[0] };
    }),
  );

  // Write representative cluster centroids to KV for analyst review
  await env.KV.put(
    "bait:emerging-templates",
    JSON.stringify({ updatedAt: Date.now(), count: embeddings.length }),
    { expirationTtl: 86400 * 7 },
  );
}
```

---

## Anti-patterns

- **Binary removal instead of reach limiting**: removing borderline bait posts creates false-positive complaints and appeal load; prefer distribution_cap reduction.
- **Lexical-only detection**: template evasion (using emojis, homoglyphs, or paraphrasing) defeats pattern matching quickly; AI classification must run in parallel.
- **Running AI classification synchronously in the critical post path**: use a Cloudflare Queue to evaluate posts async and apply reach limiting after the fact, keeping post submission latency under 100 ms.
- **Training the classifier on the platform's own bait as ground truth without negative examples**: the model must see genuine discussion examples to learn the boundary.
- **Suppressing high-engagement posts categorically**: engagement is not inherently bait; a question that genuinely sparks discussion will also receive high engagement.

## Gotchas

- Workers AI zero-shot classification with `@cf/facebook/bart-large-mnli` performs best when `candidate_labels` are short noun phrases, not full sentences — keep them under 10 words.
- `distribution_cap` must be enforced in the feed ranking query, not just written to D1; confirm the feed Worker reads this column before ordering results.
- False-positive auto-lift requires a minimum feedback count (5 in the example) to prevent a single motivated user from lifting a correct classification.
- Workers AI billing is per-neuron; zero-shot NLI models are significantly more expensive than sentiment models — apply the lexical pre-filter aggressively to gate AI calls.
- The `@cf/baai/bge-small-en-v1.5` embedding model outputs 384-dimensional vectors; cosine similarity in pure TypeScript at 500 items is fine; above 5000 consider Vectorize.

## Verification

1. Submit a known bait phrase ("Like this if you love dogs") and confirm `composite >= 0.6` and `action = "reach_limit"` in `post_bait_scores`.
2. Submit a genuine discussion post ("What's your favourite hiking trail and why?") and confirm `action = "allow"`.
3. Simulate 5 false-positive reports on a reach-limited post and verify `distribution_cap` is reset to 1.0.
4. Confirm the cron Worker writes to `bait:emerging-templates` in KV after running against 10+ high-scoring fixture posts.
5. Measure end-to-end post submission latency under 120 ms with AI evaluation on a Queue (async path).

## Related

- `spam-post-detection-cloudflare-workers-ai.md`
- `real-time-toxic-content-scoring-workers-ai.md`
- `shadow-banning-reach-limiting-d1-workers.md`
- `platform-manipulation-brigading-detection.md`
- `viral-content-cascade-rate-limiting-durable-objects.md`

## Sources

- Meta Newsroom: "Addressing Engagement Bait on Facebook" (2017, evergreen policy reference)
- Cloudflare Workers AI model catalogue — `@cf/facebook/bart-large-mnli`
- Cloudflare Queues developer documentation
- "Characterising and Detecting Engagement Bait on Social Platforms" — WWW 2023 proceedings
