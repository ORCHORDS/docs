# feature-cookbook-search-detail

**Issue:** Search — full-text, fuzzy, ranked
**Date:** 2026-08-09
**Status:** documented

## Symptom
Users search for "Alice." The DB has "alice@example.com"
and "Alice Smith." You run `LIKE '%Alice%'`. The search
is slow, case-sensitive, and the results are random.

## Root cause
**`LIKE` is not search.** Use a search engine.

**Source:** ElasticSearch docs.

## Search strategies

### LIKE
- **How:** `WHERE name LIKE '%alice%'`
- **Pros:** Built-in
- **Cons:** No ranking, slow, no fuzzy

### Full-text (FTS5)
- **How:** FTS5 virtual table
- **Pros:** Ranking, fast, no external dep
- **Cons:** SQLite only

```sql
CREATE VIRTUAL TABLE users_fts USING fts5(id, displayName, email, content=users, content_rowid=rowid);

-- Insert trigger
CREATE TRIGGER users_ai AFTER INSERT ON users BEGIN
  INSERT INTO users_fts(rowid, id, displayName, email) VALUES (new.rowid, new.id, new.displayName, new.email);
END;

-- Update trigger
CREATE TRIGGER users_au AFTER UPDATE ON users BEGIN
  UPDATE users_fts SET displayName = new.displayName, email = new.email WHERE rowid = new.rowid;
END;

-- Delete trigger
CREATE TRIGGER users_ad AFTER DELETE ON users BEGIN
  DELETE FROM users_fts WHERE rowid = old.rowid;
END;
```

### ElasticSearch
- **How:** External service
- **Pros:** Powerful, scalable
- **Cons:** Operational overhead

### Algolia
- **How:** SaaS
- **Pros:** Easy, fast
- **Cons:** Cost

For most apps, **FTS5** is enough.

## The "FTS5" pattern

For FTS5:
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

FTS5 ranks results.

## The "prefix search" pattern

For prefix search:
```ts
const results = await env.DB!.prepare(`
  SELECT * FROM users WHERE displayName LIKE ?
  ORDER BY displayName
  LIMIT 20
`).bind(`${query}%`).all();
```

The prefix is supported.

## The "fuzzy search" pattern

For fuzzy search, edit distance:
```ts
// Levenshtein distance
function levenshtein(a: string, b: string): number {
  const dp = Array.from({ length: a.length + 1 }, () => new Array(b.length + 1).fill(0));
  for (let i = 0; i <= a.length; i++) dp[i][0] = i;
  for (let j = 0; j <= b.length; j++) dp[0][j] = j;
  for (let i = 1; i <= a.length; i++) {
    for (let j = 1; j <= b.length; j++) {
      if (a[i - 1] === b[j - 1]) {
        dp[i][j] = dp[i - 1][j - 1];
      } else {
        dp[i][j] = Math.min(
          dp[i - 1][j] + 1,
          dp[i][j - 1] + 1,
          dp[i - 1][j - 1] + 1
        );
      }
    }
  }
  return dp[a.length][b.length];
}
```

The distance is computed.

For SQL, use `EDITDIST3` (SQLite extension):
```sql
SELECT * FROM users WHERE EDITDIST3(displayName, ?) <= 2;
```

The edit distance is in the DB.

## The "ranking" pattern

For ranking:
- **Exact match:** Higher rank
- **Prefix match:** Higher than substring
- **Recent:** Boost recent items
- **Popular:** Boost popular items

```ts
function rank(item: any, query: string): number {
  let score = 0;
  const q = query.toLowerCase();
  const name = item.displayName.toLowerCase();

  if (name === q) score += 100;
  if (name.startsWith(q)) score += 50;
  if (name.includes(q)) score += 10;
  if (item.email.toLowerCase().includes(q)) score += 5;

  return score;
}
```

The score is computed.

## The "autocomplete" pattern

For autocomplete:
```ts
const results = await env.DB!.prepare(`
  SELECT * FROM users WHERE displayName LIKE ? LIMIT 10
`).bind(`${query}%`).all();

return Response.json({
  suggestions: results.results.map(u => u.displayName),
});
```

The suggestions are returned.

## The "search observability" pattern

For search observability:
- **Query:** What is the user searching for?
- **Results:** How many?
- **Latency:** How long?
- **CTR:** Did they click?

```ts
logEvent('search.query', 'info', {
  query,
  resultCount: results.length,
  latencyMs: Date.now() - start,
  userId: ctx.user.id,
});
```

The search is monitored.

## The "no-results" pattern

For no results:
- **Empty results:** No items match
- **Suggestions:** "Did you mean..."
- **Related:** Show popular items

```ts
if (results.length === 0) {
  // Suggest similar
  const suggestions = await suggestSimilar(query);
  return Response.json({ data: [], suggestions });
}
```

The empty case is handled.

## The "search performance" pattern

For performance:
- **Index:** FTS5 is already an index
- **Cache:** Cache popular queries
- **Limit:** Limit the result set

```ts
// Cache popular queries
const cacheKey = `search:${query}`;
const cached = await env.KV!.get(cacheKey, 'json');
if (cached) return cached;

const results = await search(query);
await env.KV!.put(cacheKey, JSON.stringify(results), { expirationTtl: 300 });
return results;
```

The search is cached.

## The "multi-field search" pattern

For multi-field, FTS5 with multiple columns:
```ts
const results = await env.DB!.prepare(`
  SELECT u.*, rank
  FROM users u
  JOIN users_fts ON users_fts.rowid = u.rowid
  WHERE users_fts MATCH ?
  ORDER BY rank
  LIMIT 20
`).bind(`displayName:${query} OR email:${query}`).all();
```

The multi-field is searched.

## The "search anti-pattern" anti-patterns

### 1. LIKE on every query
- **Issue:** Slow, no ranking
- **Fix:** Use FTS5

### 2. No ranking
- **Issue:** Random results
- **Fix:** Score + sort

### 3. Case-sensitive
- **Issue:** "alice" doesn't match "Alice"
- **Fix:** Lowercase + FTS5

### 4. No typo tolerance
- **Issue:** "Aliec" doesn't match "Alice"
- **Fix:** Edit distance

### 5. No autocomplete
- **Issue:** User types everything
- **Fix:** Autocomplete

## Verification
- **Test:** Search returns correct results
- **Test:** Ranking is correct
- **Test:** Performance is good (< 100ms)
- **Live:** Search is monitored
- **Audit:** Quarterly review

## Gotchas
- **The "LIKE on every query" anti-pattern.** Use FTS5.
- **The "no ranking" anti-pattern.** Score + sort.
- **The "case-sensitive" anti-pattern.** Lowercase.

## Related
- `search-architecture.md`
- `feature-cookbook-search-ranking.md`
- `feature-cookbook-data-import.md`
- FTS5: https://www.sqlite.org/fts5.html
- ElasticSearch: https://www.elastic.co/
- Algolia: https://www.algolia.com/
