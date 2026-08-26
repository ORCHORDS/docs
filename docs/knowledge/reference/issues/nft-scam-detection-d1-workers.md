# NFT Scam Detection — D1 & Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

example project users share NFT mint links, collection drops, and "allowlist" giveaways. A significant
fraction are rug-pull promotions, fake royalty schemes, or wash-trading rings inflating floor
prices. These posts arrive in coordinated bursts from low-trust accounts and link to newly
registered contract addresses with no on-chain history. Operators must catch and suppress them
before they reach the wider feed.

## Context

Detection combines three signals stored in D1: (1) a contract-address block-list with risk
tiers, (2) URL pattern matching against known scam domains, and (3) per-user posting velocity
that flags coordinated bursts. Workers AI provides zero-shot text classification to catch novel
scam copy that has not yet reached the block-list. An R2-backed audit log retains evidence for
law-enforcement and regulator requests.

## 1. Contract Address Risk Lookup in D1

```typescript
// workers/nft-scam-detect.ts
export interface Env {
  DB: D1Database;
  AI: Ai;
  AUDIT: R2Bucket;
}

interface NftPost {
  postId: string;
  userId: string;
  text: string;
  contractAddress?: string;
}

async function contractRisk(
  env: Env,
  address: string,
): Promise<'blocked' | 'high' | 'unknown'> {
  const row = await env.DB.prepare(
    'SELECT risk_tier FROM nft_contract_blocklist WHERE LOWER(address) = LOWER(?1) LIMIT 1',
  ).bind(address).first<{ risk_tier: string }>();
  return (row?.risk_tier as 'blocked' | 'high') ?? 'unknown';
}
```

## 2. Scam Domain URL Pattern Matching

```typescript
const SCAM_DOMAIN_PATTERNS: RegExp[] = [
  /free-?nft\d*\.(xyz|io|art)/i,
  /nft-?airdrop[^.]*\.(com|net)/i,
  /mint-?now-?\d+\.(io|xyz)/i,
  /allowlist-?claim[^.]*\.(io|xyz|art)/i,
];

function extractUrls(text: string): string[] {
  return [...text.matchAll(/https?:\/\/[^\s"'<>]+/gi)].map(m => m[0]);
}

function domainScamScore(text: string): number {
  const urls = extractUrls(text);
  if (!urls.length) return 0;
  let hits = 0;
  for (const url of urls) {
    for (const pattern of SCAM_DOMAIN_PATTERNS) {
      if (pattern.test(url)) hits++;
    }
  }
  return Math.min(hits / Math.max(urls.length, 1), 1);
}
```

## 3. Coordinated Posting Velocity via D1

```typescript
async function postingVelocityScore(env: Env, userId: string): Promise<number> {
  // Count posts with NFT signals from this user in the last 10 minutes
  const since = new Date(Date.now() - 10 * 60 * 1000).toISOString();
  const row = await env.DB.prepare(
    `SELECT COUNT(*) AS cnt FROM posts
     WHERE user_id = ?1 AND created_at > ?2 AND has_nft_signal = 1`,
  ).bind(userId, since).first<{ cnt: number }>();
  const cnt = row?.cnt ?? 0;
  // >5 NFT-tagged posts in 10 min = score 1.0
  return Math.min(cnt / 5, 1);
}
```

## 4. Workers AI Zero-Shot Classification

```typescript
async function aiScamProbability(env: Env, text: string): Promise<number> {
  const result = await env.AI.run('@cf/facebook/bart-large-mnli', {
    text: text.slice(0, 512),
    candidate_labels: [
      'cryptocurrency scam',
      'NFT rug pull',
      'legitimate NFT project',
    ],
  });
  // Look up by label name — returned order is descending by score, not input order
  const scamIdx = result.labels.indexOf('cryptocurrency scam');
  const rugIdx = result.labels.indexOf('NFT rug pull');
  return Math.max(result.scores[scamIdx] ?? 0, result.scores[rugIdx] ?? 0);
}
```

## 5. Decision Gate and R2 Audit Trail

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const post = await request.json<NftPost>();

    const [contractTier, domainScore, velocityScore] = await Promise.all([
      post.contractAddress
        ? contractRisk(env, post.contractAddress)
        : Promise.resolve('unknown' as const),
      Promise.resolve(domainScamScore(post.text)),
      postingVelocityScore(env, post.userId),
    ]);

    // Only call AI when fast signals are inconclusive
    let aiScore = 0;
    if (contractTier === 'unknown' && domainScore < 0.5) {
      aiScore = await aiScamProbability(env, post.text);
    }

    const blocked =
      contractTier === 'blocked' || domainScore > 0.6 || aiScore > 0.75;
    const flagged =
      !blocked && (contractTier === 'high' || velocityScore > 0.6 || aiScore > 0.5);
    const decision = blocked ? 'blocked' : flagged ? 'review' : 'approved';

    // Persist audit record to R2 for legal hold
    await env.AUDIT.put(
      `nft-scam/${post.postId}.json`,
      JSON.stringify({ post, contractTier, domainScore, velocityScore, aiScore, decision }),
    );

    if (blocked || flagged) {
      await env.DB.prepare(
        `INSERT INTO moderation_queue (post_id, user_id, reason, tier, queued_at)
         VALUES (?1, ?2, ?3, ?4, ?5)`,
      ).bind(post.postId, post.userId, 'nft_scam', decision, new Date().toISOString()).run();
    }

    return new Response(JSON.stringify({ decision }), {
      status: blocked ? 403 : 200,
      headers: { 'Content-Type': 'application/json' },
    });
  },
} satisfies ExportedHandler<Env>;
```

## Anti-patterns

- Relying solely on contract-address block-lists — scammers deploy new contracts per campaign within hours; combine with text and velocity signals.
- Blocking all NFT mentions platform-wide — this punishes legitimate creator communities; use scored thresholds and route borderline cases to human review.
- Calling Workers AI on every post — invoke the classifier only when cheaper signals are inconclusive to stay within CPU budget.
- Writing scam copy verbatim to D1 — store signal scores and content hashes, not raw post text, to minimise personal-data surface under GDPR Article 5(1)(c).

## Gotchas

- `@cf/facebook/bart-large-mnli` returns `labels` in descending score order, not in the order you passed `candidate_labels`; always look up by label name using `Array.indexOf`, not by position index.
- Ethereum contract addresses are case-insensitive (EIP-55 checksum is cosmetic); normalise with `LOWER()` in both the insert and the select path.
- D1 `COUNT(*)` queries without an index on `(user_id, created_at)` will full-scan as the posts table grows; add: `CREATE INDEX idx_posts_user_nft ON posts (user_id, created_at) WHERE has_nft_signal = 1;`
- R2 `put` inside a `fetch` handler counts against wall-time; for high-throughput ingest, defer audit writes to a Queue consumer.

## Verification

```bash
# Seed the block-list
wrangler d1 execute YOUR_DB --command \
  "INSERT INTO nft_contract_blocklist (address, risk_tier) VALUES ('0xdeadbeef', 'blocked');"

# POST a blocked-contract scam post
curl -X POST https://your-worker.workers.dev/ \
  -H 'Content-Type: application/json' \
  -d '{"postId":"p1","userId":"u1","text":"Free airdrop https://free-nft99.xyz","contractAddress":"0xdeadbeef"}'
# Expect: { "decision": "blocked" }

# Confirm moderation_queue row
wrangler d1 execute YOUR_DB --command \
  "SELECT * FROM moderation_queue WHERE post_id = 'p1';"
```

## Related

- `financial-fraud-detection-digital-goods.md`
- `cryptocurrency-regulatory-risk-platform.md`
- `coordinated-inauthentic-behavior-detection-d1.md`
- `platform-abuse-rate-velocity-d1-workers.md`
- `mica-cryptocurrency-enforcement-2026.md`
- `legal-hold-evidence-preservation-d1-r2.md`

## Sources

- Chainalysis NFT Market Report 2024: https://www.chainalysis.com/blog/nft-market-report-2024/
- Cloudflare Workers AI model catalog: https://developers.cloudflare.com/workers-ai/models/
- BART-MNLI zero-shot classification: https://huggingface.co/facebook/bart-large-mnli
- D1 indexing guidance: https://developers.cloudflare.com/d1/best-practices/
- MiCA Regulation (EU) 2023/1114: https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32023R1114
