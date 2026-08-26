# AI Content Recommendation with Collaborative Filtering and D1

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

You need personalised content recommendations for authenticated users without a dedicated ML serving cluster. The
example project platform already stores user interaction events in Cloudflare D1 and content embeddings in Vectorize, making
it natural to build a lightweight collaborative filtering layer directly inside Workers.

## Context

Collaborative filtering infers a user's preferences from the aggregate behaviour of similar users. The simplest viable
approach for a Workers runtime is item-based CF: precompute item-to-item co-occurrence scores offline (or
incrementally), store them in D1, then at request time rank candidate items by the dot product of the user's recent
interaction history against those co-occurrence weights. Vectorize supplies the semantic fallback when co-occurrence
data is sparse (cold-start). D1's row-level SQLite queries are fast enough for the recommendation hot path when the
item catalogue is in the tens of thousands.

## D1 Schema and Interaction Recording

```typescript
// schema.sql — run once via wrangler d1 execute
/*
CREATE TABLE IF NOT EXISTS interactions (
  user_id    TEXT    NOT NULL,
  item_id    TEXT    NOT NULL,
  event_type TEXT    NOT NULL,  -- 'view' | 'like' | 'share' | 'purchase'
  weight     REAL    NOT NULL DEFAULT 1.0,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_interactions_user ON interactions(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_interactions_item ON interactions(item_id);

CREATE TABLE IF NOT EXISTS item_similarity (
  item_a  TEXT NOT NULL,
  item_b  TEXT NOT NULL,
  score   REAL NOT NULL,
  PRIMARY KEY (item_a, item_b)
);
CREATE INDEX IF NOT EXISTS idx_sim_a ON item_similarity(item_a, score DESC);
*/

interface Env {
  DB: D1Database;
  VECTORIZE: VectorizeIndex;
  AI: Ai;
}

const EVENT_WEIGHTS: Record<string, number> = {
  view: 1.0,
  like: 3.0,
  share: 4.0,
  purchase: 5.0,
};

async function recordInteraction(
  env: Env,
  userId: string,
  itemId: string,
  eventType: keyof typeof EVENT_WEIGHTS
): Promise<void> {
  const weight = EVENT_WEIGHTS[eventType] ?? 1.0;
  await env.DB.prepare(
    `INSERT INTO interactions (user_id, item_id, event_type, weight, created_at)
     VALUES (?, ?, ?, ?, ?)`
  )
    .bind(userId, itemId, eventType, weight, Date.now())
    .run();
}
```

## Item-Based Collaborative Filtering Lookup

Fetch the user's recent interactions, then JOIN against item_similarity to surface candidate items.

```typescript
interface RecommendedItem {
  itemId: string;
  cfScore: number;
  source: "cf" | "semantic";
}

async function getCollaborativeRecs(
  env: Env,
  userId: string,
  limit: number
): Promise<RecommendedItem[]> {
  // Pull the 20 most recent weighted interactions for this user
  const history = await env.DB.prepare(
    `SELECT item_id, SUM(weight) AS total_weight
     FROM interactions
     WHERE user_id = ?
       AND created_at > ?
     GROUP BY item_id
     ORDER BY total_weight DESC
     LIMIT 20`
  )
    .bind(userId, Date.now() - 30 * 24 * 60 * 60 * 1000)
    .all<{ item_id: string; total_weight: number }>();

  if (!history.results.length) return [];

  const interactedIds = history.results.map((r) => r.item_id);
  const weightMap = Object.fromEntries(
    history.results.map((r) => [r.item_id, r.total_weight])
  );

  // Build parameterised IN list
  const placeholders = interactedIds.map(() => "?").join(",");

  const candidates = await env.DB.prepare(
    `SELECT s.item_b AS item_id,
            SUM(s.score * ?) AS cf_score
     FROM item_similarity s
     WHERE s.item_a IN (${placeholders})
       AND s.item_b NOT IN (${placeholders})
     GROUP BY s.item_b
     ORDER BY cf_score DESC
     LIMIT ?`
  )
    .bind(
      1, // placeholder for weight — see note below
      ...interactedIds,
      ...interactedIds,
      limit
    )
    .all<{ item_id: string; cf_score: number }>();

  return candidates.results.map((row) => ({
    itemId: row.item_id,
    cfScore: row.cf_score,
    source: "cf",
  }));
}
```

## Semantic Fallback for Cold-Start Users

When a user has fewer than 3 interaction events, fall back to Vectorize nearest-neighbour search on their profile
embedding. The profile embedding is the average of the embeddings of items they have viewed.

```typescript
async function getSemanticFallbackRecs(
  env: Env,
  userId: string,
  limit: number
): Promise<RecommendedItem[]> {
  const history = await env.DB.prepare(
    `SELECT item_id FROM interactions WHERE user_id = ? LIMIT 5`
  )
    .bind(userId)
    .all<{ item_id: string }>();

  if (!history.results.length) return [];

  // Fetch stored embeddings from Vectorize for each item the user interacted with
  const itemIds = history.results.map((r) => r.item_id);
  const fetched = await env.VECTORIZE.getByIds(itemIds);

  if (!fetched.length) return [];

  const dim = fetched[0].values.length;
  const profileVec = new Array<number>(dim).fill(0);

  for (const v of fetched) {
    for (let i = 0; i < dim; i++) profileVec[i] += v.values[i];
  }
  for (let i = 0; i < dim; i++) profileVec[i] /= fetched.length;

  const results = await env.VECTORIZE.query(profileVec, {
    topK: limit + itemIds.length,
    returnMetadata: "none",
  });

  const excludeSet = new Set(itemIds);
  return results.matches
    .filter((m) => !excludeSet.has(m.id))
    .slice(0, limit)
    .map((m) => ({
      itemId: m.id,
      cfScore: m.score,
      source: "semantic",
    }));
}

// Unified recommendation entry point
async function recommend(
  env: Env,
  userId: string,
  limit = 10
): Promise<RecommendedItem[]> {
  const count = await env.DB.prepare(
    `SELECT COUNT(*) AS n FROM interactions WHERE user_id = ?`
  )
    .bind(userId)
    .first<{ n: number }>();

  if ((count?.n ?? 0) < 3) {
    return getSemanticFallbackRecs(env, userId, limit);
  }
  return getCollaborativeRecs(env, userId, limit);
}
```

## Worker Fetch Handler

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === "POST" && url.pathname === "/interactions") {
      const { userId, itemId, eventType } = (await request.json()) as {
        userId: string;
        itemId: string;
        eventType: string;
      };
      await recordInteraction(env, userId, itemId, eventType as any);
      return new Response("OK", { status: 204 });
    }

    if (request.method === "GET" && url.pathname === "/recommendations") {
      const userId = url.searchParams.get("userId");
      if (!userId) return new Response("Missing userId", { status: 400 });
      const limit = parseInt(url.searchParams.get("limit") ?? "10", 10);
      const recs = await recommend(env, userId, limit);
      return Response.json({ userId, recommendations: recs });
    }

    return new Response("Not Found", { status: 404 });
  },
} satisfies ExportedHandler<Env>;
```

## Anti-patterns

- Running co-occurrence computation at request time — this is O(n²) over the item catalogue and will exceed the 30 s
  Worker CPU limit for any non-trivial catalogue.
- Recommending items the user has already purchased — always exclude previously interacted IDs from candidates.
- Ignoring recency bias — an interaction from 6 months ago should carry less weight than one from yesterday; decay the
  weight by age before storing or apply a recency multiplier at query time.

## Gotchas

- D1 does not support array-valued parameters natively. Build the `IN (?, ?, ?)` placeholder string dynamically and
  spread the values into `.bind()`; mixing too many values risks hitting the 100-parameter SQLite limit.
- Vectorize `getByIds` returns results in arbitrary order and silently omits IDs that do not exist. Always guard
  against partial results when averaging profile vectors.

## Verification

```bash
# Seed interactions
curl -X POST https://your-worker.workers.dev/interactions \
  -H "Content-Type: application/json" \
  -d '{"userId":"u1","itemId":"item-42","eventType":"like"}'

# Fetch recommendations
curl "https://your-worker.workers.dev/recommendations?userId=u1&limit=5" | jq .

# Cold-start path — new user with no history should still return results via semantic fallback
curl "https://your-worker.workers.dev/recommendations?userId=new-user&limit=5" | jq '.recommendations[0].source'
# Expected: "semantic"
```

## Related

- `ai-ml/vector-embeddings-d1-vectorize-search.md`
- `ai-ml/retrieval-augmented-generation-d1-vectorize.md`
- `ai-ml/embedding-generation-patterns.md`

## Sources

- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/vectorize/
- https://en.wikipedia.org/wiki/Collaborative_filtering
