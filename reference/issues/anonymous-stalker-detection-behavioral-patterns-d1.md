# Anonymous Stalker Detection via Behavioral Patterns — D1 + Workers

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

An anonymous example project user systematically visits the same target's profile, reacts to every post within seconds of publication, and sends unsolicited DMs at irregular hours — behaviour indistinguishable from a stalker even without a persistent identity. The platform must detect these temporal and structural patterns without storing PII, then intervene before the target feels unsafe.

## Context

On example project every action is tied to an ephemeral `session_id`, not a persistent account. D1 retains a 30-day sliding-window event log keyed by session. Workers aggregate visit frequency, reaction velocity, and DM cadence per (observer_session, target_session) pair each time a new action arrives. Durable Objects serialise the per-pair state to avoid D1 write contention under burst load.

## Detection — Behavioral Pattern Aggregation

```typescript
// workers/stalker-detector.ts
interface Env {
  DB: D1Database;
  STALKER_KV: KVNamespace;      // ephemeral per-pair counters (TTL 24 h)
  ALERT_QUEUE: Queue;
}

interface ActionEvent {
  observerSession: string;
  targetSession: string;
  actionType: "profile_view" | "reaction" | "dm" | "share" | "mention";
  contentId?: string;
  ts: number;                   // unix ms
}

interface PairStats {
  profileViews24h: number;
  reactions24h: number;
  dms24h: number;
  uniqueDays7d: number;
  avgIntervalMs: number;        // mean gap between actions
  nightActions: number;         // 00:00–05:00 local-ish UTC
}

const THRESHOLDS = {
  profileViews24h: 15,
  reactions24h: 30,
  dms24h: 10,
  nightActionsRatio: 0.6,       // >60 % of actions between midnight–5 am
  avgIntervalMaxMs: 5_000,      // reacting within 5 s of post means pre-refresh obsession
};

export async function recordAndScore(event: ActionEvent, env: Env): Promise<number> {
  const key = `pair:${event.observerSession}:${event.targetSession}`;

  // 1. Persist action to D1 for 30-day audit window
  await env.DB.prepare(
    `INSERT INTO stalker_events
       (observer_session, target_session, action_type, content_id, occurred_at)
     VALUES (?, ?, ?, ?, datetime(?, 'unixepoch'))`
  )
    .bind(
      event.observerSession,
      event.targetSession,
      event.actionType,
      event.contentId ?? null,
      Math.floor(event.ts / 1000)
    )
    .run();

  // 2. Pull 24-hour aggregate from D1
  const stats = await env.DB.prepare(
    `SELECT
       SUM(action_type = 'profile_view') AS profile_views,
       SUM(action_type = 'reaction')     AS reactions,
       SUM(action_type = 'dm')           AS dms,
       COUNT(DISTINCT date(occurred_at)) AS unique_days,
       AVG(
         CAST(strftime('%s', occurred_at) AS REAL) * 1000 -
         LAG(CAST(strftime('%s', occurred_at) AS REAL) * 1000)
           OVER (ORDER BY occurred_at)
       ) AS avg_interval_ms,
       SUM(CAST(strftime('%H', occurred_at) AS INTEGER) < 5) AS night_actions
     FROM stalker_events
     WHERE observer_session = ?
       AND target_session   = ?
       AND occurred_at > datetime('now', '-1 day')`
  )
    .bind(event.observerSession, event.targetSession)
    .first<{
      profile_views: number;
      reactions: number;
      dms: number;
      unique_days: number;
      avg_interval_ms: number | null;
      night_actions: number;
    }>();

  if (!stats) return 0;

  const total = (stats.profile_views ?? 0) + (stats.reactions ?? 0) + (stats.dms ?? 0);
  const nightRatio = total > 0 ? (stats.night_actions ?? 0) / total : 0;

  let score = 0;
  if ((stats.profile_views ?? 0) >= THRESHOLDS.profileViews24h) score += 0.25;
  if ((stats.reactions ?? 0) >= THRESHOLDS.reactions24h) score += 0.25;
  if ((stats.dms ?? 0) >= THRESHOLDS.dms24h) score += 0.25;
  if (nightRatio >= THRESHOLDS.nightActionsRatio) score += 0.15;
  if (stats.avg_interval_ms !== null && stats.avg_interval_ms <= THRESHOLDS.avgIntervalMaxMs) score += 0.10;

  // Cache score in KV for hot reads by the delivery gateway
  await env.STALKER_KV.put(key, JSON.stringify({ score, ts: Date.now() }), {
    expirationTtl: 60 * 60 * 24,
  });

  return score;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

    const event = await request.json<ActionEvent>();
    const score = await recordAndScore(event, env);

    if (score >= 0.75) {
      await env.ALERT_QUEUE.send({
        type: "STALKER_HIGH",
        observerSession: event.observerSession,
        targetSession: event.targetSession,
        score,
        ts: Date.now(),
      });
    } else if (score >= 0.5) {
      await env.ALERT_QUEUE.send({
        type: "STALKER_REVIEW",
        observerSession: event.observerSession,
        targetSession: event.targetSession,
        score,
        ts: Date.now(),
      });
    }

    return new Response(JSON.stringify({ score }), { status: 200 });
  },
};
```

## Response and Enforcement — Alert Queue Consumer

```typescript
// workers/stalker-responder.ts
interface AlertEvent {
  type: "STALKER_HIGH" | "STALKER_REVIEW";
  observerSession: string;
  targetSession: string;
  score: number;
  ts: number;
}

export default {
  async queue(batch: MessageBatch<AlertEvent>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const evt = msg.body;

      if (evt.type === "STALKER_HIGH") {
        // 1. Restrict observer from viewing/contacting target
        await env.DB.prepare(
          `INSERT OR REPLACE INTO interaction_blocks
             (observer_session, target_session, reason, blocked_at)
           VALUES (?, ?, 'stalking_pattern', CURRENT_TIMESTAMP)`
        ).bind(evt.observerSession, evt.targetSession).run();

        // 2. Elevate target's account to "stalking_victim" mode:
        //    DMs from unknown sessions are queued, not delivered live
        await env.DB.prepare(
          `UPDATE anonymous_sessions
             SET protection_mode = 'stalking_victim', protection_since = CURRENT_TIMESTAMP
           WHERE session_id = ?`
        ).bind(evt.targetSession).run();

        // 3. Write audit record
        await env.DB.prepare(
          `INSERT INTO stalker_interventions
             (observer_session, target_session, score, action, actioned_at)
           VALUES (?, ?, ?, 'block_and_protect', CURRENT_TIMESTAMP)`
        ).bind(evt.observerSession, evt.targetSession, evt.score).run();
      }

      if (evt.type === "STALKER_REVIEW") {
        // Flag for human moderation queue; no automated block yet
        await env.DB.prepare(
          `INSERT INTO moderation_queue
             (item_type, reference_id, reason, queued_at)
           VALUES ('session_pair', ?, 'possible_stalking', CURRENT_TIMESTAMP)`
        ).bind(`${evt.observerSession}:${evt.targetSession}`).run();
      }

      msg.ack();
    }
  },
};
```

## Audit and Compliance — Schema and Reporting

```sql
-- D1 migration: stalker detection tables
CREATE TABLE IF NOT EXISTS stalker_events (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  observer_session TEXT    NOT NULL,
  target_session   TEXT    NOT NULL,
  action_type      TEXT    NOT NULL,
  content_id       TEXT,
  occurred_at      TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_stalker_pair_time
  ON stalker_events(observer_session, target_session, occurred_at);

CREATE TABLE IF NOT EXISTS interaction_blocks (
  observer_session TEXT NOT NULL,
  target_session   TEXT NOT NULL,
  reason           TEXT NOT NULL,
  blocked_at       TEXT NOT NULL,
  PRIMARY KEY (observer_session, target_session)
);

CREATE TABLE IF NOT EXISTS stalker_interventions (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  observer_session TEXT NOT NULL,
  target_session   TEXT NOT NULL,
  score            REAL NOT NULL,
  action           TEXT NOT NULL,
  actioned_at      TEXT NOT NULL
);

-- Weekly compliance summary query
SELECT
  COUNT(*)                                          AS total_interventions,
  SUM(action = 'block_and_protect')                AS blocks,
  AVG(score)                                        AS avg_score,
  strftime('%Y-%W', actioned_at)                   AS week
FROM stalker_interventions
GROUP BY week
ORDER BY week DESC
LIMIT 12;
```

## Anti-patterns

- **Sharing target session IDs in alert payloads to external services** — anonymous victim IDs are still personal-context data; keep escalations internal.
- **Blocking the observer globally** on first high score — false positives occur (journalists tracking a story, fans of public figures); restrict only the specific pair interaction.
- **Relying solely on action count** without time-distribution analysis — binge-reading an old thread is not stalking; interval and night-ratio signals matter.
- **Storing raw event payloads with message bodies** — stalker_events should log action type and content ID only, never message text.
- **Forgetting to purge** stalker_events after the 30-day window — schedule a D1 delete job; stale rows inflate aggregate queries.

## Gotchas

- D1's `LAG()` window function works in SQLite 3.25+ — confirm Cloudflare's bundled SQLite version supports it before relying on it; fall back to application-side interval calculation if not.
- KV TTL resets on each `.put()` call, so the 24-hour window restarts with every action — intentional here, but document it.
- `protection_mode = 'stalking_victim'` must be checked by the DM delivery Worker; if it is not wired up, the protection flag has no effect.
- High-score pairs that self-resolve (observer stops) still hold an `interaction_blocks` row; add an expiry or manual review path so legitimate reconnection isn't blocked permanently.
- SQLite aggregate `SUM(action_type = 'profile_view')` uses implicit boolean-to-integer cast; test on the Cloudflare D1 engine specifically, not local SQLite.

## Verification

```bash
# Seed 20 profile-view events for pair (obs1, tgt1)
for i in $(seq 1 20); do
  curl -s -X POST https://example.com/internal/stalker-event \
    -H "Content-Type: application/json" \
    -d "{\"observerSession\":\"obs1\",\"targetSession\":\"tgt1\",
         \"actionType\":\"profile_view\",\"ts\":$(date +%s%3N)}"
done
# Final response should contain score >= 0.25

# Verify interaction_blocks row was created at score >= 0.75
wrangler d1 execute example project-db --command \
  "SELECT * FROM interaction_blocks WHERE observer_session='obs1';"

# Verify target protection mode
wrangler d1 execute example project-db --command \
  "SELECT protection_mode FROM anonymous_sessions WHERE session_id='tgt1';"

# Verify KV cache hit
wrangler kv:key get --namespace-id=<STALKER_NS> "pair:obs1:tgt1"
```

## Related

- `harassment-pattern-detection-durable-objects.md`
- `ban-evasion-device-fingerprint-detection-d1.md`
- `anonymous-content-reporting-worker-pipeline.md`
- `doxxing-pii-scan-prevention-workers-ai.md`

## Sources

- https://www.suicidepreventionlifeline.org/help-yourself/safety-planning/
- https://stopstalkerware.org/resources/
- https://www.stalkingawarenessmonth.org/
