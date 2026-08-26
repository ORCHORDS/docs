# AI-Powered Spam Detection for Social Platform UGC with Workers
- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

Your social platform lets users post comments, reviews, or short messages. You are
experiencing spam: duplicate promotional text, URL farms, bot-generated filler,
and coordinated inauthentic posting. Simple regex rules are being gamed within
hours. You need an ML-backed detection layer that runs at edge, evaluates each
submission before it is stored, and blocks or soft-queues suspected spam — all
without adding more than ~100 ms to the post latency.

## Context

Three complementary signals catch different spam types:

| Signal | Catches | Latency |
|---|---|---|
| Embedding similarity to known-spam vectors | Duplicate/near-duplicate spam | ~30 ms |
| Text classifier (zero-shot MNLI or fine-tuned) | Promotional / bot-generated text | ~60 ms |
| Velocity rules in KV/D1 | Coordinated accounts, burst posting | < 5 ms |

Running all three in parallel keeps p95 detection latency under 120 ms on mobile
(where network round-trips dominate). The Worker acts as a gate: submissions that
pass all three checks are forwarded to the origin; others are blocked or soft-queued.

---

## Section 1 — Bindings and Schema

```toml
# wrangler.toml
[ai]
binding = "AI"

[[vectorize]]
binding    = "SPAM_VECTORS"
index_name = "spam-embeddings"

[[kv_namespaces]]
binding = "VELOCITY"
id      = "xxxx"

[[d1_databases]]
binding       = "DB"
database_name = "ugc"
database_id   = "yyyy"
```

```sql
-- migrations/0001_spam.sql

CREATE TABLE IF NOT EXISTS ugc_submissions (
  id          TEXT PRIMARY KEY,
  author_id   TEXT NOT NULL,
  content     TEXT NOT NULL,
  spam_score  REAL,            -- composite 0-1; NULL = not scored
  disposition TEXT NOT NULL DEFAULT 'pending',  -- 'approved', 'blocked', 'review'
  created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_ugc_author ON ugc_submissions(author_id, created_at);

CREATE TABLE IF NOT EXISTS spam_patterns (
  id          TEXT PRIMARY KEY,
  pattern_vec TEXT NOT NULL,  -- JSON array — seed vectors for Vectorize
  added_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
```

---

## Section 2 — Velocity Check (KV)

The fastest and cheapest check. Block authors who exceed posting frequency limits
before spending tokens on AI.

```typescript
// src/velocity.ts
export interface Env {
  VELOCITY: KVNamespace;
}

interface VelocityLimits {
  postsPerMinute:  number;
  postsPerHour:    number;
  postsPerDay:     number;
}

const DEFAULT_LIMITS: VelocityLimits = {
  postsPerMinute: 3,
  postsPerHour:   20,
  postsPerDay:    100,
};

export async function checkVelocity(
  env: Env,
  authorId: string,
  limits = DEFAULT_LIMITS,
): Promise<{ allowed: boolean; reason?: string }> {
  const now    = Date.now();
  const minute = Math.floor(now / 60_000);
  const hour   = Math.floor(now / 3_600_000);
  const day    = Math.floor(now / 86_400_000);

  const keys = [
    `v:${authorId}:m:${minute}`,
    `v:${authorId}:h:${hour}`,
    `v:${authorId}:d:${day}`,
  ];

  // Read all three counters in one round-trip (KV.getWithMetadata not needed here)
  const [minCount, hourCount, dayCount] = await Promise.all(
    keys.map(k => env.VELOCITY.get(k).then(v => parseInt(v ?? "0", 10))),
  );

  if (minCount  >= limits.postsPerMinute)  return { allowed: false, reason: "rate_minute" };
  if (hourCount >= limits.postsPerHour)    return { allowed: false, reason: "rate_hour" };
  if (dayCount  >= limits.postsPerDay)     return { allowed: false, reason: "rate_day" };

  // Increment counters (fire-and-forget; no need to await)
  const increments = [
    env.VELOCITY.put(keys[0], String(minCount + 1),  { expirationTtl: 120 }),
    env.VELOCITY.put(keys[1], String(hourCount + 1), { expirationTtl: 7200 }),
    env.VELOCITY.put(keys[2], String(dayCount + 1),  { expirationTtl: 172800 }),
  ];
  void Promise.all(increments);  // intentionally non-blocking

  return { allowed: true };
}
```

---

## Section 3 — Embedding Similarity (Vectorize)

Catches near-duplicate promotional text: "Check out our AMAZING deals at site.com"
in a hundred slight variations.

```typescript
// src/similarity.ts
export interface Env {
  AI:           Ai;
  SPAM_VECTORS: VectorizeIndex;
}

// Threshold above which a match is classified as duplicate spam
const SIMILARITY_THRESHOLD = 0.88;

export async function checkSimilarity(
  env: Env,
  content: string,
  isMobile: boolean,
): Promise<{ isSpam: boolean; score: number; matchedId?: string }> {
  // Truncate very long posts for embedding (model context limit)
  const text = content.slice(0, isMobile ? 256 : 512);

  const embeddingResponse = await env.AI.run("@cf/baai/bge-small-en-v1.5", {
    text: [text],
  });

  const vector = (embeddingResponse as any).data[0] as number[];

  const results = await env.SPAM_VECTORS.query(vector, {
    topK:          1,
    returnMetadata: "none",
    returnValues:  false,
    filter:        { type: { $eq: "spam" } },
  });

  if (!results.matches.length) return { isSpam: false, score: 0 };

  const topScore = results.matches[0].score;
  return {
    isSpam:    topScore >= SIMILARITY_THRESHOLD,
    score:     topScore,
    matchedId: topScore >= SIMILARITY_THRESHOLD ? results.matches[0].id : undefined,
  };
}

// Called by moderators when confirming a spam post — seeds future detection
export async function addSpamVector(
  env: Env,
  id: string,
  content: string,
): Promise<void> {
  const embeddingResponse = await env.AI.run("@cf/baai/bge-small-en-v1.5", {
    text: [content.slice(0, 512)],
  });
  const vector = (embeddingResponse as any).data[0] as number[];
  await env.SPAM_VECTORS.upsert([{ id, values: vector, metadata: { type: "spam" } }]);
}
```

---

## Section 4 — Text Classifier (Zero-Shot)

Catches promotional, inauthentic, or bot-like content that does not match existing
spam vectors — handles novel campaigns.

```typescript
// src/classifier.ts
export interface Env {
  AI: Ai;
}

export interface ClassifierResult {
  isSpam:    boolean;
  spamScore: number;   // 0-1
  category:  string;  // "promotional", "bot-generated", "legitimate", etc.
}

const SPAM_LABELS = ["promotional spam", "bot-generated filler", "phishing link"];
const HAM_LABEL   = "genuine user content";
const ALL_LABELS  = [...SPAM_LABELS, HAM_LABEL];

export async function classifyText(
  env: Env,
  content: string,
  isMobile: boolean,
): Promise<ClassifierResult> {
  // Use shorter content slice on mobile to reduce classifier latency
  const text = content.slice(0, isMobile ? 150 : 400);

  const response = await env.AI.run("@cf/huggingface/distilbart-mnli-12-1", {
    text,
    candidate_labels: ALL_LABELS,
  });

  const res     = response as { labels: string[]; scores: number[] };
  const hamIdx  = res.labels.indexOf(HAM_LABEL);
  const hamScore = res.scores[hamIdx] ?? 0;

  // Spam score = 1 - ham probability
  const spamScore = 1 - hamScore;

  // Find highest spam label
  let topSpamLabel = "promotional spam";
  let topSpamScore = 0;
  for (const label of SPAM_LABELS) {
    const idx   = res.labels.indexOf(label);
    const score = res.scores[idx] ?? 0;
    if (score > topSpamScore) { topSpamScore = score; topSpamLabel = label; }
  }

  return {
    isSpam:    spamScore > 0.60,
    spamScore,
    category:  spamScore > 0.60 ? topSpamLabel : "legitimate",
  };
}
```

---

## Section 5 — Unified Gate Handler

```typescript
// src/index.ts
import { checkVelocity }   from "./velocity";
import { checkSimilarity } from "./similarity";
import { classifyText }    from "./classifier";

export interface Env {
  AI:           Ai;
  SPAM_VECTORS: VectorizeIndex;
  VELOCITY:     KVNamespace;
  DB:           D1Database;
  ORIGIN:       Fetcher;  // service binding to the actual API
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    if (req.method !== "POST") return env.ORIGIN.fetch(req);

    const body      = await req.json<{ authorId: string; content: string }>();
    const authorId  = body.authorId;
    const content   = body.content ?? "";
    const ua        = req.headers.get("User-Agent") ?? "";
    const isMobile  = /Mobile|Android|iPhone|iPad/.test(ua);

    // 1. Velocity check — synchronous, fast
    const velocity = await checkVelocity(env, authorId);
    if (!velocity.allowed) {
      return new Response(
        JSON.stringify({ error: "Rate limit exceeded", code: velocity.reason }),
        { status: 429, headers: { "Content-Type": "application/json" } },
      );
    }

    // 2. Run similarity + classifier in parallel
    const [similarity, classifier] = await Promise.all([
      checkSimilarity(env, content, isMobile),
      classifyText(env, content, isMobile),
    ]);

    // 3. Composite score (weighted)
    const compositeSpamScore =
      similarity.score * 0.5 + classifier.spamScore * 0.5;

    // 4. Disposition
    let disposition: "approved" | "blocked" | "review";
    if (similarity.isSpam) {
      disposition = "blocked";  // high confidence near-duplicate
    } else if (compositeSpamScore > 0.75) {
      disposition = "blocked";
    } else if (compositeSpamScore > 0.50) {
      disposition = "review";   // human moderator queue
    } else {
      disposition = "approved";
    }

    // 5. Persist submission with scores
    const submissionId = crypto.randomUUID();
    await env.DB.prepare(
      `INSERT INTO ugc_submissions (id, author_id, content, spam_score, disposition)
       VALUES (?1, ?2, ?3, ?4, ?5)`,
    )
      .bind(submissionId, authorId, content, compositeSpamScore, disposition)
      .run();

    if (disposition === "blocked") {
      return new Response(
        JSON.stringify({ error: "Content blocked", id: submissionId }),
        { status: 422, headers: { "Content-Type": "application/json" } },
      );
    }

    if (disposition === "review") {
      // Return 202 Accepted — content visible after moderation
      return new Response(
        JSON.stringify({ status: "pending_review", id: submissionId }),
        { status: 202, headers: { "Content-Type": "application/json" } },
      );
    }

    // Approved — forward to origin
    const originReq = new Request(req.url, {
      method:  req.method,
      headers: req.headers,
      body:    JSON.stringify({ ...body, submissionId }),
    });

    return env.ORIGIN.fetch(originReq);
  },
};
```

---

## Anti-patterns

- **Only using regex** — motivated spammers rotate wording within hours. ML-backed
  similarity and zero-shot classification are essential for durability.
- **Running all checks sequentially** — velocity + similarity + classification in
  series adds 200+ ms; `Promise.all` on the AI checks brings p95 down under 100 ms.
- **Too-low a similarity threshold** — setting the Vectorize threshold at 0.75
  catches lots of legitimate posts with common phrases ("check this out"). Calibrate
  on real traffic with a confusion matrix; 0.85–0.92 is typically the right range.
- **Hard-blocking review-category content** — returning 422 for 0.50–0.75 spam
  score means false-positive blocking for borderline content. Use 202 + queue
  instead; human moderators resolve.
- **Not feeding confirmed spam back to Vectorize** — the similarity check only
  improves over time if you call `addSpamVector` when a moderator confirms spam.
  Build a moderator action webhook that calls this.

---

## Gotchas

- KV `put` with `expirationTtl` is eventually consistent — in rare cases a counter
  may be under-counted in the same minute across edge nodes. Accept this small
  error; exact velocity counting requires Durable Objects.
- Vectorize metadata filtering (`{ type: { $eq: "spam" } }`) requires the metadata
  field to be indexed. Declare it in `wrangler.toml`:
  ```toml
  [[vectorize]]
  binding    = "SPAM_VECTORS"
  index_name = "spam-embeddings"
  [[vectorize.metadata_indexes]]
  property_name = "type"
  index_type    = "string"
  ```
- `@cf/huggingface/distilbart-mnli-12-1` input is capped at 1 024 tokens. Posts
  longer than ~750 words must be truncated before passing to avoid a 400 error.
- The composite score combines an L2-normalised cosine similarity (Vectorize) and
  an un-calibrated MNLI probability — both happen to live in [0, 1] but have
  different distributions. Consider isotonic regression calibration offline if
  high precision is needed.
- Mobile clients posting large text bodies (long reviews) will have content
  truncated to 150 chars for the classifier. This is a trade-off: full precision
  costs ~40 ms extra. Adjust the cut-off based on your platform's average post
  length.

---

## Verification

```bash
# Check the last 100 blocked submissions
wrangler d1 execute ugc --command \
  "SELECT disposition, COUNT(*), AVG(spam_score)
     FROM ugc_submissions
    WHERE created_at >= datetime('now', '-1 day')
   GROUP BY disposition;"

# Check velocity counters for a specific user (KV)
wrangler kv key get --namespace-id=<id> "v:<authorId>:m:$(date +%s | awk '{print int($1/60)}')"
```

End-to-end smoke test:

```bash
# Should return 422 (blocked)
curl -X POST https://your-worker.workers.dev/post \
  -H "Content-Type: application/json" \
  -d '{"authorId":"test-bot-1","content":"Buy cheap followers! Visit spam-site.com for AMAZING deals!!!"}'

# Should return 200 (approved)
curl -X POST https://your-worker.workers.dev/post \
  -H "Content-Type: application/json" \
  -d '{"authorId":"test-user-2","content":"Really enjoyed this track, the synth pads in the bridge were beautiful."}'
```

---

## Related

- `ai-content-moderation-pipeline.md` — broader content moderation pipeline
- `ai-content-moderation-nsfw-detection-workers.md` — image moderation
- `workers-ai-text-classification-moderation.md` — text classification fundamentals
- `llm-prompt-injection-defense-workers.md` — defending against adversarial inputs
- `ai-gateway-rate-limiting.md` — rate limiting at the AI Gateway level

---

## Sources

- Cloudflare Vectorize metadata filtering: https://developers.cloudflare.com/vectorize/reference/metadata-filtering/
- Workers AI DistilBart MNLI: https://developers.cloudflare.com/workers-ai/models/distilbart-mnli-12-1/
- Workers KV TTL: https://developers.cloudflare.com/kv/api/write-key-value-pairs/#expiring-keys
- Zero-shot classification with NLI: https://joeddav.github.io/blog/2020/05/29/ZSL.html
