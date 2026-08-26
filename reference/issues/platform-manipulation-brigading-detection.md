# Platform Manipulation — Brigading and Coordinated Inauthentic Behavior Detection
- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

example project is an anonymous social platform, which makes it an attractive target for coordinated
manipulation campaigns: groups of users (or bots controlled by a group) simultaneously downvote,
report, or flood a specific post or user session in order to suppress it, get it auto-moderated,
or simply cause reputational damage ("brigading"). Because sessions are anonymous, there is no
social-graph layer to detect coordination through friendship links.

Observed patterns on anonymous platforms:

- **Vote flooding**: 50+ distinct sessions all react to the same post within 90 seconds of it
  being published — especially when the post was not surfaced by the recommendation algorithm
  to those sessions (implying out-of-band coordination, e.g., a Discord server link-sharing).
- **Report bombing**: A post receives ≥ 10 user-submitted reports within 120 seconds. The content
  moderation queue auto-holds the post, which is exactly what the brigade intends.
- **Reply flooding / thread burial**: Dozens of sessions each post short replies to the same thread
  within a burst window, burying the original post under noise.
- **Coordinated Solana tip-draining**: Multiple sessions rapidly send micropayments to a single
  wallet to drain its SOL for gas manipulation.

Without detection, a motivated off-platform group can suppress any content on example project within
minutes, defeating the platform's anonymous speech mission.

---

## Context

example project is built on Cloudflare Workers + D1 + R2. All interactions (reactions, reports, replies)
are individual Worker invocations that write event rows to D1. There is no persistent user account
to query; coordination detection must work purely from timing and content-ID clustering.

The core insight: in organic traffic, interactions with a post arrive at a rate proportional to
its distribution by the recommendation algorithm. If a post receives a burst of identical
interactions from sessions that were *not* shown the post by the algorithm, the out-of-band
coordination signal is strong regardless of whether the individual sessions are bots or humans.

Cloudflare Analytics Engine is used for real-time event aggregation without blowing D1's
row limits. Durable Objects are used for per-post coordination state machines.

---

## Section 1 — D1 Schema

```sql
-- post_interaction_log: every reaction / report / reply event
CREATE TABLE IF NOT EXISTS post_interaction_log (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  post_id         TEXT    NOT NULL,
  session_token   TEXT    NOT NULL,
  interaction_type TEXT   NOT NULL, -- react | report | reply | tip
  ip_subnet       TEXT    NOT NULL,
  cf_asn          INTEGER NOT NULL DEFAULT 0,
  algorithmic_referral INTEGER NOT NULL DEFAULT 0, -- 1 if session was served post by algo
  created_at      INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS pil_post_time
  ON post_interaction_log (post_id, created_at);
CREATE INDEX IF NOT EXISTS pil_session_time
  ON post_interaction_log (session_token, created_at);

-- coordination_flags: posts flagged for coordinated inauthentic behavior
CREATE TABLE IF NOT EXISTS coordination_flags (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  post_id         TEXT    NOT NULL,
  flag_type       TEXT    NOT NULL, -- vote_flood | report_bomb | reply_flood | tip_drain
  evidence_json   TEXT    NOT NULL, -- snapshot of detection signals
  action          TEXT    NOT NULL DEFAULT 'hold', -- hold | dismiss | escalate
  reviewed_by     TEXT,
  created_at      INTEGER NOT NULL DEFAULT (unixepoch()),
  resolved_at     INTEGER
);

CREATE UNIQUE INDEX IF NOT EXISTS cf_post_flag
  ON coordination_flags (post_id, flag_type)
  WHERE resolved_at IS NULL;
```

---

## Section 2 — Durable Object: Per-Post Coordination State Machine

Durable Objects provide strongly-consistent, low-latency state per post without a D1 write on
every interaction. The DO holds an in-memory sliding window; it writes to D1 only when a
threshold is crossed.

```typescript
// post-coordination-do.ts

interface Env {
  DB: D1Database;
  MODERATION_QUEUE: Queue;
}

interface InteractionEvent {
  sessionToken: string;
  interactionType: 'react' | 'report' | 'reply' | 'tip';
  ipSubnet: string;
  asn: number;
  algorithmicReferral: boolean;
  ts: number; // Unix ms
}

interface WindowState {
  reactions:  { ts: number; subnet: string; algorithmicReferral: boolean }[];
  reports:    { ts: number; subnet: string }[];
  replies:    { ts: number; subnet: string }[];
  tips:       { ts: number; amountSol: number }[];
  flagged:    Set<string>; // flag_type set to avoid duplicate D1 writes
}

export class PostCoordinationDO implements DurableObject {
  private state: DurableObjectState;
  private env: Env;
  private window: WindowState = {
    reactions: [], reports: [], replies: [], tips: [], flagged: new Set()
  };
  private postId: string = '';

  constructor(state: DurableObjectState, env: Env) {
    this.state = state;
    this.env = env;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    this.postId = url.searchParams.get('post_id') ?? 'unknown';

    if (request.method === 'POST') {
      const event = await request.json<InteractionEvent>();
      return this.handleInteraction(event);
    }
    return new Response('Method not allowed', { status: 405 });
  }

  private async handleInteraction(event: InteractionEvent): Promise<Response> {
    const now = event.ts;
    const WINDOW_90S = 90 * 1000;
    const WINDOW_120S = 120 * 1000;

    // Prune stale entries
    this.window.reactions = this.window.reactions.filter(e => now - e.ts < WINDOW_90S);
    this.window.reports   = this.window.reports.filter(e => now - e.ts < WINDOW_120S);
    this.window.replies   = this.window.replies.filter(e => now - e.ts < WINDOW_90S);
    this.window.tips      = this.window.tips.filter(e => now - e.ts < WINDOW_90S);

    // Add new event
    if (event.interactionType === 'react') {
      this.window.reactions.push({
        ts: now, subnet: event.ipSubnet, algorithmicReferral: event.algorithmicReferral
      });
    } else if (event.interactionType === 'report') {
      this.window.reports.push({ ts: now, subnet: event.ipSubnet });
    } else if (event.interactionType === 'reply') {
      this.window.replies.push({ ts: now, subnet: event.ipSubnet });
    }

    // Thresholds
    await this.checkVoteFlood();
    await this.checkReportBomb();
    await this.checkReplyFlood();

    return new Response(JSON.stringify({ ok: true }));
  }

  private async checkVoteFlood(): Promise<void> {
    if (this.window.flagged.has('vote_flood')) return;
    const nonAlgoReactions = this.window.reactions.filter(e => !e.algorithmicReferral);
    const uniqueSubnets = new Set(nonAlgoReactions.map(e => e.subnet)).size;
    if (nonAlgoReactions.length >= 40 && uniqueSubnets >= 20) {
      await this.raiseFlag('vote_flood', {
        count: nonAlgoReactions.length,
        unique_subnets: uniqueSubnets,
        window_ms: 90000,
      });
    }
  }

  private async checkReportBomb(): Promise<void> {
    if (this.window.flagged.has('report_bomb')) return;
    const uniqueSubnets = new Set(this.window.reports.map(e => e.subnet)).size;
    if (this.window.reports.length >= 10 && uniqueSubnets >= 5) {
      await this.raiseFlag('report_bomb', {
        count: this.window.reports.length,
        unique_subnets: uniqueSubnets,
        window_ms: 120000,
      });
    }
  }

  private async checkReplyFlood(): Promise<void> {
    if (this.window.flagged.has('reply_flood')) return;
    const uniqueSubnets = new Set(this.window.replies.map(e => e.subnet)).size;
    if (this.window.replies.length >= 30 && uniqueSubnets >= 15) {
      await this.raiseFlag('reply_flood', {
        count: this.window.replies.length,
        unique_subnets: uniqueSubnets,
        window_ms: 90000,
      });
    }
  }

  private async raiseFlag(flagType: string, evidence: Record<string, unknown>): Promise<void> {
    this.window.flagged.add(flagType);
    await Promise.all([
      this.env.DB.prepare(`
        INSERT OR IGNORE INTO coordination_flags (post_id, flag_type, evidence_json)
        VALUES (?, ?, ?)
      `).bind(this.postId, flagType, JSON.stringify(evidence)).run(),
      this.env.MODERATION_QUEUE.send({
        type: 'coordination_flag',
        post_id: this.postId,
        flag_type: flagType,
        evidence,
      }),
    ]);
  }
}
```

---

## Section 3 — Worker Middleware: Routing to Durable Object

```typescript
// interaction-router.ts

interface Env {
  DB: D1Database;
  POST_COORDINATION: DurableObjectNamespace;
  MODERATION_QUEUE: Queue;
}

export async function routeInteraction(
  request: Request,
  env: Env,
  ctx: ExecutionContext
): Promise<Response> {
  const body = await request.json<{
    post_id: string;
    session_token: string;
    interaction_type: 'react' | 'report' | 'reply' | 'tip';
    algorithmic_referral?: boolean;
  }>();

  const cf = request.cf as Record<string, unknown>;
  const rawIp = request.headers.get('CF-Connecting-IP') ?? '0.0.0.0';
  const subnet = rawIp.split('.').slice(0, 3).join('.');
  const asn = (cf.asn as number) ?? 0;

  // Write interaction to D1 for audit trail (fire-and-forget)
  ctx.waitUntil(
    env.DB.prepare(`
      INSERT INTO post_interaction_log
        (post_id, session_token, interaction_type, ip_subnet, cf_asn, algorithmic_referral)
      VALUES (?, ?, ?, ?, ?, ?)
    `).bind(
      body.post_id, body.session_token, body.interaction_type,
      subnet, asn, body.algorithmic_referral ? 1 : 0
    ).run()
  );

  // Route to per-post Durable Object (DO ID is derived from post_id for consistent routing)
  const doId = env.POST_COORDINATION.idFromName(body.post_id);
  const doStub = env.POST_COORDINATION.get(doId);

  const doResponse = await doStub.fetch(
    new Request(`https://do/interact?post_id=${body.post_id}`, {
      method: 'POST',
      body: JSON.stringify({
        sessionToken: body.session_token,
        interactionType: body.interaction_type,
        ipSubnet: subnet,
        asn,
        algorithmicReferral: body.algorithmic_referral ?? false,
        ts: Date.now(),
      }),
      headers: { 'Content-Type': 'application/json' },
    })
  );

  return doResponse;
}
```

---

## Section 4 — Moderation Queue Consumer: Handling Flags

```typescript
// queue-consumer-coordination.ts

interface FlagMessage {
  type: 'coordination_flag';
  post_id: string;
  flag_type: string;
  evidence: Record<string, unknown>;
}

export default {
  async queue(batch: MessageBatch<FlagMessage>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const { post_id, flag_type } = msg.body;

      // For report_bomb: immediately hold the post to prevent auto-moderation abuse
      if (flag_type === 'report_bomb') {
        await env.DB.prepare(`
          UPDATE posts SET status = 'held_coordination' WHERE post_id = ?
        `).bind(post_id).run();
        // Clear the report queue for this post — don't let report count drive auto-removal
        await env.DB.prepare(`
          UPDATE moderation_queue SET suppressed = 1
          WHERE post_id = ? AND suppressed = 0 AND report_type = 'user_report'
        `).bind(post_id).run();
      }

      // For vote_flood: freeze the vote count at current value
      if (flag_type === 'vote_flood') {
        await env.DB.prepare(`
          UPDATE posts SET vote_frozen = 1 WHERE post_id = ?
        `).bind(post_id).run();
      }

      msg.ack();
    }
  }
};
```

---

## Anti-patterns

- **Auto-removing content on report threshold alone**: This is exactly what a report-bombing attack
  exploits. Reports should only trigger a hold-for-review, not automatic removal. Coordinated report
  flags must *suppress* the report queue rather than amplify it.
- **Using only total interaction counts, not uniqueness**: 50 reactions from 3 subnets is less
  suspicious than 50 reactions from 50 subnets with no algorithmic referral. Always measure unique
  subnet count alongside raw count.
- **Storing DO state across restarts without Durable Object storage**: The in-memory `WindowState`
  above is evicted when the DO hibernates. For critical flag state, use `this.state.storage.put`.
  The current pattern is acceptable because the 90s window is shorter than typical DO hibernation
  latency.
- **Treating algorithmic-referral and non-referral interactions equally**: Organic engagement on a
  post the algorithm surfaced widely should not trigger coordination flags. Always tag each
  interaction with whether the user arrived via the recommendation pipeline.
- **Blocking all sessions involved in a coordinated action**: Human participants in a brigade are
  often themselves victims of social pressure (e.g., a moderator encouraging users in a community
  chat). Use content hold + human review rather than mass session bans.
- **Retaining interaction logs indefinitely**: Per GDPR data minimisation, `post_interaction_log`
  rows older than 30 days that are not linked to an open moderation case should be deleted.

---

## Gotchas

- Durable Objects are co-located with the first request that activates them (Cloudflare selects the
  pop). Subsequent requests to the same DO are routed globally, so cross-continent latency is
  possible on the first subrequest. For burst detection accuracy, the DO must be warmed by the
  first post-creation event, not the first interaction event.
- `DurableObjectNamespace.idFromName(post_id)` produces the same ID for the same string globally —
  no sharding, one DO per post. This is correct for this use-case but means DO hot spots are
  possible for viral posts. Monitor DO CPU limits (Worker CPU limit applies per DO invocation).
- Cloudflare Queues guarantee at-least-once delivery. The `INSERT OR IGNORE` in `raiseFlag` uses
  the `UNIQUE INDEX` on `(post_id, flag_type)` to make the moderation flag idempotent regardless
  of queue redelivery.
- `post_interaction_log` can grow very large for high-traffic posts. Partition the index by `(post_id,
  created_at)` (as shown) and run a scheduled cleanup that moves interactions older than 72h to
  a cold R2-backed Parquet log for analytics, then deletes from D1.
- The `algorithmic_referral` flag must be set server-side (the recommendation engine stamps the
  interaction token when it serves a post). Do not trust a client-supplied `algorithmic_referral`
  field — it is trivially spoofed by an attacker who wants to avoid triggering the non-referral
  coordination threshold.

---

## Verification

```bash
# 1. Simulate a report bomb (10 reports on same post in <120s)
POST_ID="test-post-001"
for i in $(seq 1 12); do
  curl -s -X POST https://example.com/api/interact \
    -H "Content-Type: application/json" \
    -H "CF-Connecting-IP: 10.$((RANDOM%255)).$((RANDOM%255)).1" \
    -d "{\"post_id\":\"$POST_ID\",\"session_token\":\"sess$i\",
         \"interaction_type\":\"report\",\"algorithmic_referral\":false}"
done

# 2. Verify coordination_flags created
wrangler d1 execute example project-prod --command \
  "SELECT post_id, flag_type, evidence_json, action FROM coordination_flags
   WHERE post_id = 'test-post-001';"

# 3. Verify post status was set to held_coordination
wrangler d1 execute example project-prod --command \
  "SELECT status, vote_frozen FROM posts WHERE post_id = 'test-post-001';"

# 4. Verify report queue suppressed
wrangler d1 execute example project-prod --command \
  "SELECT COUNT(*) FROM moderation_queue
   WHERE post_id = 'test-post-001' AND suppressed = 1;"

# 5. Check DO metrics via Cloudflare dashboard
# Cloudflare > Workers > Durable Objects > PostCoordinationDO > Metrics
# Look for: requests/sec spikes, storage read/write ratio, CPU time per request
```

---

## Related

- `anonymous-platform-abuse-prevention.md`
- `spam-post-detection-cloudflare-workers-ai.md`
- `botnet-registration-detection-turnstile-fingerprinting.md`
- `repeat-offender-detection-anonymous-sessions.md`
- `content-moderation-appeals-workflow.md`
- `hash-based-duplicate-content-detection-r2.md`
- `platform-trust-score-cloudflare-signals.md`
- `eu-dsa-recommender-2026.md`

---

## Sources

- EU DSA Article 16 (notice and action obligations for user reports) — https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32022R2065
- Meta Coordinated Inauthentic Behavior definition — https://transparency.fb.com/policies/community-standards/coordinated-inauthentic-behavior/
- Cloudflare Durable Objects documentation — https://developers.cloudflare.com/durable-objects/
- Cloudflare Queues at-least-once delivery guarantees — https://developers.cloudflare.com/queues/reference/delivery-guarantees/
- Cloudflare Analytics Engine for real-time aggregation — https://developers.cloudflare.com/analytics/analytics-engine/
- Stanford Internet Observatory — Brigading and coordinated harassment on anonymous platforms (2023) — https://cyber.fsi.stanford.edu/io
