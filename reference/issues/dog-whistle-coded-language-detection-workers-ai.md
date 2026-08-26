# Dog-Whistle & Coded Language Detection — Workers AI

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Hate speech reports keep arriving for content that passes all keyword and regex filters cleanly. Moderators flag phrases like "the usual suspects," "👃," specific number strings (e.g., "1488," "110"), or community-specific slang that carries explicit meaning to in-group readers but looks innocuous to automated systems. Standard hate-speech models trained on explicit slurs miss this category almost entirely.

## Context

Dog-whistle language is intentionally designed to evade literal-match moderation while conveying derogatory meaning to an informed audience. Detection requires semantic understanding, cultural context, and time-series awareness (new codes emerge weekly). example project's anonymous nature makes coded language particularly attractive to bad actors because there is no persistent identity to ban. The stack is: Workers AI (embedding + classification), D1 (known-code dictionary + hit history), Queues (async re-scoring), and R2 (audit snapshots).

## 1. Known-Code Dictionary in D1

```sql
-- migrations/0041_dog_whistle_codes.sql
CREATE TABLE IF NOT EXISTS dw_codes (
  code        TEXT PRIMARY KEY,          -- normalized phrase or symbol
  category    TEXT NOT NULL,             -- hate_group | extremism | slur_proxy
  severity    INTEGER NOT NULL,          -- 1-5
  added_at    INTEGER NOT NULL,
  source      TEXT                       -- researcher citation or report ID
);

CREATE TABLE IF NOT EXISTS dw_hits (
  post_id     TEXT NOT NULL,
  code        TEXT NOT NULL,
  detected_at INTEGER NOT NULL,
  action      TEXT,                      -- flagged | removed | escalated
  PRIMARY KEY (post_id, code)
);
```

## 2. Fast Exact-Match Pass (Worker)

```typescript
// src/dw-exact.ts
export async function exactCodeMatch(
  text: string,
  env: Env
): Promise<{ hit: boolean; codes: string[]; maxSeverity: number }> {
  const normalized = text.toLowerCase().replace(/\s+/g, " ").trim();

  // Pull active codes — cached in KV with 5-min TTL
  const cacheKey = "dw:codes:v1";
  let codes: Array<{ code: string; severity: number }> = [];

  const cached = await env.KV.get(cacheKey, "json");
  if (cached) {
    codes = cached as typeof codes;
  } else {
    const rows = await env.DB.prepare(
      "SELECT code, severity FROM dw_codes ORDER BY LENGTH(code) DESC"
    ).all<{ code: string; severity: number }>();
    codes = rows.results;
    await env.KV.put(cacheKey, JSON.stringify(codes), { expirationTtl: 300 });
  }

  const hits: string[] = [];
  let maxSev = 0;

  for (const { code, severity } of codes) {
    if (normalized.includes(code)) {
      hits.push(code);
      if (severity > maxSev) maxSev = severity;
    }
  }

  return { hit: hits.length > 0, codes: hits, maxSeverity: maxSev };
}
```

## 3. Semantic Embedding Pass (Workers AI)

```typescript
// src/dw-semantic.ts
const KNOWN_HATEFUL_EXEMPLARS = [
  "we need to remove the demographic group from our country",
  "those people control the media and banks",
  "the great replacement is real and happening now",
];

export async function semanticDogWhistleScore(
  text: string,
  env: Env
): Promise<number> {
  // Embed the candidate text
  const [textEmbed, ...exemplarEmbeds] = await Promise.all([
    env.AI.run("@cf/baai/bge-large-en-v1.5", { text: [text] }),
    ...KNOWN_HATEFUL_EXEMPLARS.map((e) =>
      env.AI.run("@cf/baai/bge-large-en-v1.5", { text: [e] })
    ),
  ]);

  const tv = textEmbed.data[0] as number[];

  // Cosine similarity against each exemplar
  const sims = exemplarEmbeds.map((ex) => {
    const ev = ex.data[0] as number[];
    const dot = tv.reduce((s, v, i) => s + v * ev[i], 0);
    const normT = Math.sqrt(tv.reduce((s, v) => s + v * v, 0));
    const normE = Math.sqrt(ev.reduce((s, v) => s + v * v, 0));
    return dot / (normT * normE);
  });

  return Math.max(...sims); // 0..1; >0.72 is high-confidence match
}
```

## 4. Combined Scoring & Action Gate (Worker Entry Point)

```typescript
// src/dw-gate.ts
import { exactCodeMatch } from "./dw-exact";
import { semanticDogWhistleScore } from "./dw-semantic";

export async function evaluatePost(
  postId: string,
  text: string,
  env: Env,
  ctx: ExecutionContext
): Promise<"allow" | "queue_review" | "remove"> {
  const [exact, semanticScore] = await Promise.all([
    exactCodeMatch(text, env),
    semanticDogWhistleScore(text, env),
  ]);

  if (exact.maxSeverity >= 4 || semanticScore >= 0.82) {
    // Auto-remove: high-confidence coded hate
    ctx.waitUntil(
      env.DB.prepare(
        "INSERT OR IGNORE INTO dw_hits VALUES (?,?,?,?)"
      )
        .bind(postId, exact.codes.join(","), Date.now(), "removed")
        .run()
    );
    return "remove";
  }

  if (exact.hit || semanticScore >= 0.65) {
    ctx.waitUntil(env.MODERATION_QUEUE.send({ postId, text, semanticScore }));
    return "queue_review";
  }

  return "allow";
}
```

## 5. Emerging-Code Ingestion from Researcher Reports

```typescript
// src/dw-ingest.ts — called by internal admin endpoint
export async function ingestNewCode(
  code: string,
  category: string,
  severity: number,
  source: string,
  env: Env
): Promise<void> {
  await env.DB.prepare(
    `INSERT INTO dw_codes (code, category, severity, added_at, source)
     VALUES (?, ?, ?, ?, ?)
     ON CONFLICT(code) DO UPDATE SET severity=excluded.severity`
  )
    .bind(code.toLowerCase(), category, severity, Date.now(), source)
    .run();

  // Invalidate KV cache so Workers pick up new code within 5 min
  await env.KV.delete("dw:codes:v1");
}
```

## 6. Retroactive Re-Scan Queue Consumer

```typescript
// src/dw-rescan-consumer.ts
export default {
  async queue(batch: MessageBatch<{ postId: string; text: string }>, env: Env) {
    for (const msg of batch.messages) {
      const { postId, text } = msg.body;
      const score = await semanticDogWhistleScore(text, env);
      if (score >= 0.72) {
        await env.DB.prepare(
          "UPDATE posts SET visibility='hidden', hide_reason='dw_rescan' WHERE id=?"
        )
          .bind(postId)
          .run();
      }
      msg.ack();
    }
  },
};
```

## Anti-patterns

- Relying solely on a static slur list — new codes emerge faster than list updates.
- Using cosine similarity without exemplar diversity — a single exemplar creates a narrow funnel and misses variant phrasing.
- Blocking posts with score > 0.65 without human review — semantic models produce false positives on academic discussions and counter-speech.
- Caching codes indefinitely — stale cache means newly ingested codes take hours to take effect.

## Gotchas

- BGE embeddings are English-centric; multilingual coded language (e.g., French "remigration," German "Umvolkung") needs a multilingual model like `@cf/BAAI/bge-m3`.
- Number-based codes ("88," "1488") are common in URLs and post IDs — apply number-code detection only to prose segments, not structured fields.
- Workers AI `run()` calls count against CPU time; parallelize exemplar embeddings but cap batch size at 8 to avoid CPU-limit eviction.
- D1 `INSERT OR IGNORE` on `dw_hits` can silently drop a re-detection; use `ON CONFLICT DO UPDATE SET detected_at` if you need the latest timestamp.

## Verification

```bash
# Confirm codes table is populated
wrangler d1 execute example project-prod --command \
  "SELECT category, COUNT(*) n FROM dw_codes GROUP BY category"

# Smoke-test exact match via staging
curl -X POST https://api.example.com/internal/dw/test \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"text":"1488 day coming soon friends"}'
# Expect: {"result":"remove","codes":["1488"],"semanticScore":...}

# Confirm KV cache invalidation after ingest
wrangler kv key get --namespace-id=$KV_ID "dw:codes:v1"
# Expect: null (or freshly written JSON within 5 min of ingest)
```

## Related

- `hate-speech-detection-multilingual-workers-ai.md`
- `real-time-toxic-content-scoring-workers-ai.md`
- `automated-content-policy-rule-engine-workers-d1.md`
- `election-misinformation-detection-workers-ai.md`

## Sources

- ADL Hate Symbols Database (adl.org/resources/hate-symbols)
- GIFCT Transparency Report 2025 (gifct.org/transparency)
- "Dog Whistles, Slurs, and How to Study Them" — Tirrell (2018)
- Cloudflare Workers AI model catalog (developers.cloudflare.com/workers-ai/models/)
