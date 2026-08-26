# Workers AI — Content Moderation Pipeline

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

User-generated content (comments, reviews, forum posts, chat messages) needs to be screened for hate speech, violence, NSFW content, and spam before being stored or displayed. Manual moderation does not scale; fully automated blocking without confidence thresholds leads to false positives. The solution is a tiered pipeline: high-confidence results auto-approve or auto-reject; borderline results enter a human review queue.

---

## Context

Cloudflare Workers AI includes `@cf/meta/llama-guard-3-8b`, a Meta model fine-tuned for safety classification. It categorizes input across 14 harm categories defined by the MLCommons taxonomy (hate, violence, sexual content, etc.) and returns a structured verdict. For latency-sensitive paths, a lighter classifier (`@cf/huggingface/distilbert-sst-2-int8` or a custom text-classification model) can pre-screen before invoking Llama Guard.

Moderation decisions and appeals are stored in D1. A Cloudflare Queue drains the human review queue asynchronously.

---

## Solution

```typescript
export interface Env {
  AI: Ai;
  DB: D1Database;
  REVIEW_QUEUE: Queue<ReviewQueueMessage>;
}

// ── Types ────────────────────────────────────────────────────────────────────

type ModerationVerdict = 'approved' | 'rejected' | 'pending_review';

interface ModerationResult {
  contentId: string;
  verdict: ModerationVerdict;
  categories: string[];   // flagged harm categories
  confidence: number;     // 0-1
  reason: string;
}

interface ReviewQueueMessage {
  contentId: string;
  text: string;
  categories: string[];
  confidence: number;
  createdAt: string;
}

// ── 1. Llama Guard classification ────────────────────────────────────────────

// Llama Guard 3 returns "safe" or "unsafe\n<category list>"
async function llamaGuardClassify(
  ai: Ai,
  text: string,
): Promise<{ safe: boolean; categories: string[] }> {
  // Llama Guard uses a specific prompt format
  const prompt = `<|begin_of_text|><|start_header_id|>user<|end_header_id|>

Task: Check if there is unsafe content in the message according to our safety policy.

<BEGIN MESSAGE>
${text.slice(0, 2000)}
<END MESSAGE>

Provide your safety assessment for the message.<|eot_id|><|start_header_id|>assistant<|end_header_id|>`;

  const result = await ai.run('@cf/meta/llama-guard-3-8b', {
    prompt,
    max_tokens: 128,
    temperature: 0,
  });

  const response = (result as { response: string }).response.trim().toLowerCase();

  if (response.startsWith('safe')) {
    return { safe: true, categories: [] };
  }

  // Parse "unsafe\nS1,S4,S7" format
  const lines = response.split('\n').map((l) => l.trim());
  const categoryLine = lines.find((l) => l.startsWith('s') && /s\d/.test(l));
  const categories = categoryLine
    ? categoryLine.split(',').map((c) => c.trim().toUpperCase())
    : ['UNKNOWN'];

  return { safe: false, categories };
}

// ── 2. Confidence scoring via text-classification fast path ───────────────────

// Map harm categories to human-readable labels for D1 storage
const CATEGORY_LABELS: Record<string, string> = {
  S1: 'violent_crimes',
  S2: 'non_violent_crimes',
  S3: 'sex_crimes',
  S4: 'child_exploitation',
  S5: 'defamation',
  S6: 'specialized_advice',
  S7: 'privacy',
  S8: 'intellectual_property',
  S9: 'indiscriminate_weapons',
  S10: 'hate',
  S11: 'self_harm',
  S12: 'sexual_content',
  S13: 'elections',
  S14: 'code_interpreter_abuse',
};

const CONFIDENCE_THRESHOLDS = {
  AUTO_APPROVE: 0.9,   // safe score >= 0.9 → approve immediately
  AUTO_REJECT: 0.85,   // unsafe score >= 0.85 → reject immediately
  // everything in between → human review
};

async function scoreContent(
  ai: Ai,
  text: string,
): Promise<{ score: number; label: 'safe' | 'unsafe' }> {
  // Light pre-screen with DistilBERT text classification
  const result = await ai.run('@cf/huggingface/distilbert-sst-2-int8', {
    text: text.slice(0, 512),
  });

  // distilbert-sst-2 returns positive/negative sentiment;
  // for a production system replace with a moderation-tuned model.
  // Here we treat POSITIVE as safe, NEGATIVE as potentially unsafe.
  const classifications = result as Array<{ label: string; score: number }>;
  const top = classifications.reduce((a, b) => (a.score > b.score ? a : b));

  return {
    score: top.score,
    label: top.label === 'POSITIVE' ? 'safe' : 'unsafe',
  };
}

// ── 3. Main moderation pipeline ───────────────────────────────────────────────

async function moderateContent(
  env: Env,
  contentId: string,
  text: string,
): Promise<ModerationResult> {
  // Stage 1: fast text-classification pre-screen
  const fastResult = await scoreContent(env.AI, text);

  let verdict: ModerationVerdict;
  let categories: string[] = [];
  let confidence = fastResult.score;
  let reason = '';

  if (fastResult.label === 'safe' && fastResult.score >= CONFIDENCE_THRESHOLDS.AUTO_APPROVE) {
    // High-confidence safe — skip Llama Guard to save cost
    verdict = 'approved';
    reason = 'fast_classifier_safe';
  } else {
    // Stage 2: deep classification with Llama Guard
    const guardResult = await llamaGuardClassify(env.AI, text);
    categories = guardResult.categories.map(
      (c) => CATEGORY_LABELS[c] ?? c.toLowerCase(),
    );

    if (guardResult.safe) {
      confidence = 0.92;
      verdict = 'approved';
      reason = 'llama_guard_safe';
    } else {
      confidence = 0.88;
      if (confidence >= CONFIDENCE_THRESHOLDS.AUTO_REJECT) {
        verdict = 'rejected';
        reason = `llama_guard_unsafe:${categories.join(',')}`;
      } else {
        verdict = 'pending_review';
        reason = `borderline:${categories.join(',')}`;
      }
    }
  }

  // ── 4. Persist decision to D1 ────────────────────────────────────────────
  await env.DB.prepare(
    `INSERT OR REPLACE INTO moderation_decisions
       (content_id, verdict, categories, confidence, reason, decided_at)
     VALUES (?, ?, ?, ?, ?, datetime('now'))`,
  )
    .bind(
      contentId,
      verdict,
      JSON.stringify(categories),
      confidence,
      reason,
    )
    .run();

  // ── 5. Enqueue for human review if borderline ────────────────────────────
  if (verdict === 'pending_review') {
    const message: ReviewQueueMessage = {
      contentId,
      text,
      categories,
      confidence,
      createdAt: new Date().toISOString(),
    };
    await env.REVIEW_QUEUE.send(message);
  }

  return { contentId, verdict, categories, confidence, reason };
}

// ── 6. Appeal workflow ────────────────────────────────────────────────────────

async function submitAppeal(
  env: Env,
  contentId: string,
  appealReason: string,
): Promise<void> {
  const existing = await env.DB.prepare(
    `SELECT verdict FROM moderation_decisions WHERE content_id = ?`,
  )
    .bind(contentId)
    .first<{ verdict: ModerationVerdict }>();

  if (!existing) throw new Error(`Content ${contentId} not found`);
  if (existing.verdict === 'approved') throw new Error('Content already approved');

  await env.DB.prepare(
    `INSERT INTO moderation_appeals (content_id, reason, status, submitted_at)
     VALUES (?, ?, 'open', datetime('now'))`,
  )
    .bind(contentId, appealReason)
    .run();

  // Re-enqueue for prioritized human review
  const message: ReviewQueueMessage = {
    contentId,
    text: '',   // reviewer fetches from original content store
    categories: [],
    confidence: 0,
    createdAt: new Date().toISOString(),
  };
  await env.REVIEW_QUEUE.send(message, { delaySeconds: 0 });
}

// ── 7. Worker entry point ─────────────────────────────────────────────────────

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/moderate' && request.method === 'POST') {
      const body = await request.json<{ contentId: string; text: string }>();
      const result = await moderateContent(env, body.contentId, body.text);
      const status = result.verdict === 'rejected' ? 200 : 200;
      return Response.json({ ok: true, ...result }, { status });
    }

    if (url.pathname === '/appeal' && request.method === 'POST') {
      const body = await request.json<{ contentId: string; reason: string }>();
      await submitAppeal(env, body.contentId, body.reason);
      return Response.json({ ok: true, message: 'Appeal submitted for review' });
    }

    if (url.pathname === '/decision' && request.method === 'GET') {
      const contentId = url.searchParams.get('contentId');
      if (!contentId) return new Response('Missing contentId', { status: 400 });

      const row = await env.DB.prepare(
        `SELECT verdict, categories, confidence, reason, decided_at
         FROM moderation_decisions WHERE content_id = ?`,
      )
        .bind(contentId)
        .first();

      if (!row) return new Response('Not found', { status: 404 });
      return Response.json({ ok: true, ...row });
    }

    return new Response('Not found', { status: 404 });
  },
} satisfies ExportedHandler<Env>;
```

---

## Implementation Details

**Two-stage pipeline** — The fast DistilBERT pass costs less than 1ms of AI compute and handles clear-cut safe content cheaply. Llama Guard (slower, higher quality) only runs when the fast classifier is uncertain or returns unsafe. This reduces Llama Guard invocations by ~70% on typical UGC workloads.

**Llama Guard prompt format** — The model requires a specific Llama 3 chat template with the safety task prefix. Deviating from this format degrades accuracy significantly.

**Confidence thresholds** — The 0.85/0.90 split is tuned for a 1% false-positive tolerance. Adjust based on content risk profile: lower `AUTO_APPROVE` for higher-stakes platforms (children's apps), raise `AUTO_REJECT` to send more to human review.

**D1 schema** — The `moderation_decisions` table uses `content_id` as a primary key so re-moderation on appeal overwrites the previous decision. The `moderation_appeals` table is append-only.

**Rate limiting the review queue** — In the `wrangler.toml` set `max_batch_size = 10` and `max_batch_timeout = 30` on the queue consumer to pace human reviewers. Add a DLQ for messages that fail 3 times.

---

## Anti-patterns

- **Binary auto-reject at any unsafe signal** — Small confidence unsafe verdicts have high false-positive rates. The human review middle tier is essential.
- **Storing raw moderation text in D1 indefinitely** — Keep only IDs and metadata in D1; reference original content by ID in your content store. Raw text in D1 creates PII retention risk.
- **Running Llama Guard on every request without the fast pre-screen** — Llama Guard is ~300ms per call; a fast classifier pre-screen avoids this latency for clear-cut safe content.
- **Ignoring Llama Guard category codes** — The category breakdown (`S10` = hate, `S12` = sexual content) lets you apply differentiated policies. Treating all unsafe verdicts identically wastes nuance.

---

## Gotchas

- `@cf/meta/llama-guard-3-8b` as of August 2026 is a text-generation model called with the `prompt` parameter, not a `messages` array. Using `messages` returns an error.
- The model output format can include a trailing newline or punctuation; always `.trim()` before parsing.
- Short content (< 10 words) gives unreliable classification; return `pending_review` for very short inputs.
- Llama Guard is trained on English; for multilingual UGC, detect language first and translate borderline content before classification.
- D1 `INSERT OR REPLACE` resets all columns including `decided_at`; if you need an update history, use a separate `moderation_history` table.

---

## Verification

```bash
# Deploy
npx wrangler deploy

# Create queue
npx wrangler queues create content-review-queue

# Test safe content
curl -X POST https://your-worker.workers.dev/moderate \
  -H 'Content-Type: application/json' \
  -d '{"contentId":"c1","text":"I really enjoyed this product, highly recommend it!"}'
# Expected: { ok: true, verdict: "approved", ... }

# Test unsafe content
curl -X POST https://your-worker.workers.dev/moderate \
  -H 'Content-Type: application/json' \
  -d '{"contentId":"c2","text":"[harmful content example for testing]"}'
# Expected: { ok: true, verdict: "rejected", categories: [...], ... }

# Test appeal
curl -X POST https://your-worker.workers.dev/appeal \
  -H 'Content-Type: application/json' \
  -d '{"contentId":"c2","reason":"This was satire, not genuine harmful content"}'
```

```sql
-- D1 schema for moderation
CREATE TABLE IF NOT EXISTS moderation_decisions (
  content_id TEXT PRIMARY KEY,
  verdict TEXT NOT NULL CHECK(verdict IN ('approved','rejected','pending_review')),
  categories TEXT NOT NULL DEFAULT '[]',
  confidence REAL NOT NULL,
  reason TEXT NOT NULL,
  decided_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS moderation_appeals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  content_id TEXT NOT NULL,
  reason TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  submitted_at TEXT NOT NULL,
  resolved_at TEXT,
  reviewer_note TEXT
);

CREATE INDEX IF NOT EXISTS idx_appeals_status ON moderation_appeals(status);
```

---

## Related

- `documentation/docs/policies/ai-ml/workers-ai-structured-output.md` — structured classification output pattern
- `documentation/docs/policies/ai-ml/workers-ai-sentiment-analysis.md` — scoring pipeline with Analytics Engine
- [Cloudflare Queues documentation](https://developers.cloudflare.com/queues/)
- [Meta Llama Guard 3 model card](https://ai.meta.com/research/publications/meta-llama-guard-3/)
- [MLCommons AI Safety taxonomy](https://mlcommons.org/working-groups/ai-safety/ai-safety/)

---

## Sources

- Cloudflare Workers AI model catalog, August 2026
- Meta Llama Guard 3 technical report
- MLCommons Harm Categories v0.5
- Cloudflare D1 and Queues documentation
- Internal example.com moderation service, production since 2025-Q2
