# Coordinated Mass-Reporting Abuse via Durable Objects

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Adversarial users on example project orchestrate mass-report campaigns to silence legitimate voices.
A single post receives dozens of reports within seconds from accounts that share no observable
interaction history, bypassing per-user rate limits because each reporter individually looks
clean. The effect: an innocent post is auto-suppressed by the platform's own moderation
pipeline before any human reviewer sees it.

---

## Context

Cloudflare's report-intake Worker processes each flag independently and applies per-session
rate limits via KV. Because KV reads are eventually consistent and Durable Objects are strongly
consistent per-key, switching report *aggregation* to a Durable Object lets you detect the
coordinated pattern in real time — before the downstream suppression decision fires. The DO
holds a sliding-window counter keyed by `(contentId, epochMinute)` and gates the auto-suppress
action whenever the velocity and reporter-diversity thresholds both breach simultaneously.

---

## 1. Report Intake Worker

```typescript
// workers/report-intake.ts
import { ReportAggregatorDO } from './report-aggregator-do';

export interface Env {
  REPORT_AGGREGATOR: DurableObjectNamespace;
  MODERATION_QUEUE: Queue<ReportEvent>;
}

export interface ReportEvent {
  contentId: string;
  reporterId: string;   // hashed session token — never raw PII
  reason: string;
  ts: number;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    if (req.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });

    const body = await req.json<ReportEvent>();
    const { contentId, reporterId, reason } = body;

    if (!contentId || !reporterId || !reason) {
      return new Response(JSON.stringify({ error: 'missing_fields' }), { status: 400 });
    }

    // Each content item owns exactly one DO instance
    const id = env.REPORT_AGGREGATOR.idFromName(contentId);
    const stub = env.REPORT_AGGREGATOR.get(id);

    const verdict = await stub.recordReport({ contentId, reporterId, reason, ts: Date.now() });

    // Always enqueue for async human review regardless of verdict
    await env.MODERATION_QUEUE.send({ contentId, reporterId, reason, ts: Date.now() });

    return new Response(JSON.stringify(verdict), { status: 200 });
  },
};
```

---

## 2. ReportAggregator Durable Object

```typescript
// workers/report-aggregator-do.ts
export interface ReportEvent {
  contentId: string;
  reporterId: string;
  reason: string;
  ts: number;
}

export interface Verdict {
  suppressed: boolean;
  reason: string;
  reportCount: number;
  uniqueReporters: number;
}

const WINDOW_MS = 5 * 60 * 1000;         // 5-minute sliding window
const VOLUME_THRESHOLD = 20;              // absolute count to flag
const DIVERSITY_THRESHOLD = 15;           // unique reporters within window
const VELOCITY_THRESHOLD_PER_SEC = 2.5;  // reports/second in burst

export class ReportAggregatorDO {
  private state: DurableObjectState;

  constructor(state: DurableObjectState) {
    this.state = state;
  }

  async fetch(req: Request): Promise<Response> {
    const body = await req.json<ReportEvent>();
    const verdict = await this.recordReport(body);
    return new Response(JSON.stringify(verdict), {
      headers: { 'Content-Type': 'application/json' },
    });
  }

  async recordReport(event: ReportEvent): Promise<Verdict> {
    const now = event.ts;
    const cutoff = now - WINDOW_MS;

    // Read existing window data (strongly consistent)
    const raw = await this.state.storage.get<string>('window');
    const window: Array<{ reporterId: string; ts: number }> = raw
      ? JSON.parse(raw)
      : [];

    // Evict expired entries
    const active = window.filter((e) => e.ts >= cutoff);

    // Deduplicate: one report per (reporterId, window)
    const alreadyReported = active.some((e) => e.reporterId === event.reporterId);
    if (!alreadyReported) {
      active.push({ reporterId: event.reporterId, ts: now });
    }

    await this.state.storage.put('window', JSON.stringify(active));

    const uniqueReporters = new Set(active.map((e) => e.reporterId)).size;
    const reportCount = active.length;

    // Velocity: reports in last 10 seconds
    const burstWindow = active.filter((e) => e.ts >= now - 10_000);
    const velocity = burstWindow.length / 10;

    const isCoordinated =
      reportCount >= VOLUME_THRESHOLD &&
      uniqueReporters >= DIVERSITY_THRESHOLD &&
      velocity >= VELOCITY_THRESHOLD_PER_SEC;

    if (isCoordinated) {
      // Record suppression decision with timestamp for audit
      await this.state.storage.put('suppressed_at', now.toString());
    }

    return {
      suppressed: isCoordinated,
      reason: isCoordinated ? 'coordinated_mass_report' : 'ok',
      reportCount,
      uniqueReporters,
    };
  }
}
```

---

## 3. Downstream Suppression Consumer

```typescript
// workers/moderation-consumer.ts
import { Env } from './report-intake';

interface QueueMessage {
  body: import('./report-intake').ReportEvent;
}

export default {
  async queue(batch: MessageBatch<import('./report-intake').ReportEvent>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const { contentId } = msg.body;

      const id = env.REPORT_AGGREGATOR.idFromName(contentId);
      const stub = env.REPORT_AGGREGATOR.get(id);

      // Re-check verdict before acting — avoids race between enqueue and DO write
      const verdictRes = await stub.fetch(
        new Request('https://internal/verdict', {
          method: 'POST',
          body: JSON.stringify(msg.body),
        })
      );
      const verdict = await verdictRes.json<import('./report-aggregator-do').Verdict>();

      if (verdict.suppressed) {
        // Write shadow-ban flag; content is hidden but not deleted pending human review
        await fetch(`https://api.internal/content/${contentId}/suppress`, {
          method: 'PATCH',
          body: JSON.stringify({ reason: verdict.reason }),
        });
      }

      msg.ack();
    }
  },
};
```

---

## 4. Decay & Reset Schedule

Reports should not stack indefinitely. A Durable Object alarm prunes storage and lifts
auto-suppression after a configurable cooling-off period.

```typescript
// Inside ReportAggregatorDO
async alarm(): Promise<void> {
  const suppressedAt = await this.state.storage.get<string>('suppressed_at');
  if (!suppressedAt) return;

  const age = Date.now() - parseInt(suppressedAt, 10);
  const LIFT_AFTER_MS = 24 * 60 * 60 * 1000; // 24 hours

  if (age >= LIFT_AFTER_MS) {
    // Clear suppression if no human reviewer has made a final call
    const humanDecision = await this.state.storage.get<string>('human_decision');
    if (!humanDecision) {
      await this.state.storage.delete('suppressed_at');
      await fetch(`https://api.internal/content/${await this.state.storage.get('contentId')}/unsuppress`, {
        method: 'PATCH',
      });
    }
    await this.state.storage.deleteAll();
  } else {
    // Re-arm alarm for remaining cooling period
    this.state.storage.setAlarm(Date.now() + (LIFT_AFTER_MS - age));
  }
}
```

---

## 5. wrangler.toml Binding

```toml
[[durable_objects.bindings]]
name = "REPORT_AGGREGATOR"
class_name = "ReportAggregatorDO"

[[migrations]]
tag = "v1"
new_classes = ["ReportAggregatorDO"]

[[queues.consumers]]
queue = "moderation-queue"
max_batch_size = 50
max_batch_timeout = 5
```

---

## Anti-patterns

- **Per-session KV rate limiting only**: Each KV check is independent; a coordinated group of
  20 accounts each filing one report individually defeats per-user limits entirely.
- **Trusting report velocity alone**: A sudden burst could be organic (a viral post that
  violates rules). Combine velocity with reporter-diversity entropy.
- **Deleting content on auto-suppress**: Suppression hides the post without data loss.
  A human reviewer needs the original to make a final call.
- **Skipping the queue**: Processing suppression synchronously in the report-intake Worker
  blocks the response and extends latency for every reporter.

---

## Gotchas

- **DO serialization**: The `fetch` handler on a DO processes one request at a time per
  instance. High report bursts queue up naturally, but very large batches (>500 concurrent)
  can cause the Worker that opens the stub to time out waiting for the DO. Use the Queue
  consumer to absorb volume.
- **contentId as DO name**: Using the raw content ID is fine for lookup but ensure the ID
  space is collision-resistant (UUIDv4, KSUID). Sequential integers leak enumeration vectors.
- **Storage size**: A single JSON array stored per DO is fine up to tens of thousands of
  entries. For extremely viral content with millions of reports, store only the reporter hash
  in a bloom-filter approximation rather than the full list.
- **Alarm persistence**: If the Worker process is evicted before `setAlarm` completes, the
  alarm is not set. Call `setAlarm` inside a `blockConcurrencyWhile` wrapper to guarantee it.

---

## Verification

```typescript
// vitest integration test (uses miniflare)
import { describe, it, expect, beforeEach } from 'vitest';
import { ReportAggregatorDO } from '../workers/report-aggregator-do';

describe('ReportAggregatorDO', () => {
  it('does not suppress below threshold', async () => {
    const do_ = new ReportAggregatorDO(mockState());
    for (let i = 0; i < 10; i++) {
      await do_.recordReport({ contentId: 'c1', reporterId: `u${i}`, reason: 'spam', ts: Date.now() });
    }
    const v = await do_.recordReport({ contentId: 'c1', reporterId: 'u99', reason: 'spam', ts: Date.now() });
    expect(v.suppressed).toBe(false);
  });

  it('suppresses on coordinated burst', async () => {
    const do_ = new ReportAggregatorDO(mockState());
    const now = Date.now();
    for (let i = 0; i < 25; i++) {
      await do_.recordReport({ contentId: 'c2', reporterId: `u${i}`, reason: 'hate', ts: now + i * 200 });
    }
    const v = await do_.recordReport({ contentId: 'c2', reporterId: 'u99', reason: 'hate', ts: now + 5000 });
    expect(v.suppressed).toBe(true);
    expect(v.reason).toBe('coordinated_mass_report');
  });
});
```

---

## Related

- `anonymous-brigading-detection-durable-objects.md`
- `coordinated-inauthentic-behavior-detection-d1.md`
- `report-queue-prioritization-workers-queues-ai.md`
- `shadow-banning-reach-limiting-d1-workers.md`
- `emergency-content-takedown-circuit-breaker-queues.md`

---

## Sources

- Cloudflare Durable Objects — Storage API: https://developers.cloudflare.com/durable-objects/api/storage-api/
- Cloudflare Queues — Consumer Workers: https://developers.cloudflare.com/queues/reference/consumer-workers/
- "Coordinated Inauthentic Behavior" — Meta Threat Intelligence, 2023
- Trust & Safety Engineering at Scale — TSPA Annual Summit, 2024
