# feature-cookbook-search-ranking

**Issue:** Search ranking — relevance, popularity, recency
**Date:** 2026-08-09
**Status:** documented

## Symptom
Users search for "redis." The results are 1000 random
documents. The most relevant is on page 5. The user
gives up. You wish your search was better.

## Root cause
**Search without ranking is just a filter.** Rank the
results.

**Source:** ElasticSearch — BM25.

## The "BM25" algorithm

BM25 is the standard full-text ranking:
- **Term frequency:** How often does the term appear?
- **Document length:** Shorter docs are more relevant
- **IDF:** How rare is the term in the corpus?

**Source:** Wikipedia BM25:
https://en.wikipedia.org/wiki/Okapi_BM25

## The "FTS5 rank" pattern

For FTS5, the built-in `rank`:
```ts
const results = await env.DB!.prepare(`
  SELECT u.*, rank
  FROM users u
  JOIN users_fts ON users_fts.rowid = u.rowid
  WHERE users_fts MATCH ?
  ORDER BY rank
  LIMIT 20
`).bind('alice').all<{ id: string; email: string; displayName: string; rank: number }>();
```

The rank is built-in.

## The "composite ranking" pattern

For composite ranking (multiple signals):
```ts
function rankUser(user: any, query: string): number {
  const q = query.toLowerCase();
  const name = user.displayName.toLowerCase();
  const email = user.email.toLowerCase();

  let score = 0;

  // Exact match (highest)
  if (name === q) score += 1000;
  if (email === q) score += 800;

  // Prefix match
  if (name.startsWith(q)) score += 500;
  if (email.startsWith(q)) score += 400;

  // Substring match
  if (name.includes(q)) score += 100;
  if (email.includes(q)) score += 80;

  // Boost: popular users
  if (user.viewCount > 1000) score += 50;

  // Boost: verified users
  if (user.verified) score += 20;

  return score;
}

const results = await env.DB!.prepare(`SELECT * FROM users`).all();
const ranked = results.results
  .map(u => ({ ...u, score: rankUser(u, query) }))
  .sort((a, b) => b.score - a.score)
  .slice(0, 20);
```

The composite score is computed.

## The "recency" pattern

For recency boost:
```ts
function recencyBoost(item: any): number {
  const ageInDays = (Date.now() - new Date(item.createdAt).getTime()) / (24 * 60 * 60 * 1000);
  return Math.max(0, 100 - ageInDays);  // 100 for new, 0 for 100 days old
}

const score = relevanceScore + recencyBoost(item) + popularityScore(item);
```

The recency is a boost.

## The "popularity" pattern

For popularity boost:
```ts
function popularityScore(item: any): number {
  // Log-scaled view count
  return Math.log10(item.viewCount + 1) * 10;
}
```

The popularity is log-scaled.

## The "personalization" pattern

For personalization, the user's history:
```ts
function personalize(userId: string, item: any, env: Env): number {
  // Boost items from the same author the user follows
  const follows = await env.DB!.prepare(
    `SELECT followed_id FROM follows WHERE follower_id = ?`
  ).bind(userId).all();

  if (follows.results.some(f => f.followed_id === item.authorId)) {
    return 50;
  }

  return 0;
}
```

The personalization is contextual.

## The "A/B test ranking" pattern

For A/B testing rankings:
```ts
function getRanker(userId: string, env: Env): (item: any) => number {
  const variant = hashUserToVariant(userId, ['A', 'B']);

  if (variant === 'A') {
    return rankerA;  // Old ranking
  } else {
    return rankerB;  // New ranking
  }
}

const ranker = getRanker(user.id, env);
const ranked = items.sort((a, b) => ranker(b) - ranker(a));
```

The ranking is A/B tested.

## The "search facets" pattern

For facets (count by category):
```ts
const results = await env.DB!.prepare(`
  SELECT * FROM users WHERE name LIKE ?
`).bind(`%${query}%`).all();

const facets = {
  verified: results.results.filter(u => u.verified).length,
  unverified: results.results.filter(u => !u.verified).length,
  byCountry: {},
};

for (const user of results.results) {
  facets.byCountry[user.country] = (facets.byCountry[user.country] ?? 0) + 1;
}
```

The facets are computed.

## The "search observability" pattern

For observability:
- **Query:** What is the user searching?
- **Result count:** How many results?
- **Click position:** What did they click?
- **Zero-result rate:** % no results
- **Latency:** Time to result

```ts
logEvent('search.query', 'info', {
  query,
  resultCount: results.length,
  latencyMs: Date.now() - start,
  userId: ctx.user.id,
});
```

The search is monitored.

## The "synonyms" pattern

For synonyms:
```ts
const synonyms: Record<string, string[]> = {
  'js': ['javascript', 'node', 'nodejs'],
  'k8s': ['kubernetes'],
  'py': ['python'],
};

function expandQuery(query: string): string {
  const words = query.toLowerCase().split(' ');
  return words.map(w => synonyms[w]?.[0] ?? w).join(' ');
}
```

The query is expanded.

## The "search anti-pattern" anti-patterns

### 1. No ranking
- **Issue:** Random results
- **Fix:** Use FTS5 rank

### 2. Wrong ranking
- **Issue:** Most popular at top
- **Fix:** Match user intent

### 3. No personalization
- **Issue:** Generic results
- **Fix:** Personalize

### 4. No zero-result handling
- **Issue:** User gets nothing
- **Fix:** Suggest similar

### 5. Slow ranking
- **Issue:** Latency
- **Fix:** Pre-compute + cache

## Verification
- **Test:** Ranking is correct
- **Test:** A/B test works
- **Live:** CTR is monitored
- **Audit:** Quarterly review

## Gotchas
- **The "no ranking" anti-pattern.** Always rank.
- **The "wrong ranking" anti-pattern.** Test with users.

## Related
- `feature-cookbook-search-detail.md`
- `feature-cookbook-data-import.md`
- `feature-cookbook-experimentation.md`
- BM25: https://en.wikipedia.org/wiki/Okapi_BM25
- ElasticSearch: https://www.elastic.co/
