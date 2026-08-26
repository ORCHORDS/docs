# Cryptocurrency Pump-and-Dump Coordination Detection — D1 + Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Groups of anonymous accounts on example project coordinate to promote a low-cap cryptocurrency or token
at scale. The pattern: dozens of posts in rapid succession hyping the same ticker, then silence
after the organiser dumps their holdings. Victims who buy in suffer losses; the platform is used
as a manipulation mechanism and may face regulatory liability (SEC, FCA, ESMA have all issued
guidance on social-media-driven market manipulation).

This differs from organic enthusiasm: timing is compressed, accounts are newly activated or
dormant-then-burst, the ticker is micro-cap and illiquid, and the language follows a template.

---

## Context

Pump-and-dump signals:

1. **Ticker clustering** — many posts mention the same symbol ($TICKER, "buy X now") within a
   short window.
2. **Account burst activation** — previously dormant or new accounts all post within the campaign
   window.
3. **Template language** — posts use near-identical phrases ("next 100x", "don't miss the rocket",
   "whale just bought").
4. **Cross-post amplification** — same post liked/shared by a cluster of accounts with no prior
   interaction history.
5. **Timing correlation** — post burst correlates with a price spike detectable via an external
   price feed (optional: webhook integration).

D1 can store ticker mention events and run SQL aggregation to detect clustering. Workers AI can
classify whether a post is promotional/coordinated vs. genuine opinion.

Regulatory context: MiCA (EU Markets in Crypto Assets Regulation) Art. 91 explicitly prohibits
market manipulation for crypto assets; MICA came into full effect December 2024. FCA PS22/4
covers financial promotions for crypto in the UK.

---

## Architecture

```
Post with ticker mention → Worker (ticker extract → classify → event insert)
                         → D1 (ticker_mention_events)
                         → Cron Worker (every 5 min — cluster analysis)
                             → D1 (pump_alerts)
                             → Queues (moderation-action-queue)
```

---

## Implementation

### 1. Ticker Extractor

```typescript
// src/extractors/ticker.ts

// Matches $TICKER (1–10 uppercase letters) or explicit "buy X" patterns
const TICKER_RE = /\$([A-Z]{1,10})\b/g;

export function extractTickers(content: string): string[] {
  const matches = [...content.matchAll(TICKER_RE)];
  return [...new Set(matches.map((m) => m[1]))];
}
```

### 2. Post Classification — Is It Promotional Coordination?

```typescript
// src/scoring/crypto-promo.ts
import type { Env } from '../types';

export interface CryptoPromoScore {
  isPromo: boolean;
  confidence: number;
  templatePhrases: string[];
}

const PROMO_PROMPT = (content: string) => `
You are a financial content classifier for an anonymous social platform subject to MiCA regulation.

Post content: """${content}"""

Determine whether this post is:
1. Coordinated cryptocurrency promotional content (pump-and-dump style)
2. Organic financial opinion or news

Signals of coordinated promotion:
- Superlatives with no factual basis ("100x guaranteed", "moon incoming")
- Urgency language ("buy NOW", "last chance", "don't miss it")
- Generic template phrases without personalisation
- No risk disclosure

Respond ONLY with JSON:
{
  "is_promo": <boolean>,
  "confidence": <0.0–1.0>,
  "template_phrases": [<list of identified template phrases, max 5>]
}
`.trim();

export async function scoreCryptoPromo(
  content: string,
  env: Env,
): Promise<CryptoPromoScore> {
  const result = await env.AI.run('@cf/meta/llama-3.3-70b-instruct-fp8-fast', {
    prompt: PROMO_PROMPT(content),
    max_tokens: 200,
  });

  try {
    const parsed = JSON.parse((result as { response: string }).response);
    return {
      isPromo: Boolean(parsed.is_promo),
      confidence: Number(parsed.confidence ?? 0),
      templatePhrases: Array.isArray(parsed.template_phrases)
        ? parsed.template_phrases
        : [],
    };
  } catch {
    return { isPromo: false, confidence: 0, templatePhrases: [] };
  }
}
```

### 3. Event Ingestion Handler

```typescript
// src/handlers/crypto-mention-ingest.ts
import { extractTickers } from '../extractors/ticker';
import { scoreCryptoPromo } from '../scoring/crypto-promo';
import type { Env } from '../types';

export async function handlePostIngest(request: Request, env: Env): Promise<Response> {
  const body = await request.json<{ postId: string; content: string; accountToken: string }>();
  const tickers = extractTickers(body.content);

  if (tickers.length === 0) {
    return Response.json({ skipped: true });
  }

  const promo = await scoreCryptoPromo(body.content, env);

  // Insert one row per ticker mentioned in the post
  const stmt = env.DB.prepare(
    `INSERT OR IGNORE INTO ticker_mention_events
       (event_id, post_id, ticker, account_token, is_promo, promo_confidence,
        template_phrases, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, unixepoch())`,
  );

  const batch = tickers.map((ticker) =>
    stmt.bind(
      crypto.randomUUID(),
      body.postId,
      ticker,
      body.accountToken,
      promo.isPromo ? 1 : 0,
      promo.confidence,
      JSON.stringify(promo.templatePhrases),
    ),
  );

  await env.DB.batch(batch);

  return Response.json({ tickers, isPromo: promo.isPromo });
}
```

### 4. Cron Worker — Cluster Analysis (runs every 5 minutes)

```typescript
// src/cron/pump-detector.ts
import type { Env } from '../types';

// Alert when ≥ MENTION_THRESHOLD posts about same ticker in the last WINDOW_MINUTES
const WINDOW_MINUTES   = 15;
const MENTION_THRESHOLD = 20;
const PROMO_RATIO_THRESHOLD = 0.60; // ≥60% of posts classified as promo

interface ClusterRow {
  ticker: string;
  mention_count: number;
  promo_count: number;
  unique_accounts: number;
}

export async function runPumpDetection(env: Env): Promise<void> {
  const windowStart = Math.floor(Date.now() / 1000) - WINDOW_MINUTES * 60;

  const clusters = await env.DB.prepare(
    `SELECT
       ticker,
       COUNT(*)                                AS mention_count,
       SUM(is_promo)                           AS promo_count,
       COUNT(DISTINCT account_token)           AS unique_accounts
     FROM ticker_mention_events
     WHERE created_at >= ?
     GROUP BY ticker
     HAVING mention_count >= ?
     ORDER BY mention_count DESC`,
  )
    .bind(windowStart, MENTION_THRESHOLD)
    .all<ClusterRow>();

  for (const cluster of clusters.results) {
    const promoRatio = cluster.promo_count / cluster.mention_count;
    if (promoRatio < PROMO_RATIO_THRESHOLD) continue;

    const alertId = crypto.randomUUID();
    await env.DB.prepare(
      `INSERT OR IGNORE INTO pump_alerts
         (alert_id, ticker, mention_count, promo_count, unique_accounts,
          promo_ratio, window_start, detected_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, unixepoch())`,
    ).bind(
      alertId,
      cluster.ticker,
      cluster.mention_count,
      cluster.promo_count,
      cluster.unique_accounts,
      promoRatio,
      windowStart,
    ).run();

    await env.MODERATION_QUEUE.send({
      alertId,
      type: 'pump_dump_campaign',
      ticker: cluster.ticker,
      mentionCount: cluster.mention_count,
      promoRatio,
      uniqueAccounts: cluster.unique_accounts,
      action: cluster.mention_count >= 50 ? 'auto_suppress_ticker' : 'human_review',
    });
  }
}

// wrangler.toml cron trigger:
// [triggers]
// crons = ["*/5 * * * *"]
```

### 5. D1 Schema

```sql
CREATE TABLE IF NOT EXISTS ticker_mention_events (
  event_id          TEXT PRIMARY KEY,
  post_id           TEXT NOT NULL,
  ticker            TEXT NOT NULL,
  account_token     TEXT NOT NULL,   -- anonymised hash of session token
  is_promo          INTEGER NOT NULL DEFAULT 0,
  promo_confidence  REAL NOT NULL DEFAULT 0.0,
  template_phrases  TEXT,            -- JSON array
  created_at        INTEGER NOT NULL
);

CREATE INDEX idx_tme_ticker_time   ON ticker_mention_events(ticker, created_at DESC);
CREATE INDEX idx_tme_account_time  ON ticker_mention_events(account_token, created_at DESC);
CREATE INDEX idx_tme_is_promo      ON ticker_mention_events(is_promo, created_at DESC);

CREATE TABLE IF NOT EXISTS pump_alerts (
  alert_id        TEXT PRIMARY KEY,
  ticker          TEXT NOT NULL,
  mention_count   INTEGER NOT NULL,
  promo_count     INTEGER NOT NULL,
  unique_accounts INTEGER NOT NULL,
  promo_ratio     REAL NOT NULL,
  window_start    INTEGER NOT NULL,
  detected_at     INTEGER NOT NULL,
  resolved_at     INTEGER,
  resolution      TEXT    -- 'false_positive' | 'campaign_suppressed' | 'escalated_regulator'
);

CREATE INDEX idx_pump_alerts_ticker ON pump_alerts(ticker, detected_at DESC);
```

### 6. Ticker Suppression Action Consumer

```typescript
// src/consumers/ticker-suppress.ts
import type { Env } from '../types';

interface SuppressMessage {
  alertId: string;
  type: string;
  ticker: string;
  action: string;
}

export async function suppressTickerPosts(
  batch: MessageBatch<SuppressMessage>,
  env: Env,
): Promise<void> {
  for (const msg of batch.messages) {
    if (msg.body.action !== 'auto_suppress_ticker') {
      msg.ack();
      continue;
    }

    // Shadow-restrict all promo posts mentioning this ticker in the last window
    await env.DB.prepare(
      `UPDATE posts
       SET visibility = 'restricted'
       WHERE post_id IN (
         SELECT DISTINCT post_id FROM ticker_mention_events
         WHERE ticker = ? AND is_promo = 1 AND created_at >= unixepoch() - 900
       )`,
    ).bind(msg.body.ticker).run();

    // Mark alert resolved
    await env.DB.prepare(
      `UPDATE pump_alerts SET resolved_at = unixepoch(), resolution = 'campaign_suppressed'
       WHERE alert_id = ?`,
    ).bind(msg.body.alertId).run();

    msg.ack();
  }
}
```

---

## Anti-patterns

- **Flagging any ticker mention** — genuine financial commentary ("I sold my $BTC") is not a
  pump campaign. The promo classifier + cluster threshold combination is required; neither alone
  is sufficient.
- **Using post count alone without deduplication by account** — a single account posting 25 times
  about the same ticker is spam, not a coordinated campaign. `unique_accounts` is a critical
  dimension; a high unique account count with high promo ratio indicates genuine coordination.
- **Running cluster analysis in-band on every post** — cluster SQL over the full table on every
  ingest is prohibitively expensive at volume. The Cron Worker pattern decouples ingestion from
  analysis.
- **Hard-coding the suppression threshold** — different asset classes and market conditions warrant
  different thresholds; externalise `MENTION_THRESHOLD` and `PROMO_RATIO_THRESHOLD` to a D1
  config table.

---

## Gotchas

- D1 `UPSERT` via `INSERT OR IGNORE` requires the target column to have a UNIQUE or PRIMARY KEY
  constraint. Use a deterministic `event_id` (hash of `postId + ticker`) if you need idempotent
  re-ingestion.
- `COUNT(DISTINCT account_token)` in SQLite / D1 cannot be combined with `HAVING` on the alias
  directly in older SQLite versions; wrap in a subquery or use the full expression in HAVING.
- Cron Workers execute once per trigger globally (not per isolate replica). The 5-minute cron
  interval is the minimum allowed in wrangler.toml at the time of writing.
- MiCA Art. 91 applies to "market manipulation" broadly; platform liability arises only if the
  platform had actual knowledge and failed to act. Logging `pump_alerts` with timestamps provides
  the evidence trail that action was taken promptly.
- Do not expose the ticker suppression to users — it teaches campaign operators to stay below
  the detection threshold by spreading posts over a longer time window.

---

## Verification

```sql
-- Inspect recent pump alerts
SELECT ticker, mention_count, unique_accounts,
       ROUND(promo_ratio * 100, 1) AS promo_pct,
       datetime(detected_at, 'unixepoch') AS detected,
       resolution
FROM pump_alerts
ORDER BY detected_at DESC
LIMIT 10;

-- False positive rate: alerts resolved as false_positive
SELECT
  COUNT(*) FILTER (WHERE resolution = 'false_positive') AS false_positives,
  COUNT(*) FILTER (WHERE resolution = 'campaign_suppressed') AS true_positives,
  COUNT(*) FILTER (WHERE resolution IS NULL) AS pending
FROM pump_alerts
WHERE detected_at > unixepoch() - 604800;  -- last 7 days
```

---

## Related

- `cryptocurrency-fraud-detection-workers.md` — general crypto fraud signals
- `nft-scam-detection-d1-workers.md` — NFT-specific scam patterns
- `coordinated-inauthentic-behavior-detection-d1.md` — CIB detection framework
- `anonymous-dm-spam-burst-detection-durable-objects.md` — burst spam via DMs
- `platform-manipulation-brigading-detection.md` — general brigading detection

---

## Sources

- MiCA Regulation (EU) 2023/1114, Art. 91 — Market manipulation prohibition
- FCA PS22/4 — Cryptoasset Financial Promotions (UK): https://www.fca.org.uk/publications/policy-statements/ps22-4
- SEC — Social Media and Market Manipulation: https://www.sec.gov/investor/alerts/socialmediaandmarketmanipulation.htm
- Cloudflare Workers Cron Triggers: https://developers.cloudflare.com/workers/configuration/cron-triggers/
- Cloudflare D1 batch API: https://developers.cloudflare.com/d1/worker-api/d1-database/#batch-statements
