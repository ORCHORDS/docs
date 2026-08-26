# d1-json-column-patterns

**Date:** 2026-08-22
**Author:** example.com
**Status:** documented

## Symptom

example project Worker routes need to store heterogeneous metadata alongside
structured rows—anonymous post extras, community settings, per-user
notification preferences—without adding a column for every possible
field. Naive approaches either bloat the schema with nullable columns
or require a separate key-value sidecar table that adds a join on every
read.

## Context

SQLite ships the JSON1 extension by default, and Cloudflare D1 exposes
it in full. Columns typed as `TEXT` or `BLOB` can hold JSON strings that
SQLite functions (`json_extract`, `json_patch`, `json_set`,
`json_insert`, `json_remove`, `json_each`, `json_type`) operate on at
query time. No extension pragma is required—JSON1 is always available in
D1.

Two design philosophies apply:

- **Schema-on-write**: the JSON stored must conform to a shape validated
  before insert (application layer or a CHECK constraint with
  `json_valid()`). Querying is predictable; the risk is stale documents
  with old shapes.
- **Schema-on-read**: any valid JSON is accepted; the application
  interprets the shape at read time. Flexible for evolving fields but
  requires defensive null checks everywhere.

example project uses a hybrid: `schema-on-write` for the envelope (required
top-level keys), `schema-on-read` for the nested `extras` sub-object
that carries optional display metadata.

## JSON Column Declaration

```sql
CREATE TABLE posts (
  id          TEXT    PRIMARY KEY,
  body        TEXT    NOT NULL,
  community_id TEXT   NOT NULL REFERENCES communities(id),
  created_at  INTEGER NOT NULL,
  -- schema-on-write: require valid JSON, minimum keys enforced by app
  metadata    TEXT    NOT NULL DEFAULT '{}' CHECK (json_valid(metadata))
);
```

`json_valid()` in a CHECK constraint rejects malformed JSON at write
time with no application code needed. The cost is negligible (<0.1 ms
per row on D1).

## json_extract — Point Reads

```typescript
// Read one JSON field without fetching the full column.
const stmt = env.DB.prepare(`
  SELECT id, body,
         json_extract(metadata, '$.pinned')   AS pinned,
         json_extract(metadata, '$.author_tag') AS author_tag
  FROM   posts
  WHERE  community_id = ?
  ORDER  BY created_at DESC
  LIMIT  25
`).bind(communityId);

const { results } = await stmt.all<PostRow>();
```

`json_extract` paths use RFC 6901-style dot notation prefixed with `$`.
Arrays use `$[0]`, `$[1]`, etc. Returns SQL NULL when the path is
absent—safe to coerce in TypeScript with `?? defaultValue`.

## json_patch — Partial Updates

`json_patch(base, patch)` applies a JSON Merge Patch (RFC 7396) to the
stored document. Use it to update one key without overwriting the entire
column, which avoids read-modify-write races on concurrent Workers.

```typescript
async function setPinned(
  postId: string,
  pinned: boolean,
  env: Env
): Promise<void> {
  await env.DB.prepare(`
    UPDATE posts
    SET    metadata = json_patch(metadata, json(?))
    WHERE  id = ?
  `).bind(JSON.stringify({ pinned }), postId).run();
}
```

`json_patch` sets a key to the patch value or, when the patch value is
SQL NULL (not JSON `null`), removes the key. To explicitly set a key to
JSON `null`, use `json_set` instead.

## json_set / json_remove for Surgical Edits

```sql
-- Append a tag without touching other keys:
UPDATE posts
SET    metadata = json_set(metadata, '$.tags', json(?))
WHERE  id = ?;

-- Remove a deprecated field during a lazy migration:
UPDATE posts
SET    metadata = json_remove(metadata, '$.legacy_score')
WHERE  json_extract(metadata, '$.legacy_score') IS NOT NULL
LIMIT  500;
```

The `LIMIT 500` lazy migration pattern avoids a table-scan lock on
large example project community tables during peak traffic.

## json_each — Shredding Arrays

```sql
-- Expand a JSON array column into rows for aggregation.
SELECT p.id, j.value AS tag, COUNT(*) AS usage
FROM   posts p, json_each(json_extract(p.metadata, '$.tags')) j
WHERE  p.community_id = ?
GROUP  BY j.value
ORDER  BY usage DESC
LIMIT  10;
```

`json_each` is a table-valued function that returns one row per element.
Performance degrades with large arrays (>100 elements per row) because
each call re-parses the JSON string. Cache aggregated results in a
derived column or a separate summary table if this runs frequently.

## Partial Index on JSON Field

D1 supports generated/expression indexes on `json_extract`:

```sql
CREATE INDEX idx_posts_pinned
  ON posts (community_id, created_at)
  WHERE json_extract(metadata, '$.pinned') = 1;
```

This covers the "pinned posts in a community" query with a tiny index
that only stores rows where `pinned` is true. Use it when a JSON boolean
flag drives a common filter.

## Mobile vs Desktop Payload Considerations

| Concern                  | Mobile strategy                              | Desktop strategy                          |
|--------------------------|----------------------------------------------|-------------------------------------------|
| Metadata column size     | Strip optional keys before API response      | Return full metadata, let client filter   |
| JSON serialisation cost  | Avoid `json_each` shredding per request      | Shredding acceptable for analytics views  |
| Partial update round-trip | Use `json_patch` to send only changed keys  | Full document PUT acceptable              |
| Bandwidth of full column | Project only needed `json_extract` paths     | SELECT metadata OK for admin dashboards   |

Keep the `metadata` column below 4 KB per row for mobile paths. Anything
larger should move to a dedicated BLOB table or Cloudflare R2.

## Schema-on-Read vs Schema-on-Write Summary

| Dimension          | Schema-on-write                              | Schema-on-read                           |
|--------------------|----------------------------------------------|------------------------------------------|
| Validation point   | INSERT / UPDATE (CHECK + app)                | Application read path                   |
| Migration cost     | Backfill when shape changes                  | Handle both old and new shape in code   |
| Query safety       | `json_extract` paths always exist            | Must guard every extract with `IS NOT NULL` |
| D1 fit             | Recommended for required envelope keys       | Acceptable for optional `extras` sub-objects |

## Anti-Patterns

- Storing entire relational entities inside a JSON column to avoid joins.
  JSON columns are for schemaless extensions; core foreign-key data
  belongs in normalized columns.
- Using `json_extract` in a WHERE clause without an expression index—
  causes full table scans on every filter.
- Relying on key order inside JSON for business logic; SQLite's JSON1
  does not guarantee insertion order on all paths.
- Exceeding 4 KB metadata per row on mobile-facing routes—D1 returns
  full column values; there is no server-side field projection.
- Using `json_patch` with a JSON Merge Patch that contains keys set to
  `null` expecting them to be removed; RFC 7396 removes keys whose patch
  value is `null`, but the D1 binding must pass SQL `NULL`, not the
  JSON string `"null"`.

## Gotchas

- `json_valid()` in a CHECK constraint does not distinguish between
  `{}`, `[]`, or a bare string like `"hello"`. All are valid JSON.
  Add a tighter CHECK if object structure is required:
  `CHECK (json_type(metadata) = 'object')`.
- `json_patch` merges shallowly; nested objects are replaced wholesale,
  not merged recursively. Use `json_set` for deep-path updates.
- D1's SQLite version does not support the `->` / `->>` JSON operators
  added in SQLite 3.38. Use `json_extract()` function syntax instead.
- Wrangler's local dev SQLite version may differ from D1's production
  version—always test JSON queries against a live D1 branch, not only
  locally.
- `json_each` is not supported in a `WHERE` clause directly; use a
  subquery or CTE to shred and then filter.

## Verification

```bash
# Confirm JSON1 is available in D1:
wrangler d1 execute example project_DB --command \
  "SELECT json_extract('{\"ok\":true}', '$.ok');"
# Expected: 1

# Test json_patch update in the branch DB:
wrangler d1 execute example project_DB --command \
  "UPDATE posts SET metadata = json_patch(metadata, '{\"pinned\":1}')
   WHERE id = 'test-id' RETURNING json_extract(metadata,'$.pinned');"

# Verify CHECK constraint rejects bad JSON:
wrangler d1 execute example project_DB --command \
  "INSERT INTO posts (id, body, community_id, created_at, metadata)
   VALUES ('bad', 'text', 'c1', 0, 'NOT_JSON');"
# Expected: CHECK constraint failed
```

## Related

- `database/d1-sqlite-query-optimization.md`
- `database/d1-foreign-keys-referential-integrity.md`
- `database/json-columns-patterns.md`
- `database/partial-indexes.md`
- `database/d1-batch-operations-performance.md`

## Sources

- https://www.sqlite.org/json1.html
- https://developers.cloudflare.com/d1/sql-api/sql-statements/
- https://developers.cloudflare.com/d1/build-databases/use-d1/
- https://www.rfc-editor.org/rfc/rfc7396 (JSON Merge Patch)
