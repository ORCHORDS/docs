# Cryptocurrency Fraud & Financial Scam Detection — Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

example project DMs and public posts carry pig-butchering scripts, fake investment platform links,
pump-and-dump promotions, and "double your crypto" giveaway impersonations. These scams cause
direct financial harm to users and expose the platform to regulatory liability under MiCA,
the FTC Act, and emerging social-platform financial-content rules. Early interception at the
post and DM layers is mandatory; post-hoc takedowns after virality are insufficient.

## Context

Detection runs in two layers: (1) a fast keyword/pattern gate in the Workers fetch handler
using regex and a KV-cached domain block-list, and (2) a slower Workers AI zero-shot
classification for novel copy that evades keyword rules. D1 stores a per-user financial-content
incident ledger for escalating repeat offenders. Cloudflare Analytics Engine records signal
telemetry for weekly compliance and MiCA Article 76 reporting.

## 1. Keyword and Pattern Gate

```typescript
// workers/crypto-fraud-detect.ts
export interface Env {
  AI: Ai;
  DB: D1Database;
  BLOCKED_DOMAINS: KVNamespace;
  AE: AnalyticsEngineDataset;
}

const FRAUD_PATTERNS: RegExp[] = [
  /double\s+your\s+(bitcoin|btc|eth|usdt|crypto)/i,
  /send\s+\d+\s*(btc|eth|usdt)\s+(?:and|to)\s+(?:receive|get)\s+\d+/i,
  /guaranteed\s+\d+[\d.]*\s*%\s+(?:daily|weekly|monthly)\s+return/i,
  /pig\s*[-\s]?butchering|sha\s*zhu\s*pan/i,
  /recover\s+(?:lost|stolen)\s+(?:crypto|bitcoin|funds|wallet)/i,
  /connect\s+(?:your\s+)?(?:metamask|trust\s*wallet)\s+to\s+claim/i,
];

function patternScore(text: string): number {
  let hits = 0;
  for (const re of FRAUD_PATTERNS) {
    if (re.test(text)) hits++;
  }
  return Math.min(hits / 2, 1); // 2+ pattern hits → score 1.0
}
```

## 2. KV-Cached Domain Block-list

```typescript
async function domainBlocked(env: Env, text: string): Promise<boolean> {
  const domains = [...text.matchAll(/https?:\/\/([^/\s"'<>]+)/gi)]
    .map(m => m[1].toLowerCase().replace(/^www\./, ''));

  for (const domain of domains) {
    const hit = await env.BLOCKED_DOMAINS.get(domain);
    if (hit !== null) return true;
  }
  return false;
}
```

## 3. Workers AI Zero-Shot Financial Scam Classifier

```typescript
async function aiScamScore(env: Env, text: string): Promise<number> {
  // Limit text to ~256 chars to stay within BART's 1 024-token budget
  // with multilingual input (multilingual tokenisation is denser than English)
  const result = await env.AI.run('@cf/facebook/bart-large-mnli', {
    text: text.slice(0, 256),
    candidate_labels: [
      'cryptocurrency investment scam',
      'financial fraud',
      'legitimate financial discussion',
    ],
  });
  // Scores are returned in descending order; look up by label name, not index
  const scamIdx = result.labels.indexOf('cryptocurrency investment scam');
  const fraudIdx = result.labels.indexOf('financial fraud');
  return Math.max(result.scores[scamIdx] ?? 0, result.scores[fraudIdx] ?? 0);
}
```

## 4. Per-User Financial Incident Ledger in D1

```typescript
async function incidentCount(env: Env, userId: string): Promise<number> {
  const since = new Date(Date.now() - 30 * 86_400_000).toISOString();
  const row = await env.DB.prepare(
    `SELECT COUNT(*) AS cnt FROM financial_incidents
     WHERE user_id = ?1 AND detected_at > ?2`,
  ).bind(userId, since).first<{ cnt: number }>();
  return row?.cnt ?? 0;
}

async function recordIncident(
  env: Env,
  userId: string,
  postId: string,
  signals: { pattern: number; ai: number; composite: number },
): Promise<void> {
  await env.DB.prepare(
    `INSERT INTO financial_incidents (user_id, post_id, signals_json, detected_at)
     VALUES (?1, ?2, ?3, ?4)`,
  ).bind(userId, postId, JSON.stringify(signals), new Date().toISOString()).run();
}
```

## 5. Decision Handler with Analytics Engine Telemetry

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { userId, postId, text } = await request.json<{
      userId: string; postId: string; text: string;
    }>();

    // Fast synchronous signals first
    const [blocked, pattern] = await Promise.all([
      domainBlocked(env, text),
      Promise.resolve(patternScore(text)),
    ]);

    // Invoke AI only when cheap signals are inconclusive
    let ai = 0;
    if (!blocked && pattern < 0.5) {
      ai = await aiScamScore(env, text);
    }

    const composite = blocked ? 1.0 : Math.max(pattern, ai);
    const priorIncidents = await incidentCount(env, userId);

    // Repeat offenders escalate at a lower threshold
    const decision =
      composite > 0.75 || priorIncidents >= 3 ? 'blocked' :
      composite > 0.4 ? 'review' : 'approved';

    if (decision !== 'approved') {
      await recordIncident(env, userId, postId, { pattern, ai, composite });
    }

    // Fire-and-forget telemetry for compliance dashboards
    env.AE.writeDataPoint({
      blobs: [userId, decision],
      doubles: [composite, priorIncidents],
      indexes: ['crypto_fraud'],
    });

    return new Response(JSON.stringify({ decision, composite }), {
      status: decision === 'blocked' ? 403 : 200,
      headers: { 'Content-Type': 'application/json' },
    });
  },
} satisfies ExportedHandler<Env>;
```

## 6. Scheduled Domain Block-list Sync

```typescript
// Cron Worker — wrangler.toml: [triggers] crons = ["0 5 * * *"]
// Pulls updated block-list from GIFCT TCAP or internal threat-intel feed
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const resp = await fetch('https://internal-threat-intel.example/crypto-scam-domains.txt');
    if (!resp.ok) return;
    const text = await resp.text();
    const domains = text.split('\n').map(d => d.trim()).filter(Boolean);
    await Promise.all(
      domains.map(d => env.BLOCKED_DOMAINS.put(d, '1', { expirationTtl: 7 * 86400 })),
    );
  },
} satisfies ExportedHandler<Env>;
```

## Anti-patterns

- Using regex alone without AI fallback — pig-butchering scripts are paraphrased continuously; keyword patterns miss novel copy within days of a new campaign.
- Storing raw scam post text in D1 for audit — the content may be harmful data subject to EU minimisation rules; store signal scores and a SHA-256 content hash, not raw text.
- Blocking every mention of "bitcoin" or "crypto" — over-suppression drives legitimate creator finance discussion off the platform; use scored thresholds and layered signals.
- Ignoring the repeat-offender escalation path — a user who accumulates three `review` decisions should auto-block on the next incident without requiring a high standalone composite.

## Gotchas

- `env.AE.writeDataPoint` is fire-and-forget in the Workers runtime — failures are silently swallowed and will not throw or roll back D1 writes. Do not use Analytics Engine as the audit system of record.
- KV `get` returns `null` for missing keys (never `undefined`); `if (hit !== null)` is the correct guard — `if (hit)` would also incorrectly pass on an empty-string value stored as a falsy sentinel.
- The `text.slice(0, 256)` character limit for the BART classifier is conservative by design; multilingual and emoji-heavy text tokenises at 3–5 chars per token, so 256 chars maps to roughly 50–80 tokens — well within budget.
- D1 `COUNT(*)` with a date range filter on `financial_incidents` requires an index: `CREATE INDEX idx_fi_user_date ON financial_incidents (user_id, detected_at);` — without it the query scans the full table.

## Verification

```bash
# Test a pig-butchering pattern
curl -X POST https://your-worker.workers.dev/ \
  -H 'Content-Type: application/json' \
  -d '{"userId":"u1","postId":"p1","text":"Send 0.1 BTC and receive 0.3 BTC back — guaranteed 300% daily returns!"}'
# Expect: { "decision": "blocked", "composite": 1.0 }

# Add a scam domain to the block-list
wrangler kv key put --binding BLOCKED_DOMAINS "cryptodouble99.io" "1"

# Confirm the domain blocks a post
curl -X POST https://your-worker.workers.dev/ \
  -H 'Content-Type: application/json' \
  -d '{"userId":"u2","postId":"p2","text":"Invest here https://cryptodouble99.io"}'
# Expect: { "decision": "blocked", "composite": 1.0 }

# Check Analytics Engine telemetry in CF dashboard:
# Workers & Pages → your worker → Analytics → custom dataset "crypto_fraud"
```

## Related

- `financial-fraud-detection-digital-goods.md`
- `cryptocurrency-regulatory-risk-platform.md`
- `mica-cryptocurrency-enforcement-2026.md`
- `nft-scam-detection-d1-workers.md`
- `platform-abuse-rate-velocity-d1-workers.md`
- `legal-hold-evidence-preservation-d1-r2.md`

## Sources

- FTC pig-butchering scam alert (2023): https://consumer.ftc.gov/articles/what-know-about-cryptocurrency-scams
- Global Anti-Scam Alliance reports: https://www.global-anti-scam.org/
- MiCA Regulation (EU) 2023/1114: https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32023R1114
- Cloudflare Analytics Engine: https://developers.cloudflare.com/analytics/analytics-engine/
- Cloudflare Workers KV: https://developers.cloudflare.com/kv/
