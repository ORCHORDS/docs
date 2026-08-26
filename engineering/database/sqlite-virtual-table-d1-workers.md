# SQLite Virtual Tables in D1 Workers

- Date: 2026-08-22
- Author: example.com
- Status: production

## Using SQLite virtual table extensions available inside D1

D1 runs SQLite under the hood but exposes only a subset of extensions. Understanding
which virtual tables are available — and how they behave on D1's edge infrastructure —
lets you write queries that would otherwise require a separate search index or geospatial
service.

## Context

D1 bundles SQLite's built-in extensions: `json1`, `fts5`, and `rtree`. User-defined
virtual tables via `CREATE VIRTUAL TABLE ... USING <module>` are restricted to these
bundled modules. You cannot load external `.so` modules. This article covers the three
available virtual table families and their practical patterns inside Workers.

## JSON1 Virtual Table: `json_each` and `json_tree`

`json_each` and `json_tree` are table-valued functions exposed by the `json1` extension.
They are not persistent virtual tables but behave like inline views over a JSON value.

```sql
-- Unnest a JSON array column into individual rows.
-- Table: products(id, tags TEXT)  -- tags = '["electronics","sale","refurbished"]'
SELECT p.id, j.value AS tag
FROM products AS p, json_each(p.tags) AS j
WHERE j.value = 'sale';
```

```sql
-- Aggregate all tags across all products (flat unique list).
SELECT DISTINCT j.value AS tag
FROM products AS p, json_each(p.tags) AS j
ORDER BY tag;
```

```sql
-- json_tree for deeply nested JSON; extract every key named "price".
SELECT t.fullkey, t.value
FROM orders AS o, json_tree(o.data) AS t
WHERE t.key = 'price' AND t.type = 'real';
```

```typescript
// Workers: query unnested tags with a binding parameter.
export async function getProductsByTag(db: D1Database, tag: string) {
  return db
    .prepare(
      `SELECT p.id, p.name
       FROM products AS p, json_each(p.tags) AS j
       WHERE j.value = ?`,
    )
    .bind(tag)
    .all<{ id: string; name: string }>();
}
```

Performance note: `json_each` on a JSON array column is computed at query time for each
row scanned. Without a supporting index on the column, this is O(n × array_length).
For high-cardinality tag searches create a partial index or materialise tags into a
junction table.

## FTS5 Full-Text Search Virtual Table

```sql
-- Create the FTS5 virtual table (covered in d1-full-text-search-fts5.md).
CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts
USING fts5(title, body, content='documents', content_rowid='rowid');

-- Populate.
INSERT INTO docs_fts(docs_fts) VALUES('rebuild');
```

```sql
-- BM25-ranked phrase search.
SELECT d.id, d.title, bm25(docs_fts) AS rank
FROM docs_fts
JOIN documents AS d ON d.rowid = docs_fts.rowid
WHERE docs_fts MATCH 'workers AND deploy'
ORDER BY rank
LIMIT 10;
```

## RTree Spatial Indexing

`rtree` enables efficient minimum bounding rectangle queries. In D1 it is useful for
proximity search when you do not need full PostGIS capabilities.

```sql
-- Four-column rtree: id, min_lon, max_lon, min_lat, max_lat.
CREATE VIRTUAL TABLE IF NOT EXISTS locations_idx
USING rtree(id, min_lon, max_lon, min_lat, max_lat);

-- Auxiliary data lives in a regular table joined at query time.
CREATE TABLE IF NOT EXISTS locations (
  id      INTEGER PRIMARY KEY,
  name    TEXT NOT NULL,
  lon     REAL NOT NULL,
  lat     REAL NOT NULL
);

-- Insert a point location (bounding box is the point itself).
INSERT INTO locations (id, name, lon, lat) VALUES (1, 'Eiffel Tower', 2.2945, 48.8584);
INSERT INTO locations_idx (id, min_lon, max_lon, min_lat, max_lat)
VALUES (1, 2.2945, 2.2945, 48.8584, 48.8584);
```

```typescript
// Bounding-box proximity query from a Worker.
export async function findNearby(
  db: D1Database,
  lon: number,
  lat: number,
  deltaLon: number,
  deltaLat: number,
) {
  return db
    .prepare(
      `SELECT l.id, l.name, l.lon, l.lat
       FROM locations_idx AS idx
       JOIN locations AS l ON l.id = idx.id
       WHERE idx.min_lon >= ? AND idx.max_lon <= ?
         AND idx.min_lat >= ? AND idx.max_lat <= ?`,
    )
    .bind(lon - deltaLon, lon + deltaLon, lat - deltaLat, lat + deltaLat)
    .all<{ id: number; name: string; lon: number; lat: number }>();
}
```

RTree bounding-box queries have O(log n + k) complexity (k = results), versus O(n) for a
sequential scan with `WHERE lat BETWEEN ? AND ?`.

## Performance Characteristics vs Regular Tables

| Feature              | Regular index (B-tree)      | json_each             | rtree                      | fts5                      |
|----------------------|-----------------------------|-----------------------|----------------------------|---------------------------|
| Storage overhead     | Low                         | None (computed)       | Separate virtual table     | Separate virtual table    |
| Write cost           | Low                         | None                  | Separate INSERT required   | Trigger or manual rebuild |
| Point lookup         | O(log n)                    | O(n)                  | O(log n)                   | N/A                       |
| Range / proximity    | O(log n + k)                | O(n)                  | O(log n + k)               | N/A                       |
| Full-text rank       | Not supported               | Not supported         | Not supported              | BM25 built-in             |
| D1 support confirmed | Yes                         | Yes                   | Yes                        | Yes                       |

Prefer `json_each` when the JSON array is small (< 20 elements) and queried infrequently.
For write-heavy workloads with frequent array searches, normalise to a junction table with
a conventional index.

## json_each for Array Unnesting: Advanced Patterns

```sql
-- Count how many products carry each tag.
SELECT j.value AS tag, COUNT(*) AS cnt
FROM products, json_each(products.tags) AS j
GROUP BY j.value
ORDER BY cnt DESC
LIMIT 10;
```

```sql
-- Filter products that carry ALL of a set of required tags (set intersection).
SELECT id, name
FROM products
WHERE (
  SELECT COUNT(DISTINCT j.value)
  FROM json_each(products.tags) AS j
  WHERE j.value IN ('sale', 'electronics')
) = 2;
```

## Anti-patterns

- Calling `INSERT INTO fts5_table(...)` for each document inside a loop — use
  `db.batch()` to coalesce writes or `INSERT INTO fts(fts) VALUES('rebuild')` after a
  bulk load.
- Forgetting to insert into both `locations` and `locations_idx` — they are independent
  tables; no triggers keep them in sync on D1 (triggers exist but firing on virtual
  tables requires a real table trigger with a manual `INSERT INTO ... _idx`).
- Using `rtree` with floating-point lon/lat at precision > 7 decimal places — rtree uses
  32-bit floats internally; store higher-precision data in the join table.
- Treating `json_tree` like a full recursive descent in SQL — it walks the full document;
  use `json_extract` for known paths instead.

## Gotchas

- D1 does not allow `CREATE VIRTUAL TABLE USING <module>` for anything other than `fts5`,
  `rtree`, and `json1` table-valued functions. Attempting `spellfix1` or `csv` returns
  `no such module`.
- FTS5 content tables (`content='documents'`) require a manual `INSERT INTO fts(fts)
  VALUES('rebuild')` after bulk inserts; D1 does not auto-trigger FTS updates unless you
  add SQLite triggers explicitly.
- RTree `id` must be a 64-bit integer, not TEXT. Use SQLite's `ROWID` or a separate
  integer primary key.
- `json_each` with a `NULL` column returns zero rows (not an error), which can silently
  exclude rows from results.

## Verification

```sql
-- Confirm rtree module is available.
SELECT * FROM pragma_module_list() WHERE name = 'rtree';

-- Confirm fts5 module is available.
SELECT * FROM pragma_module_list() WHERE name = 'fts5';

-- Quick json_each smoke test.
SELECT j.value FROM json_each('["a","b","c"]') AS j;
-- Expected: a, b, c
```

## Related

- `d1-full-text-search-fts5.md`
- `d1-json-columns-partial-indexes.md`
- `d1-spatial-geo-search.md`
- `sqlite-d1-patterns.md`

## Sources

- SQLite JSON1 extension — https://www.sqlite.org/json1.html
- SQLite FTS5 — https://www.sqlite.org/fts5.html
- SQLite RTree — https://www.sqlite.org/rtree.html
- Cloudflare D1 supported SQLite features — https://developers.cloudflare.com/d1/reference/sqlite-compatibility/
