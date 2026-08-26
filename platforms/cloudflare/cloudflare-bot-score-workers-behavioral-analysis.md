# Cloudflare Bot Score Workers Behavioral Analysis

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case
example project / example.com's anonymous social model attracts bot actors that inflate post view counts, farm reactions, and pollute the recommendation graph with synthetic signals. The WAF's managed bot rules block obvious scrapers but pass through low-score bots (score 30–70) that mimic real browser behavior. The platform needs a layered approach: read the raw CF bot score in a Worker, combine it with session-level behavioral signals stored in a Durable Object, and make a per-request routing decision without adding latency for genuine users.

## Context
Cloudflare Bot Management assigns every request a bot score (1–99, where 1 = definitely bot, 99 = definitely human) exposed on the `request.cf` object inside Workers as `cf.botManagement.score`. Enterprise Bot Management also provides `cf.botManagement.verifiedBot`, `cf.botManagement.staticResource`, and `cf.botManagement.ja3Hash`. Workers can read these fields synchronously — no external call needed — making them ideal for low-latency routing and per-session behavioral overlay.

## Reading Bot Score in a Worker

```typescript
// src/bot-gate.ts
export interface Env {
  SESSION_ANALYZER: DurableObjectNamespace;
  DB: D1Database;
}

interface BotManagement {
  score: number;
  verifiedBot: boolean;
  staticResource: boolean;
  ja3Hash?: string;
  detectionIds?: Record<string, unknown>;
}

function getBotScore(req: Request): BotManagement {
  const cf = req.cf as Record<string, unknown> | undefined;
  return {
    score: (cf?.botManagement as any)?.score ?? 99,
    verifiedBot: (cf?.botManagement as any)?.verifiedBot ?? false,
    staticResource: (cf?.botManagement as any)?.staticResource ?? false,
    ja3Hash: (cf?.botManagement as any)?.ja3Hash,
  };
}

export default {
  async fetch(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const bot = getBotScore(req);

    // Tier 1: Hard block — definitely bots
    if (bot.score <= 15 && !bot.verifiedBot) {
      return new Response("Forbidden", { status: 403 });
    }

    // Tier 2: Ambiguous — route to behavioral analysis
    if (bot.score <= 55 && !bot.verifiedBot) {
      return analyzeSessionBehavior(req, env, ctx, bot);
    }

    // Tier 3: Likely human — pass through with score header for downstream
    const resp = await fetch(req);
    return new Response(resp.body, {
      status: resp.status,
      headers: {
        ...Object.fromEntries(resp.headers),
        "X-Bot-Score": String(bot.score),
      },
    });
  },
};
```

## Session-Level Behavioral Analysis with Durable Objects

A Durable Object accumulates per-session signals (request rate, path diversity, timing variance) and emits a behavioral bot probability that overlays the CF bot score.

```typescript
// src/session-analyzer.ts
import { DurableObject } from "cloudflare:workers";

interface SessionState {
  requestCount: number;
  uniquePaths: string[];
  intervalMs: number[];
  lastTs: number;
  firstTs: number;
  flaggedAt?: number;
}

export class SessionAnalyzer extends DurableObject {
  private state: SessionState = {
    requestCount: 0,
    uniquePaths: [],
    intervalMs: [],
    lastTs: Date.now(),
    firstTs: Date.now(),
  };

  async record(path: string): Promise<number> {
    const now = Date.now();
    const interval = now - this.state.lastTs;

    this.state.requestCount++;
    this.state.intervalMs.push(interval);
    this.state.lastTs = now;

    if (!this.state.uniquePaths.includes(path)) {
      this.state.uniquePaths.push(path);
    }

    // Retain only last 50 intervals to bound memory
    if (this.state.intervalMs.length > 50) {
      this.state.intervalMs.shift();
    }

    await this.ctx.storage.put("state", this.state);
    return this.computeBotProbability();
  }

  private computeBotProbability(): number {
    const { requestCount, uniquePaths, intervalMs, firstTs } = this.state;
    if (requestCount < 5) return 0; // not enough signal

    const elapsedSec = (Date.now() - firstTs) / 1000;
    const rps = requestCount / Math.max(elapsedSec, 1);

    // High RPS: suspicious
    const rpsScore = Math.min(rps / 10, 1); // 10 req/s → probability 1.0

    // Low path diversity relative to request count: suspicious
    const diversityScore =
      1 - uniquePaths.length / Math.max(requestCount, 1);

    // Low timing variance: suspicious (bots are metronomic)
    const mean = intervalMs.reduce((a, b) => a + b, 0) / intervalMs.length;
    const variance =
      intervalMs.reduce((sum, v) => sum + (v - mean) ** 2, 0) /
      intervalMs.length;
    const stdDev = Math.sqrt(variance);
    const timingScore = stdDev < 50 ? 1 - stdDev / 50 : 0; // < 50ms stddev

    // Weighted composite
    return Math.min(rpsScore * 0.4 + diversityScore * 0.3 + timingScore * 0.3, 1);
  }

  async fetch(req: Request): Promise<Response> {
    const url = new URL(req.url);
    const path = url.searchParams.get("path") ?? "/";
    const prob = await this.record(path);
    return Response.json({ botProbability: prob });
  }
}
```

## Combining CF Bot Score with Behavioral Probability

```typescript
// src/bot-gate.ts — extended analyzeSessionBehavior
async function analyzeSessionBehavior(
  req: Request,
  env: Env,
  ctx: ExecutionContext,
  bot: BotManagement
): Promise<Response> {
  const sessionId = req.headers.get("CF-Ray")?.split("-")[0] ??
    crypto.randomUUID();

  const stub = env.SESSION_ANALYZER.get(
    env.SESSION_ANALYZER.idFromName(sessionId)
  );

  const url = new URL(req.url);
  const analysisResp = await stub.fetch(
    `https://internal/record?path=${encodeURIComponent(url.pathname)}`
  );
  const { botProbability } = await analysisResp.json<{
    botProbability: number;
  }>();

  // Normalize CF score to 0–1 probability (invert: low CF score = high bot prob)
  const cfBotProb = 1 - bot.score / 99;

  // Combined decision: weight CF score 60%, behavioral 40%
  const combinedProb = cfBotProb * 0.6 + botProbability * 0.4;

  if (combinedProb > 0.75) {
    // Log the event for model training without blocking the response
    ctx.waitUntil(
      env.DB.prepare(
        `INSERT INTO bot_detections (session_id, cf_score, behavioral_prob, combined_prob, path, ja3, detected_at)
         VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)`
      )
        .bind(
          sessionId,
          bot.score,
          botProbability,
          combinedProb,
          url.pathname,
          bot.ja3Hash ?? null
        )
        .run()
    );

    // Return a synthetic 200 (honeypot) instead of hard block to avoid detection
    return new Response(JSON.stringify({ ok: true }), {
      headers: { "Content-Type": "application/json" },
    });
  }

  // Allow through — pass request to origin
  return fetch(req);
}
```

## Routing and Telemetry Decisions

```typescript
// src/wrangler.toml additions for the DO namespace
// [[durable_objects.bindings]]
// name = "SESSION_ANALYZER"
// class_name = "SessionAnalyzer"
//
// [[migrations]]
// tag = "v1"
// new_classes = ["SessionAnalyzer"]

// Tail Worker for bot detection telemetry
export default {
  async tail(events: TraceItem[]): Promise<void> {
    for (const event of events) {
      for (const log of event.logs) {
        if (
          typeof log.message[0] === "string" &&
          log.message[0].startsWith("BOT_DETECTED")
        ) {
          // Forward to Analytics Engine or external SIEM
          console.log(JSON.stringify(log.message));
        }
      }
    }
  },
};
```

## Anti-patterns
- Reading `cf.botManagement.score` without a null check — the field is absent in local dev and on some plan tiers; default to `99` (human) to fail open
- Hard-blocking all requests with score < 30 without `verifiedBot` check — legitimate search engine crawlers (Googlebot, Bingbot) have low scores but set `verifiedBot: true`
- Storing full IP addresses in `bot_detections` for GDPR jurisdictions — store only the /24 prefix or a hashed representation
- Using `ja3Hash` as a sole bot signal — TLS fingerprints shift with browser updates and are spoofable; use it as one feature among many
- Running synchronous Durable Object calls on every request without a caching layer — add a KV cache with a 10-second TTL for the probability value once it stabilizes

## Gotchas
- `cf.botManagement` fields are only populated on Enterprise Bot Management plans; the free-tier `cf.bot_management` shape differs — test against the actual plan
- The `detectionIds` field is available on Enterprise and carries Cloudflare's internal model feature IDs; treat as opaque — do not base routing logic on specific IDs as they can change without notice
- Durable Object stubs created by `idFromName(sessionId)` based on `CF-Ray` prefixes partition sessions by PoP, not by user — a user switching PoPs mid-session gets a fresh state
- The behavioral model cold-starts for every new session; the first 5 requests are always passed through regardless of pattern
- Honeypot responses (fake 200) increase the risk of bot operators learning your detection logic over time — rotate the response shape periodically

## Verification
1. Deploy: `npx wrangler deploy`
2. Simulate a low bot score by using the Cloudflare Security dashboard's Test URL feature (Enterprise) or by using `wrangler dev` with `--test-scheduled`
3. Send rapid identical requests to a local dev tunnel: `for i in $(seq 50); do curl -s https://dev.example.com/; done`
4. Query D1 for detections: `SELECT * FROM bot_detections ORDER BY detected_at DESC LIMIT 10;`
5. Verify `verifiedBot` pass-through by checking Googlebot requests in your Zone's Security Events log

## Related
- `bot-fight-mode-free-vs-super.md`
- `bot-management-enterprise.md`
- `workers-bot-management-score-routing.md`
- `bot-fingerprinting-native-app-traffic-false-positives.md`
- `durable-objects-rate-limiter-pattern.md`

## Sources
- https://developers.cloudflare.com/bots/reference/bot-management-variables/
- https://developers.cloudflare.com/bots/concepts/bot-score/
- https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
- https://developers.cloudflare.com/durable-objects/
- https://developers.cloudflare.com/bots/get-started/bot-management-enterprise/
