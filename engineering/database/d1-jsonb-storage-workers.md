# D1 JSONB Storage in Workers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project / example.com stores variable-shape payloads — user profile metadata, post reactions,
notification bodies, and moderation audit entries — alongside structured relational columns.
Encoding these as TEXT-serialized JSON strings forces every read to parse JSON in the Worker
process. SQLite 3.45 (shipped with D1 in 2024) introduced the native `JSONB` binary format,
which is stored as a BLOB and parsed once inside the SQLite engine, reducing per-row overhead.

## Context

Cloudflare D1 runs a recent SQLite build that includes the `jsonb()` family of functions
(`jsonb()`, `json()`, `jsonb_extract()`, `jsonb_object()`, `jsonb_array()`). JSONB is an
internal binary encoding of JSON that SQLite stores as a BLOB column and operates on without
re-parsing text. Workers read JSONB columns as `ArrayBuffer` via D1's JS binding; use
`json()` in the SELECT list to convert back to a text string the Worker can `JSON.parse()`.

## Schema — BLOB Column for JSONB

Declare a `BLOB` (or `ANY`) affinity column to store the binary JSONB value. Wrap INSERT
values with `jsonb(?)` to convert text JSON into the binary format at write time.

```sql
CREATE TABLE posts (
  id         INTEGER PRIMARY KEY,
  author_id  INTEGER NOT NULL,
  body       TEXT    NOT NULL,
  metadata   BLOB,                        -- stores JSONB binary
  created_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX idx_posts_author ON posts(author_id, created_at DESC);
```

Insert with `jsonb()` conversion:

```sql
INSERT INTO posts(author_id, body, metadata)
VALUES (
  ?1,
  ?2,
  jsonb(?3)   -- converts '{"tags":["rant"],"sensitive":false}' to BLOB
);
```

## Read and Write Patterns in TypeScript

```typescript
export interface Env {
  DB: D1Database;
}

interface PostMeta {
  tags: string[];
  sensitive: boolean;
  location?: string;
}

interface PostRow {
  id: number;
  author_id: number;
  body: string;
  metadata: string;   // returned as JSON text via json() in SELECT
  created_at: number;
}

// Write: pass JSON string; let D1/SQLite convert to JSONB binary
export async function createPost(
  env: Env,
  authorId: number,
  body: string,
  meta: PostMeta
): Promise<number> {
  const { meta: result } = await env.DB.prepare(`
    INSERT INTO posts(author_id, body, metadata)
    VALUES (?1, ?2, jsonb(?3))
    RETURNING id
  `)
    .bind(authorId, body, JSON.stringify(meta))
    .first<{ id: number }>();
  return result!.id;
}

// Read: use json() to convert BLOB back to text string
export async function getPost(env: Env, id: number): Promise<PostRow | null> {
  return env.DB.prepare(`
    SELECT id, author_id, body, json(metadata) AS metadata, created_at
    FROM   posts
    WHERE  id = ?1
  `)
    .bind(id)
    .first<PostRow>();
}

// Parse metadata in the Worker after retrieval
export async function getPostWithMeta(env: Env, id: number) {
  const row = await getPost(env, id);
  if (!row) return null;
  return {
    ...row,
    metadata: JSON.parse(row.metadata) as PostMeta,
  };
}
```

## Querying JSONB Fields with jsonb_extract

`jsonb_extract()` operates on BLOB columns without converting to text first, making field-level
filtering faster than `json_extract()` on a TEXT column.

```sql
-- Filter posts tagged 'rant'
SELECT id, body, json(metadata) AS metadata
FROM   posts
WHERE  jsonb_extract(metadata, '$.tags[0]') = 'rant'
   OR  EXISTS (
         SELECT 1
         FROM   json_each(metadata, '$.tags')
         WHERE  value = 'rant'
       );
```

Expression index over a JSONB field for high-cardinality extractions:

```sql
-- Index the 'sensitive' boolean extracted from JSONB
CREATE INDEX idx_posts_sensitive
  ON posts(jsonb_extract(metadata, '$.sensitive'))
  WHERE metadata IS NOT NULL;
```

```typescript
export async function getSensitivePosts(env: Env): Promise<PostRow[]> {
  const { results } = await env.DB.prepare(`
    SELECT id, author_id, body, json(metadata) AS metadata, created_at
    FROM   posts
    WHERE  jsonb_extract(metadata, '$.sensitive') = true
    ORDER  BY created_at DESC
    LIMIT  50
  `).all<PostRow>();
  return results;
}
```

## Partial Updates with jsonb_patch

`jsonb_patch()` implements RFC 7396 JSON Merge Patch over BLOB columns, letting Workers update
individual fields without reading and rewriting the entire JSON object.

```sql
-- Merge-patch: sets location, leaves other keys intact
UPDATE posts
SET    metadata = jsonb_patch(metadata, jsonb(?1))
WHERE  id = ?2;
```

```typescript
export async function patchPostMeta(
  env: Env,
  postId: number,
  patch: Partial<PostMeta>
): Promise<void> {
  await env.DB.prepare(`
    UPDATE posts
    SET    metadata = jsonb_patch(metadata, jsonb(?1))
    WHERE  id = ?2
  `)
    .bind(JSON.stringify(patch), postId)
    .run();
}
```

## Anti-patterns

- Storing JSONB as TEXT affinity — `json()` and `jsonb()` functions work, but binary BLOB storage is lost; always use `BLOB` or `ANY` affinity
- Calling `JSON.parse()` on a column before confirming the SELECT list used `json()` — D1 returns JSONB BLOBs as `ArrayBuffer`, not strings
- Using `json_extract()` (text-based) when `jsonb_extract()` is available — the text variant re-parses on every row
- Building WHERE filters entirely in the Worker after a full-table SELECT — move predicates into SQL using `jsonb_extract()`

## Gotchas

- `jsonb()` returns `NULL` if the input string is not valid JSON — validate in the Worker before binding
- `json(metadata)` in the SELECT list returns `NULL` for `NULL` BLOB values; always handle null metadata in TypeScript
- Expression indexes on `jsonb_extract()` are not used when the SELECT-list conversion wraps the column in `json()` — write the WHERE clause using `jsonb_extract()` directly
- D1's `first<T>()` and `all<T>()` return the `json()` column as a plain `string`; do not cast to `ArrayBuffer` in the TypeScript interface

## Verification

```typescript
// Round-trip test
const id = await createPost(env, 1, 'hello', { tags: ['test'], sensitive: false });
const post = await getPostWithMeta(env, id);
console.assert(post !== null);
console.assert(post!.metadata.tags[0] === 'test');
console.assert(post!.metadata.sensitive === false);

// Patch test
await patchPostMeta(env, id, { sensitive: true });
const updated = await getPostWithMeta(env, id);
console.assert(updated!.metadata.sensitive === true);
console.assert(updated!.metadata.tags[0] === 'test', 'Patch must preserve tags');
```

## Related

- `/documentation/categories/database/d1-json-column-patterns.md`
- `/documentation/categories/database/d1-json-columns-partial-indexes.md`
- `/documentation/categories/database/d1-json-patch-partial-update-workers.md`
- `/documentation/categories/database/d1-json-aggregation-analytics.md`

## Sources

- https://developers.cloudflare.com/d1/
- https://www.sqlite.org/jsonb.html
- https://www.sqlite.org/json1.html
- https://developers.cloudflare.com/d1/build-with-d1/d1-client-api/
