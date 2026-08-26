# feature-search-detail

**Issue:** Search implementation — full-text, faceted, ranking
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your users want to search. You write `SELECT * FROM users
WHERE name LIKE '%alice%'`. It's slow. You add an index.
It's still slow. You add a full-text index. It's faster.
You want faceted search (filter by status, role, etc.). It
gets complex.

## Root cause
**Search is a feature, not a query.** For real search, use a
search engine.

**Source:** Algolia docs:
https://www.algolia.com/doc/

## The "search level" decision

### Level 1: SQL LIKE
- **What:** `WHERE name LIKE '%alice%'`
- **Pros:** Simple
- **Cons:** Slow; no ranking; no facets; case-sensitive (in
  some DBs)

```ts
const users = await env.DB!.prepare(
  `SELECT * FROM users WHERE display_name LIKE ? AND tenant_id = ?`
).bind(`%${query}%`, ctx.tenant.id).all<User>();
```

### Level 2: SQL FTS (Full-Text Search)
- **What:** `WHERE MATCH(display_name) AGAINST (?)`
- **Pros:** Faster; better ranking; case-insensitive
- **Cons:** Setup; SQL-specific syntax

```sql
-- D1 / SQLite FTS5
CREATE VIRTUAL TABLE users_fts USING fts5(
  display_name,
  email,
  content='users',
  content_rowid='rowid'
);
```

### Level 3: Search engine
- **What:** Algolia, Meilisearch, Elasticsearch
- **Pros:** Fast; faceted; ranking; typo tolerance; more
- **Cons:** Another service to operate (or pay for)

## The "FTS5" pattern (D1)

```sql
-- Create the FTS5 virtual table
CREATE VIRTUAL TABLE users_fts USING fts5(
  display_name,
  email,
  content='users',
  content_rowid='rowid'
);

-- Triggers to keep FTS in sync
CREATE TRIGGER users_fts_insert AFTER INSERT ON users BEGIN
  INSERT INTO users_fts(rowid, display_name, email) VALUES (new.rowid, new.display_name, new.email);
END;
CREATE TRIGGER users_fts_delete AFTER DELETE ON users BEGIN
  INSERT INTO users_fts(users_fts, rowid, display_name, email) VALUES('delete', old.rowid, old.display_name, old.email);
END;
CREATE TRIGGER users_fts_update AFTER UPDATE ON users BEGIN
  INSERT INTO users_fts(users_fts, rowid, display_name, email) VALUES('delete', old.rowid, old.display_name, old.email);
  INSERT INTO users_fts(rowid, display_name, email) VALUES (new.rowid, new.display_name, new.email);
END;

-- Search
SELECT u.* FROM users u
JOIN users_fts f ON u.rowid = f.rowid
WHERE users_fts MATCH ? AND u.tenant_id = ?
ORDER BY rank
LIMIT 20;
```

The FTS5 index is fast; the trigger keeps it in sync.

## The "Algolia" pattern

For a managed search:
```ts
import algoliasearch from 'algoliasearch';

const client = algoliasearch(env.ALGOLIA_APP_ID, env.ALGOLIA_API_KEY);
const index = client.initIndex('users');

await index.saveObject({
  objectID: user.id,
  displayName: user.displayName,
  email: user.email,
  tenantId: user.tenantId,
  _tags: [user.tenantId, user.role],  // For faceting
});

const results = await index.search(query, {
  filters: `tenantId:${ctx.tenant.id}`,
  facets: ['role', 'status'],
  hitsPerPage: 20,
});
```

Algolia handles ranking, facets, typo tolerance, more.

## The "Meilisearch" pattern

For an open-source self-hosted search:
```ts
const meili = new MeiliSearch({ host: env.MEILI_URL, apiKey: env.MEILI_KEY });
const index = meili.index('users');

await index.addDocuments([
  { id: 'u_1', displayName: 'Alice', email: 'a@x.test', tenantId: 't_1' },
]);

const results = await index.search(query, {
  filter: `tenantId = ${ctx.tenant.id}`,
  facets: ['role', 'status'],
  limit: 20,
});
```

Meilisearch is open source, fast, easy to self-host.

## The "faceted search" pattern

For filters (role, status, plan):
```ts
// D1 FTS5 with manual facets
const roleCounts = await env.DB!.prepare(
  `SELECT role, COUNT(*) AS count FROM users WHERE tenant_id = ? GROUP BY role`
).bind(ctx.tenant.id).all<{ role: string; count: number }>();

// Algolia / Meilisearch: built-in facets
const results = await index.search(query, {
  facets: ['role', 'status'],
});
// results.facets: { role: { admin: 10, viewer: 50 }, status: { active: 60 } }
```

Facets show counts per value; the UI can show checkboxes.

## The "typo tolerance" pattern

For "aliase" matching "alice":
- **SQL FTS5:** No typo tolerance (exact match)
- **Algolia:** Built-in (configurable threshold)
- **Meilisearch:** Built-in (configurable)

```ts
// Algolia: typo tolerance
const results = await index.search(query, {
  typoTolerance: true,
  minWordSizefor1Typo: 4,
  minWordSizefor2Typos: 8,
});
```

## The "search ranking" pattern

For ranking by relevance + recency:
- **TF-IDF:** Term frequency × inverse document frequency
- **BM25:** Modern ranking algorithm (FTS5 default)
- **Custom:** Boost by recency, popularity, etc.

```ts
// Algolia: custom ranking
await index.setSettings({
  customRanking: ['desc(createdAt)', 'desc(loginCount)'],
});
```

## The "search highlighting" pattern

For highlighting the match:
```ts
// Algolia: built-in
const results = await index.search(query, {
  attributesToHighlight: ['displayName', 'email'],
});
// results.hits[0]._highlightResult: { displayName: { value: '<em>Ali</em>ce' } }

// FTS5: snippet function
SELECT snippet(users_fts, 0, '<mark>', '</mark>', '...', 32) FROM users_fts WHERE users_fts MATCH ?;
```

## The "search performance" pattern

For performance:
- **Index:** Use FTS or a search engine
- **Limit:** Don't return more than 20 results per page
- **Cache:** Cache common queries
- **Async:** Run search in a worker; return when ready

## The "search as you type" pattern

For instant search (debounced):
```ts
// Frontend
const [query, setQuery] = useState('');
const { data } = useQuery({
  queryKey: ['search', query],
  queryFn: () => fetch(`/api/search?q=${query}`).then(r => r.json()),
  enabled: query.length >= 2,
});
```

Debounce the query to avoid flooding the server.

## The "search index sync" pattern

For keeping the search index in sync:
```ts
// On every write
async function onUserChange(user: User, env: Env): Promise<void> {
  await env.DB!.prepare(`INSERT OR REPLACE INTO users ...`).bind(...).run();

  // Update the search index
  await searchIndex.saveObject({
    objectID: user.id,
    displayName: user.displayName,
    email: user.email,
    tenantId: user.tenantId,
  });
}
```

The index is updated on every change.

## The "search at scale" pattern

For very large datasets (1M+ records):
- **Partition:** One index per tenant
- **Sharding:** Multiple search engines
- **Async indexing:** Index async, not on the write path

## Verification
- **Test:** Search returns the right results
- **Test:** Search is fast (< 100ms p99)
- **Live:** Search usage is monitored
- **Audit:** Quarterly review of search quality

## Gotchas
- **The "SQL LIKE for search" anti-pattern.** Slow, no
  ranking, no facets. Use FTS or a search engine.
- **The "search without index sync" anti-pattern.** The
  index must be in sync; otherwise users find stale data.
- **The "search that returns too much" anti-pattern.** A
  search that returns 10k results is a bug. Use pagination.
- **The "search without facets" anti-pattern.** Users want
  to filter; facets are essential.
- **The "search without typo tolerance" anti-pattern.**
  Users make typos; the search must handle them.
- **The "search without ranking" anti-pattern.** A search
  that returns in arbitrary order is bad. Use ranking.

## Related
- `search-architecture.md`
- `feature-observability-pattern.md`
- `pagination-patterns.md`
- `cache-strategies.md`
- `caching-strategies-detail.md`
- Algolia: https://www.algolia.com/
- Meilisearch: https://www.meilisearch.com/
- SQLite FTS5: https://www.sqlite.org/fts5.html
