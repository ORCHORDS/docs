# Content Farm Spam Network Detection — D1 & Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Coordinated networks of aged example project accounts flood the feed with near-duplicate posts
containing affiliate links, SEO keyword stuffing, and ad-laden external URLs. Unlike individual
spammers, content farms distribute posting across many personas with established account
histories. Their posts vary surface text via synonyms and templates but share structural
fingerprints: overlapping outbound domain clusters, synchronized posting windows, and recycled
media assets. Platforms face ad-fraud liability and user experience harm if these networks go
undetected.

## Context

Detection targets the network graph rather than individual posts. D1 stores a domain
co-occurrence graph and posting timeline. Workers AI provides semantic deduplication via
sentence embeddings. A nightly Cron Worker runs domain-cluster analysis to surface farm
cohorts for bulk suspension. KV caches cohort membership for fast ingest-time gating.

## 1. Domain Co-occurrence Graph Recording

```typescript
// workers/content-farm-detect.ts
export interface Env {
  DB: D1Database;
  AI: Ai;
  FARM_FLAGS: KVNamespace;
}

function extractDomains(text: string): string[] {
  const matches = [...text.matchAll(/https?:\/\/([^/\s"'<>]+)/gi)];
  const raw = matches.map(m => m[1].toLowerCase().replace(/^www\./, ''));
  // Filter out high-traffic benign hosts that appear across all content
  const ALLOWLIST = new Set(['youtube.com', 'twitter.com', 'instagram.com', 'tiktok.com']);
  return [...new Set(raw.filter(d => !ALLOWLIST.has(d)))];
}

async function recordDomainSignals(env: Env, userId: string, domains: string[]): Promise<void> {
  if (!domains.length) return;
  const stmts = domains.map(domain =>
    env.DB.prepare(
      `INSERT INTO domain_signals (user_id, domain, posted_at)
       VALUES (?1, ?2, ?3)`,
    ).bind(userId, domain, new Date().toISOString()),
  );
  await env.DB.batch(stmts);
}
```

## 2. Semantic Near-Duplicate Scoring via Embeddings

```typescript
async function semanticDupeScore(env: Env, userId: string, text: string): Promise<number> {
  const embResult = await env.AI.run('@cf/baai/bge-small-en-v1.5', { text });
  const vec: number[] = embResult.data[0];

  // Retrieve this user's last 5 post embeddings
  const rows = await env.DB.prepare(
    `SELECT embedding FROM post_embeddings
     WHERE user_id = ?1 ORDER BY created_at DESC LIMIT 5`,
  ).bind(userId).all<{ embedding: string }>();

  if (!rows.results.length) {
    await env.DB.prepare(
      `INSERT INTO post_embeddings (user_id, embedding, created_at) VALUES (?1, ?2, ?3)`,
    ).bind(userId, JSON.stringify(vec), new Date().toISOString()).run();
    return 0;
  }

  const cosine = (a: number[], b: number[]): number => {
    let dot = 0, na = 0, nb = 0;
    for (let i = 0; i < a.length; i++) { dot += a[i] * b[i]; na += a[i] ** 2; nb += b[i] ** 2; }
    return dot / (Math.sqrt(na) * Math.sqrt(nb) + 1e-8);
  };

  const maxSim = Math.max(...rows.results.map(r => cosine(vec, JSON.parse(r.embedding))));

  // Persist the new embedding
  await env.DB.prepare(
    `INSERT INTO post_embeddings (user_id, embedding, created_at) VALUES (?1, ?2, ?3)`,
  ).bind(userId, JSON.stringify(vec), new Date().toISOString()).run();

  return maxSim; // >0.92 = near-duplicate spin
}
```

## 3. Synchronized Posting Burst Detection

```typescript
async function domainBurstScore(env: Env, domains: string[]): Promise<number> {
  if (!domains.length) return 0;
  const windowStart = new Date(Date.now() - 5 * 60 * 1000).toISOString();
  let maxScore = 0;

  for (const domain of domains) {
    const row = await env.DB.prepare(
      `SELECT COUNT(DISTINCT user_id) AS accounts FROM domain_signals
       WHERE domain = ?1 AND posted_at > ?2`,
    ).bind(domain, windowStart).first<{ accounts: number }>();
    const accounts = row?.accounts ?? 0;
    // >8 unique accounts posting the same domain within 5 min → farm burst
    maxScore = Math.max(maxScore, Math.min(accounts / 8, 1));
  }

  return maxScore;
}
```

## 4. Nightly Cron Farm Cohort Analysis

```typescript
// Scheduled Worker — wrangler.toml: [triggers] crons = ["0 3 * * *"]
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const since = new Date(Date.now() - 86_400_000).toISOString();

    // Domains shared by ≥5 distinct accounts in the past 24 h
    const farmDomains = await env.DB.prepare(
      `SELECT domain, COUNT(DISTINCT user_id) AS cnt
       FROM domain_signals
       WHERE posted_at > ?1
       GROUP BY domain
       HAVING COUNT(DISTINCT user_id) >= 5`,
    ).bind(since).all<{ domain: string; cnt: number }>();

    for (const { domain, cnt } of farmDomains.results) {
      const accounts = await env.DB.prepare(
        `SELECT DISTINCT user_id FROM domain_signals
         WHERE domain = ?1 AND posted_at > ?2`,
      ).bind(domain, since).all<{ user_id: string }>();

      // Write cohort membership to KV for fast ingest gating
      for (const { user_id } of accounts.results) {
        await env.FARM_FLAGS.put(
          `farm:${user_id}`,
          JSON.stringify({ domain, peerCount: cnt, flaggedAt: new Date().toISOString() }),
          { expirationTtl: 7 * 86400 },
        );
      }
    }
  },
} satisfies ExportedHandler<Env>;
```

## 5. Ingest Gate Using KV Farm Flags

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { userId, text, postId } = await request.json<{
      userId: string; text: string; postId: string;
    }>();

    // Fastest path: reject known farm members immediately
    const farmFlag = await env.FARM_FLAGS.get(`farm:${userId}`);
    if (farmFlag) {
      return new Response(
        JSON.stringify({ decision: 'blocked', reason: 'known_farm_network' }),
        { status: 403, headers: { 'Content-Type': 'application/json' } },
      );
    }

    const domains = extractDomains(text);

    const [dupeScore, burstScore] = await Promise.all([
      semanticDupeScore(env, userId, text),
      domainBurstScore(env, domains),
    ]);

    await recordDomainSignals(env, userId, domains);

    const decision =
      dupeScore > 0.92 || burstScore > 0.75 ? 'review' : 'approved';

    return new Response(JSON.stringify({ decision, dupeScore, burstScore }), {
      headers: { 'Content-Type': 'application/json' },
    });
  },
} satisfies ExportedHandler<Env>;
```

## Anti-patterns

- Running cosine similarity against all historical posts — cap the lookback to the last 5 and add an index on `(user_id, created_at)` to avoid full-table scans.
- Treating any shared domain as a farm signal — CDNs and link shorteners (bit.ly, t.co) appear across millions of legitimate posts; maintain an allowlist of benign high-traffic hosts.
- Storing embeddings indefinitely in D1 — at 384 floats × 4 bytes each, the table grows quickly; prune rows older than 30 days with the nightly cron.
- Bulk-suspending entire cohorts without human review — a shared viral creator link can produce a false farm signal; route to review, not auto-suspend.

## Gotchas

- D1 `HAVING` clauses cannot reference column aliases in SQLite; repeat the full aggregate: `HAVING COUNT(DISTINCT user_id) >= 5`, not `HAVING cnt >= 5`.
- The Cron Worker's `scheduled` signature is `(event, env, ctx)` — use `ctx.waitUntil()` for tasks that must outlive the handler, not bare async awaits that may be cut off.
- KV `put` in a loop over thousands of accounts will hit rate limits; prefer D1 batch inserts and query D1 from the ingest gate instead.
- `@cf/baai/bge-small-en-v1.5` returns a 384-dimension vector; if you later switch to a different model, stored vectors in D1 will be incompatible — backfill or version the embedding column.

## Verification

```bash
# Simulate a domain burst from 10 different users
for i in $(seq 1 10); do
  curl -s -X POST https://your-worker.workers.dev/ \
    -H 'Content-Type: application/json' \
    -d "{\"userId\":\"u$i\",\"text\":\"Check this https://spamfarm.example.com\",\"postId\":\"p$i\"}" \
    > /dev/null
done

# 11th post should trigger burst score
curl -X POST https://your-worker.workers.dev/ \
  -H 'Content-Type: application/json' \
  -d '{"userId":"u11","text":"Buy now https://spamfarm.example.com","postId":"p11"}'
# Expect: { "decision": "review", "burstScore": >= 0.75 }

# Inspect domain_signals
wrangler d1 execute YOUR_DB --command \
  "SELECT domain, COUNT(DISTINCT user_id) AS accounts FROM domain_signals GROUP BY domain ORDER BY accounts DESC LIMIT 10;"
```

## Related

- `spam-post-detection-cloudflare-workers-ai.md`
- `coordinated-inauthentic-behavior-detection-d1.md`
- `platform-manipulation-brigading-detection.md`
- `platform-abuse-rate-velocity-d1-workers.md`
- `repeat-offender-detection-anonymous-sessions.md`
- `hash-based-duplicate-content-detection-r2.md`

## Sources

- Cloudflare Workers Cron Triggers: https://developers.cloudflare.com/workers/configuration/cron-triggers/
- BGE-Small embedding model card: https://huggingface.co/BAAI/bge-small-en-v1.5
- Stanford Internet Observatory content farm research: https://cyber.fsi.stanford.edu/
- D1 best practices: https://developers.cloudflare.com/d1/best-practices/
- EU DSA Article 34 risk assessment — inauthentic amplification: https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32022R2065
