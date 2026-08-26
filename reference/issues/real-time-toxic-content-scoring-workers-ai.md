# Real-Time Toxicity Scoring at the Edge with Workers AI

- Date: 2026-08-22
- Author: example.com
- Status: production

## UGC Toxicity Scoring Before Storage

Allowing user-generated content to reach storage before any quality signal exists means toxic content persists, spreads, and causes harm before a human or async classifier catches it. The alternative — fully synchronous ML inference in the request path — introduces latency that degrades the posting experience and risks timeout cascades under load.

Workers AI enables a middle path: run a lightweight toxicity classifier on the Worker before committing content to D1 or R2. For text under ~512 tokens, inference via `@cf/jpmorganchase/roberta-toxicity-classifier-v1` (or similar) typically completes in 30-80 ms at the edge. Content that scores above a "hold" threshold is diverted to a moderation queue rather than stored immediately. Content that exceeds a "hard block" threshold is rejected outright with a user-facing error. Content below both thresholds passes through normally.

The design must account for latency budgets (most APIs budget 200 ms for content submission), model availability (Workers AI inference can queue under concurrency spikes), and graceful fallback to async scoring so that model overload does not break the posting flow.

## Context

- Runtime: Cloudflare Workers + Workers AI
- Model: `@cf/jpmorganchase/roberta-toxicity-classifier-v1` or `@cf/meta/m2m100-1.2b` for multilingual
- Storage: D1 for content records, Cloudflare Queues for async moderation
- Latency budget: 200 ms end-to-end; inference must complete within 120 ms or fall back to async

## Inline Toxicity Scoring with Latency Guard

Wrap the AI.run call in a `Promise.race` against a timeout. If inference does not complete within the budget, the content is enqueued for async scoring and the write proceeds as "pending_review" rather than "approved".

```ts
// lib/toxicity-scorer.ts
export interface ToxicityResult {
  score: number;       // 0.0 – 1.0
  label: 'toxic' | 'non-toxic';
  timedOut: boolean;
}

const INFERENCE_TIMEOUT_MS = 120;
const HOLD_THRESHOLD = 0.65;
const BLOCK_THRESHOLD = 0.92;

export async function scoreToxicity(
  text: string,
  env: Env
): Promise<ToxicityResult> {
  const timeoutPromise = new Promise<ToxicityResult>((resolve) =>
    setTimeout(() => resolve({ score: 0, label: 'non-toxic', timedOut: true }), INFERENCE_TIMEOUT_MS)
  );

  const inferencePromise = env.AI.run('@cf/jpmorganchase/roberta-toxicity-classifier-v1', {
    text,
  }).then((res: any) => {
    const top = Array.isArray(res) ? res[0] : res;
    return {
      score: top.score as number,
      label: top.label as 'toxic' | 'non-toxic',
      timedOut: false,
    };
  });

  return Promise.race([inferencePromise, timeoutPromise]);
}

export function classifyScore(score: number): 'pass' | 'hold' | 'block' {
  if (score >= BLOCK_THRESHOLD) return 'block';
  if (score >= HOLD_THRESHOLD) return 'hold';
  return 'pass';
}
```

## Content Submission Handler with Score-Based Routing

The submit handler scores the content inline, then routes to block, hold, or pass. In all non-block cases the content record is written to D1 with a `moderation_status` column that downstream systems query.

```ts
// workers/submit-content.ts
import { scoreToxicity, classifyScore } from '../lib/toxicity-scorer';

interface SubmitBody {
  userId: string;
  contentType: 'post' | 'comment' | 'bio';
  text: string;
}

export async function handleSubmit(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
  const body = await request.json<SubmitBody>();
  const { userId, contentType, text } = body;

  const result = await scoreToxicity(text, env);
  const disposition = result.timedOut ? 'hold' : classifyScore(result.score);

  if (disposition === 'block') {
    return Response.json(
      { error: 'Content violates community guidelines', code: 'TOXICITY_BLOCK' },
      { status: 422 }
    );
  }

  const contentId = crypto.randomUUID();
  const moderationStatus = result.timedOut
    ? 'pending_async'  // async job will re-score
    : disposition === 'hold'
    ? 'pending_review'
    : 'approved';

  await env.DB.prepare(
    `INSERT INTO content (id, user_id, type, text, toxicity_score, moderation_status, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?)`
  )
    .bind(contentId, userId, contentType, text, result.timedOut ? null : result.score, moderationStatus, Date.now())
    .run();

  if (disposition === 'hold' || result.timedOut) {
    ctx.waitUntil(
      env.MODERATION_QUEUE.send({
        contentId,
        userId,
        text,
        reason: result.timedOut ? 'async_rescore' : 'toxicity_hold',
        score: result.score,
        enqueuedAt: Date.now(),
      })
    );
  }

  return Response.json({ contentId, status: moderationStatus }, { status: 201 });
}
```

## Async Scoring Queue Consumer

The async consumer handles timed-out content: it re-runs inference without a deadline, updates the D1 record, and either publishes or escalates based on the final score.

```ts
// workers/async-toxicity-consumer.ts
import { scoreToxicity, classifyScore } from '../lib/toxicity-scorer';

interface ModerationMessage {
  contentId: string;
  userId: string;
  text: string;
  reason: 'async_rescore' | 'toxicity_hold';
  score: number | null;
  enqueuedAt: number;
}

export default {
  async queue(batch: MessageBatch<ModerationMessage>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const { contentId, text, reason } = msg.body;

      if (reason === 'async_rescore') {
        // Re-run without timeout
        const result = await env.AI.run('@cf/jpmorganchase/roberta-toxicity-classifier-v1', { text })
          .then((r: any) => ({ score: r[0].score as number, label: r[0].label as string }));

        const disposition = classifyScore(result.score);
        const newStatus = disposition === 'block' ? 'removed' : disposition === 'hold' ? 'pending_review' : 'approved';

        await env.DB.prepare(
          `UPDATE content SET toxicity_score = ?, moderation_status = ? WHERE id = ?`
        ).bind(result.score, newStatus, contentId).run();

        if (disposition === 'block') {
          await env.MODERATION_QUEUE.send({ contentId, action: 'auto_remove', score: result.score });
        }
      }

      msg.ack();
    }
  },
};
```

## Anti-patterns

- Running inference synchronously without a timeout — model latency spikes will break user submissions
- Blocking writes until async moderation completes — use `pending_review` status and write-through
- Using a single toxicity threshold for all content types — bio and comment toxicity may need different thresholds
- Logging full text content to D1 moderation logs — store a content hash or ID, not PII
- Trusting Workers AI scores alone without human review for high-stakes actions (bans, removals)

## Gotchas

- Workers AI `env.AI.run` is not available during local `wrangler dev` without `--remote` flag
- `@cf/jpmorganchase/roberta-toxicity-classifier-v1` truncates inputs beyond 512 tokens silently
- `Promise.race` will not cancel the losing inference — AI credit is consumed even on timeout
- Queue `max_batch_size` defaults to 5; increase for async scoring to batch DB updates efficiently
- Workers AI response shape varies by model — always inspect and type the raw response before accessing `.score`

## Verification

```ts
// Verify timeout fallback writes pending_async status
const longText = 'a '.repeat(600); // likely to trigger timeout in test
const mockEnv = buildMockEnv({ aiLatencyMs: 200 }); // exceeds 120 ms budget
const res = await handleSubmit(buildRequest({ text: longText }), mockEnv, mockCtx);
const body = await res.json<{ status: string }>();
console.assert(body.status === 'pending_async', 'Timed-out content must be pending_async');
console.assert(res.status === 201, 'Timeout must not block submission');
```

## Related

- `documentation/categories/issues/automated-dispute-resolution-d1-appeals-workflow.md`
- `documentation/categories/issues/cross-platform-content-policy-enforcement-workers.md`
- `documentation/categories/issues/platform-abuse-rate-velocity-d1-workers.md`

## Sources

- https://developers.cloudflare.com/workers-ai/models/
- https://developers.cloudflare.com/workers-ai/
- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/d1/
