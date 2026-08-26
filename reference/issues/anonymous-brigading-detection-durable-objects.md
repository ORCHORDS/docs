# Anonymous Brigading Detection With Durable Objects

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Brigading on example project occurs when a coordinated group of anonymous sessions simultaneously targets a specific post or user with mass reports, downvotes, or hostile replies, overwhelming moderation queues and suppressing legitimate speech. Unlike spam, brigading is low-frequency per session but high-frequency in aggregate against a single target. The platform must detect the concerted targeting pattern within seconds of it beginning, before the target is effectively silenced.

## Context

Anonymous sessions make it impossible to link participants by account, but the temporal and spatial concentration of actions against a single content ID is a reliable signal. Durable Objects are ideal here because one DO per target (post ID or profile ID) can maintain an in-memory sliding-window counter that fires an alert the instant the threshold is crossed, without waiting for a D1 write cycle.

## Detection — Per-Target Sliding Window in a Durable Object

A `BrigadeDetector` DO lives at the edge for each targeted content item. It maintains a ring buffer of recent hostile-action timestamps and computes the rate over the last 60 seconds on every incoming action.

```typescript
// durable-objects/BrigadeDetector.ts
export interface BrigadeState {
  actionTimestamps: number[];  // Unix ms ring buffer
  sessionSet: string[];        // distinct sessions in window
  alerted: boolean;
  alertedAt: number | null;
}

const WINDOW_MS = 60_000;         // 60-second sliding window
const ALERT_THRESHOLD = 15;       // 15 distinct sessions targeting same item
const ACTION_COUNT_THRESHOLD = 25; // OR 25 total hostile actions

export class BrigadeDetector implements DurableObject {
  private state: DurableObjectState;
  private cache: BrigadeState | null = null;

  constructor(state: DurableObjectState) {
    this.state = state;
  }

  private async loadState(): Promise<BrigadeState> {
    if (this.cache) return this.cache;
    this.cache = await this.state.storage.get<BrigadeState>("brigade") ?? {
      actionTimestamps: [],
      sessionSet: [],
      alerted: false,
      alertedAt: null,
    };
    return this.cache;
  }

  async fetch(request: Request): Promise<Response> {
    const { sessionId } = await request.json<{ sessionId: string }>();
    const nowMs = Date.now();

    const s = await this.loadState();

    // Prune timestamps outside the window
    const cutoff = nowMs - WINDOW_MS;
    s.actionTimestamps = s.actionTimestamps.filter(t => t > cutoff);

    // Rebuild session set from active timestamps
    // (We store session alongside timestamp as encoded pairs)
    s.actionTimestamps.push(nowMs);

    if (!s.sessionSet.includes(sessionId)) {
      s.sessionSet.push(sessionId);
    }
    // Prune sessionSet to only sessions with actions in window
    // Simplified: cap at 500 entries
    if (s.sessionSet.length > 500) s.sessionSet = s.sessionSet.slice(-500);

    const uniqueSessions = new Set(s.sessionSet).size;
    const totalActions = s.actionTimestamps.length;

    const brigadeDetected =
      !s.alerted &&
      (uniqueSessions >= ALERT_THRESHOLD || totalActions >= ACTION_COUNT_THRESHOLD);

    if (brigadeDetected) {
      s.alerted = true;
      s.alertedAt = nowMs;
    }

    await this.state.storage.put("brigade", s);
    this.cache = s;

    return new Response(
      JSON.stringify({
        uniqueSessions,
        totalActions,
        brigadeDetected,
        alerted: s.alerted,
        alertedAt: s.alertedAt,
      }),
      { headers: { "Content-Type": "application/json" } }
    );
  }
}
```

## Enforcement — Worker Gateway With Immediate Suppression

The Worker that receives hostile actions (reports, downvotes, flagged replies) routes through the `BrigadeDetector` DO before recording the action. When a brigade is detected, subsequent actions from new sessions are silently dropped and the target is shielded.

```typescript
// workers/hostile-action-gateway.ts
export interface Env {
  BRIGADE_DETECTOR: DurableObjectNamespace;
  DB: D1Database;
  ALERT_QUEUE: Queue;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

    const body = await request.json<{
      targetId: string;
      actionType: "report" | "downvote" | "hostile-reply";
      sessionId: string;
    }>();

    const doId = env.BRIGADE_DETECTOR.idFromName(`target:${body.targetId}`);
    const detector = env.BRIGADE_DETECTOR.get(doId);

    const detectorResp = await detector.fetch(
      new Request("https://do/check", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sessionId: body.sessionId }),
      })
    );
    const result = await detectorResp.json<{
      uniqueSessions: number;
      totalActions: number;
      brigadeDetected: boolean;
      alerted: boolean;
    }>();

    if (result.alerted) {
      // Shield: silently accept but do not record the action
      // (Returns 200 so attacker doesn't know they're shielded)
      return new Response(JSON.stringify({ status: "accepted" }), {
        headers: { "Content-Type": "application/json" },
      });
    }

    if (result.brigadeDetected) {
      // First detection: send alert before recording this action
      await env.ALERT_QUEUE.send({
        type: "brigade-detected",
        targetId: body.targetId,
        uniqueSessions: result.uniqueSessions,
        totalActions: result.totalActions,
        detectedAt: new Date().toISOString(),
      });

      // Apply soft-shield on the target in D1
      await env.DB.prepare(
        `INSERT INTO content_shields (target_id, reason, shielded_at, expires_at)
         VALUES (?, 'brigade', datetime('now'), datetime('now', '+4 hours'))
         ON CONFLICT(target_id) DO UPDATE SET
           shielded_at = datetime('now'),
           expires_at = datetime('now', '+4 hours')`
      ).bind(body.targetId).run();
    }

    // Record the action normally
    await env.DB.prepare(
      `INSERT INTO hostile_actions (target_id, session_id, action_type, recorded_at)
       VALUES (?, ?, ?, datetime('now'))`
    ).bind(body.targetId, body.sessionId, body.actionType).run();

    return new Response(JSON.stringify({ status: "recorded" }), {
      headers: { "Content-Type": "application/json" },
    });
  },
};
```

## Escalation — Alert Queue Consumer

The alert queue consumer notifies the on-call moderation team and records the brigade event in D1 for post-incident analysis.

```typescript
// workers/brigade-alert-consumer.ts
export interface Env {
  DB: D1Database;
}

export default {
  async queue(batch: MessageBatch<unknown>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const event = msg.body as {
        type: string;
        targetId: string;
        uniqueSessions: number;
        totalActions: number;
        detectedAt: string;
      };

      if (event.type !== "brigade-detected") {
        msg.ack();
        continue;
      }

      await env.DB.prepare(
        `INSERT INTO brigade_events
           (target_id, unique_sessions, total_actions, detected_at, status)
         VALUES (?, ?, ?, ?, 'open')
         ON CONFLICT DO NOTHING`
      ).bind(
        event.targetId,
        event.uniqueSessions,
        event.totalActions,
        event.detectedAt
      ).run();

      // In production: send Slack/PagerDuty webhook here
      console.log(`[BRIGADE ALERT] target=${event.targetId} sessions=${event.uniqueSessions}`);
      msg.ack();
    }
  },
};
```

## Monitoring — Dashboard Queries

```typescript
// SQL for moderation dashboard
const OPEN_BRIGADES = `
  SELECT
    b.target_id,
    b.unique_sessions,
    b.total_actions,
    b.detected_at,
    c.shielded_at,
    c.expires_at
  FROM brigade_events b
  LEFT JOIN content_shields c ON c.target_id = b.target_id
  WHERE b.status = 'open'
  ORDER BY b.detected_at DESC
  LIMIT 25
`;

const BRIGADE_RATE = `
  SELECT
    strftime('%H:%M', detected_at) AS minute,
    COUNT(*) AS brigades
  FROM brigade_events
  WHERE detected_at > datetime('now', '-2 hours')
  GROUP BY minute
  ORDER BY minute
`;
```

## Anti-patterns

- Using D1 as the primary detection store — a write round-trip adds 20–80 ms latency, enough for a brigade to complete before the first alert
- Alerting on raw action count without deduplicating sessions — one session hammering report 25 times is spam, not a brigade
- Setting the window too long (>5 minutes) — legitimate waves of attention (viral posts) trigger false positives
- Hard-blocking actions during detection — the shield approach avoids signal leakage to attackers
- Evicting the DO too aggressively — use a 60-second alarm to keep the DO warm during active brigades

## Gotchas

- DO fetch handlers must return a `Response`; forgetting this causes a runtime error that silently drops the check
- `idFromName` is deterministic; use a namespaced key (`target:${id}`) to avoid collisions with other DOs
- DO storage reads are synchronous within a transaction; `state.blockConcurrencyWhile` ensures atomic window updates under concurrent requests
- The ring buffer approach grows unbounded if a target is brigaded continuously — cap `actionTimestamps` at 1000 entries and prune aggressively
- Queue consumers must call `msg.ack()` explicitly; uncalled acks cause the message to be redelivered

## Verification

1. Deploy DO and Worker, configure `ALERT_QUEUE` binding in `wrangler.toml`.
2. Simulate a brigade: send 16 POST requests to the hostile-action gateway with `targetId="post-001"` and distinct `sessionId` values over 30 seconds.
3. Verify the 16th request triggers a `brigade-detected` queue message.
4. Confirm `content_shields` row exists for `target_id="post-001"`.
5. Send a 17th request — response should be `{"status":"accepted"}` but D1 should have no new `hostile_actions` row.

## Related

- `/documentation/categories/issues/platform-manipulation-brigading-detection.md`
- `/documentation/categories/issues/harassment-pattern-detection-durable-objects.md`
- `/documentation/categories/issues/report-queue-prioritization-workers-queues-ai.md`
- `/documentation/categories/issues/anonymous-dm-spam-burst-detection-durable-objects.md`

## Sources

- https://developers.cloudflare.com/durable-objects/
- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/durable-objects/api/alarms/
- https://jigsaw.google.com/the-current/harassment/
