# Report Queue Prioritization with Workers Queues and AI Scoring

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project (example.com) receives thousands of user-submitted content reports per day. On an anonymous platform, the reporter has no verified identity and the reported content ranges from obvious CSAM or threats to petty disagreements and false-flag reporting campaigns. Without prioritization, a linear FIFO queue means a death threat buried under fifty "this post is mean" reports waits for hours before a human moderator sees it.

The operational symptom is that moderator response SLA for severity-1 events (child safety, imminent harm, coordinated harassment) is not met because the queue is saturated with low-severity noise. AI-powered scoring at enqueue time, combined with Cloudflare Queues consumer-side routing, solves this by dispatching each report to a severity-appropriate consumer immediately.

## Context

Cloudflare Queues supports multiple named queues and dead-letter queues but does not natively support priority lanes within a single queue. The example project architecture uses three queues: `reports-critical`, `reports-standard`, and `reports-low`, each with a dedicated consumer Worker. A Triage Worker sits at ingestion, runs Workers AI classification on the incoming report, and routes to the appropriate queue.

Scores are persisted to D1 immediately so that moderators who pull a report also see the AI reasoning without re-running classification. The scoring model is augmented by account-level signals from D1 — prior violation history, cluster risk score, and reporter credibility — that are unavailable to the AI model on its own.

## Triage Worker: AI Scoring and Queue Routing

The Triage Worker receives raw user reports via HTTP POST, enriches them with D1 account signals, runs Workers AI classification, and dispatches to the correct queue.

```typescript
// worker: report-triage.ts
export interface Env {
  DB: D1Database;
  AI: Ai;
  REPORTS_CRITICAL: Queue;
  REPORTS_STANDARD: Queue;
  REPORTS_LOW: Queue;
}

type ReportCategory =
  | 'csam'
  | 'imminent_harm'
  | 'hate_speech'
  | 'harassment'
  | 'spam'
  | 'misinformation'
  | 'copyright'
  | 'other';

interface InboundReport {
  reporterId: string;
  contentId: string;
  contentType: 'post' | 'comment' | 'dm' | 'profile';
  category: ReportCategory;
  description: string;
  contentSnippet?: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    const body = await request.json<InboundReport>();
    if (!body.reporterId || !body.contentId || !body.category) {
      return new Response('Missing required fields', { status: 400 });
    }

    const reportId = crypto.randomUUID();

    const [accountRisk, reporterCredibility] = await Promise.all([
      fetchAccountRisk(env.DB, body.contentId),
      fetchReporterCredibility(env.DB, body.reporterId),
    ]);

    const { aiScore, aiCategory, aiReasoning } = await classifyReport(env.AI, body);
    const finalScore = blendScore({ aiScore, accountRisk, reporterCredibility, userCategory: body.category });
    const priority = scoreToPriority(finalScore, body.category);

    // Persist before enqueuing so the record survives a consumer crash
    await env.DB.prepare(`
      INSERT INTO content_reports
        (report_id, reporter_id, content_id, content_type, user_category,
         ai_score, ai_category, ai_reasoning, account_risk, reporter_credibility,
         final_score, priority, status, created_at)
      VALUES (?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,?11,?12,'queued',unixepoch())
    `).bind(reportId, body.reporterId, body.contentId, body.contentType,
             body.category, aiScore, aiCategory, aiReasoning, accountRisk,
             reporterCredibility, finalScore, priority).run();

    const queue = priority === 'critical'
      ? env.REPORTS_CRITICAL
      : priority === 'standard'
        ? env.REPORTS_STANDARD
        : env.REPORTS_LOW;

    await queue.send({ reportId, priority, contentId: body.contentId, aiCategory, finalScore });

    return new Response(JSON.stringify({ reportId, priority }), {
      status: 202,
      headers: { 'Content-Type': 'application/json' },
    });
  },
};

async function fetchAccountRisk(db: D1Database, contentId: string): Promise<number> {
  const row = await db.prepare(`
    SELECT ac.risk_score
    FROM content c
    JOIN account_cluster_members acm ON acm.account_id = c.author_id
    JOIN account_clusters ac ON ac.cluster_id = acm.cluster_id
    WHERE c.content_id = ?1
  `).bind(contentId).first<{ risk_score: number }>();
  return row?.risk_score ?? 0;
}

async function fetchReporterCredibility(db: D1Database, reporterId: string): Promise<number> {
  const row = await db.prepare(
    'SELECT credibility_score FROM reporter_credibility WHERE reporter_id = ?1'
  ).bind(reporterId).first<{ credibility_score: number }>();
  return row?.credibility_score ?? 0.5;
}

async function classifyReport(
  ai: Ai,
  report: InboundReport
): Promise<{ aiScore: number; aiCategory: string; aiReasoning: string }> {
  const systemPrompt = `You are a content safety classifier. Given a user report, output JSON only:
{"score":0.0-1.0,"category":"csam|imminent_harm|hate_speech|harassment|spam|misinformation|copyright|other","reasoning":"one sentence"}`;

  const userPrompt = `Category: ${report.category}\nDescription: ${report.description}${
    report.contentSnippet ? `\nContent: ${report.contentSnippet.slice(0, 300)}` : ''}`;

  try {
    const response = await ai.run('@cf/meta/llama-3.1-8b-instruct', {
      messages: [
        { role: 'system', content: systemPrompt },
        { role: 'user', content: userPrompt },
      ],
      max_tokens: 150,
    }) as { response: string };

    const parsed = JSON.parse(response.response);
    return {
      aiScore: Number(parsed.score ?? 0.5),
      aiCategory: String(parsed.category ?? report.category),
      aiReasoning: String(parsed.reasoning ?? ''),
    };
  } catch {
    return {
      aiScore: categoryBaseScore(report.category),
      aiCategory: report.category,
      aiReasoning: 'AI classification unavailable; using category heuristic',
    };
  }
}

function categoryBaseScore(category: ReportCategory): number {
  const scores: Record<ReportCategory, number> = {
    csam: 1.0, imminent_harm: 0.95, hate_speech: 0.7, harassment: 0.65,
    misinformation: 0.5, spam: 0.3, copyright: 0.3, other: 0.25,
  };
  return scores[category] ?? 0.25;
}

function blendScore(p: {
  aiScore: number; accountRisk: number;
  reporterCredibility: number; userCategory: ReportCategory;
}): number {
  const base = p.aiScore * 0.5 + p.accountRisk * 0.3 + p.reporterCredibility * 0.2;
  if (p.userCategory === 'csam' || p.userCategory === 'imminent_harm') return Math.max(base, 0.9);
  return Math.min(1.0, base);
}

function scoreToPriority(score: number, category: ReportCategory): 'critical' | 'standard' | 'low' {
  if (category === 'csam' || category === 'imminent_harm') return 'critical';
  if (score >= 0.75) return 'critical';
  if (score >= 0.45) return 'standard';
  return 'low';
}
```

## Critical Queue Consumer

The critical consumer runs with minimal batching (batch size 1) to process reports with near-zero latency. It suppresses the flagged content immediately and fires an on-call webhook.

```typescript
// worker: consumer-critical.ts
export interface Env {
  DB: D1Database;
  MODERATION_WEBHOOK: string;
}

interface TriagedReport {
  reportId: string;
  contentId: string;
  aiCategory: string;
  finalScore: number;
}

export default {
  async queue(batch: MessageBatch<TriagedReport>, env: Env): Promise<void> {
    for (const message of batch.messages) {
      const r = message.body;

      await env.DB.batch([
        env.DB.prepare(
          `UPDATE content_reports SET status = 'pending_review' WHERE report_id = ?1`
        ).bind(r.reportId),
        env.DB.prepare(
          `UPDATE posts SET visibility = 'suppressed' WHERE post_id = ?1`
        ).bind(r.contentId),
      ]);

      // Fire-and-forget on-call alert — do not await, keep consumer fast
      fetch(env.MODERATION_WEBHOOK, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: `CRITICAL: ${r.aiCategory} — report ${r.reportId} (score ${r.finalScore.toFixed(2)})`,
        }),
      }).catch(() => {});

      message.ack();
    }
  },
};
```

## Standard and Low Queue Consumers

Standard and low consumers use larger batch sizes and update D1 in a single batch call for efficiency. They do not suppress content automatically — they add to the moderator review queue with lower urgency.

```typescript
// worker: consumer-standard.ts
export interface Env {
  DB: D1Database;
}

interface TriagedReport {
  reportId: string;
}

export default {
  async queue(batch: MessageBatch<TriagedReport>, env: Env): Promise<void> {
    const statements = batch.messages.map(msg =>
      env.DB.prepare(
        `UPDATE content_reports SET status = 'in_review_queue', updated_at = unixepoch()
         WHERE report_id = ?1`
      ).bind(msg.body.reportId)
    );

    if (statements.length > 0) {
      await env.DB.batch(statements);
    }

    for (const message of batch.messages) {
      message.ack();
    }
  },
};
```

## Reporter Credibility Feedback Loop

When a moderator resolves a report, the outcome updates the reporter's credibility score so future reports from that anonymous session token are weighted accordingly at triage time.

```typescript
// worker: credibility-updater.ts
export interface Env {
  DB: D1Database;
}

type ModerationAction = 'removed' | 'warned' | 'no_action' | 'false_report';

export async function updateReporterCredibility(
  env: Env,
  reportId: string,
  action: ModerationAction
): Promise<void> {
  const report = await env.DB.prepare(
    `SELECT reporter_id FROM content_reports WHERE report_id = ?1`
  ).bind(reportId).first<{ reporter_id: string }>();

  if (!report) return;

  const delta = action === 'false_report' ? -0.1 : action === 'no_action' ? 0 : 0.05;

  await env.DB.prepare(`
    INSERT INTO reporter_credibility (reporter_id, credibility_score, report_count, updated_at)
    VALUES (?1, MAX(0.1, MIN(1.0, 0.5 + ?2)), 1, unixepoch())
    ON CONFLICT(reporter_id) DO UPDATE SET
      credibility_score = MAX(0.1, MIN(1.0, credibility_score + ?2)),
      report_count      = report_count + 1,
      updated_at        = unixepoch()
  `).bind(report.reporter_id, delta).run();
}
```

## Anti-patterns

- Using a single Cloudflare Queue with a sort key hoping it acts as a priority queue — Queues does not support per-message priority or sorting within a queue; separate named queues per priority lane is the only correct approach
- Running AI classification inside the consumer Worker — by consumer execution time, content may be hours old; classify at ingestion in the Triage Worker while the event is fresh
- Hard-coding category-to-priority mapping without AI reclassification — users routinely select "spam" for content that is actually targeted harassment because it is the nearest available option; AI reclassification catches mislabeled reports
- Weighting reporter credibility too heavily before history accumulates — a new anonymous platform has no credibility history; use AI + account risk as the dominant signals and cap credibility weight at 20%
- Not persisting the report to D1 before enqueuing — if the queue consumer crashes and the message is lost before ack, there is no recovery path; write to D1 first, always

## Gotchas

- Cloudflare Queues does not guarantee exactly-once delivery; the D1 insert for content_reports must use `ON CONFLICT` or idempotency checks to handle double-delivery
- Workers AI LLM responses can fail JSON parsing even with explicit JSON-only instructions; always wrap `JSON.parse` in try/catch and fall back to the category heuristic
- `message.ack()` must be called for every message in the batch; unacknowledged messages are redelivered after the visibility timeout and generate duplicate moderation alerts
- The critical consumer must be configured with `max_retries = 0` and a dead-letter queue binding; retrying a failed critical consumer increases latency for the highest-severity cases — alert on DLQ depth instead of relying on retries
- `MAX(0.1, MIN(1.0, expr))` is the portable SQLite equivalent of `CLAMP`; D1 does not register a `CLAMP` function by default

## Verification

1. POST a synthetic report with `category: 'imminent_harm'` and a threat description to the Triage Worker.
2. Confirm the response body contains `priority: 'critical'` and a valid `reportId`.
3. Query D1 `content_reports` — expect `status = 'queued'`, `ai_score >= 0.8`, `priority = 'critical'`.
4. Consume one message from `REPORTS_CRITICAL` and confirm the post row in D1 has `visibility = 'suppressed'`.
5. POST five reports with `category: 'spam'` and no snippet — all should route to `REPORTS_LOW`.
6. Call `updateReporterCredibility` with `action: 'false_report'` five times for the same reporter; confirm `credibility_score` floors at 0.1.

## Related

- `anonymous-content-reporting-worker-pipeline.md`
- `emergency-content-takedown-circuit-breaker-queues.md`
- `real-time-toxic-content-scoring-workers-ai.md`
- `content-moderation-appeals-workflow.md`

## Sources

- Cloudflare Queues documentation: https://developers.cloudflare.com/queues/
- Workers AI model catalog: https://developers.cloudflare.com/workers-ai/models/
- DSA Article 16 notice-and-action mechanisms: https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32022R2065
