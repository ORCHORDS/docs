# Jsonb Index Gin Operator Class Tradeoffs

## Scope

This article covers indexing decisions for PostgreSQL `jsonb` columns: when to use GIN, which operator class (`jsonb_ops` versus `jsonb_path_ops`) to pick, how `?`/`@>`/`#>`/`@?` operators interact with each, and the trade-offs in write performance, query shape, and selectivity. It addresses the recurring question of why a query like `WHERE data @> '{"tags":["x"]}'` is fast with one operator class and slow or unsupportable with another. It excludes the differences between `json` and `jsonb` storage models, application-side JSON schema enforcement, and search-engine alternatives (Elasticsearch, OpenSearch) for full-text search.

## Workflow or implementation guidance

1. **Decide whether to index at all.** Indexing `jsonb` is expensive on write-heavy tables; a small, mostly-read table or a table whose queries already filter on a different indexed column may not need a `jsonb` index at all. Measure the query workload first; an index that no hot query can use is pure overhead.
2. **Use the default `jsonb_ops` operator class for ad-hoc containment queries.** `CREATE INDEX ... USING GIN (data jsonb_ops)` indexes both keys and values, supporting a wide range of operators: `?` (key exists), `?|` (any of these keys), `?&` (all of these keys), `@>` (contains), and `@?` (JSONPath exists). The flexibility is paid in index size and write cost.
3. **Use `jsonb_path_ops` when the workload is purely `@>` containment.** `jsonb_path_ops` is a smaller, faster index that supports only the `@>` operator; it does not support `?`, `?|`, `?&`, or `@?`. For a workload that asks only "does this JSON document contain this subtree", `jsonb_path_ops` is the right choice and is often a 30-50% smaller index with faster lookup.
4. **Pick the operator class based on the actual queries.** Audit the workload's `WHERE` clauses: if every clause is `@>` containment, prefer `jsonb_path_ops`; if any clause is `?`/`?|`/`?&` (key existence), use `jsonb_ops`. The choice is not a style preference; an unsupported operator against the wrong class results in a planner that falls back to a sequential scan.
5. **Add a `B-tree` index on a generated expression when the workload filters on one specific scalar field inside `jsonb`.** A query like `WHERE (data->>'email') = 'x@y'` can be served by an expression index `CREATE INDEX ... ON users ((data->>'email'))`. This is faster than GIN for equality on a single field and is the canonical answer when one path dominates the workload.
6. **Combine GIN and B-tree when needed.** A common pattern is GIN on the whole `jsonb` for ad-hoc predicates plus a B-tree expression index on the field used for ordering or range filtering. They serve different query shapes; do not pick one and discard the other if both query patterns exist.
7. **Mind the `jsonb_path_ops` containment semantics.** `jsonb_path_ops` requires the right-hand side of `@>` to be the same JSON structure as the indexed value; passing a different structure causes the operator to return false even when human intuition says true. Test the operator against representative queries before declaring the index correct.
8. **Build the index with the appropriate algorithm.** `CREATE INDEX ... USING GIN (data jsonb_ops)` is a single transaction; on large tables, prefer doing it during a maintenance window or using `pg_squeeze`/`pg_repack`-style tools. PostgreSQL 18 added parallel GIN index builds, which can shorten the window significantly.
9. **Set `GIN` fastupdate for write-heavy tables.** `CREATE INDEX ... WITH (fastupdate = on)` (default on) batches pending inserts into the GIN structure; the trade-off is that searches may scan a slightly larger pending list. For write-heavy tables this is usually a win.
10. **Use expression indexes with the same `IMMUTABLE` rules as generated columns.** `data->>'email'` is immutable because it does not consult external state; `data->>'created_at'::timestamptz` is also immutable because `timestamptz` parsing is deterministic. Stick to pure expressions.

## Controls

1. **Operator-class decision recorded.** Each `jsonb` index has a comment or migration annotation naming the operator class and the supported operators; reviewers check that the workload actually uses those operators.
2. **Write-rate measurement.** A baseline benchmark of insert throughput before and after the index is created; a regression beyond a threshold blocks the migration.
3. **Operator usage audit.** A periodic query against `pg_stat_user_indexes` and `pg_stat_statements` showing whether the index is being used; unused indexes are candidates for removal.
4. **`fastupdate` policy.** A documented setting for `fastupdate` based on the workload; reviewed against query latency after any change.
5. **Generated-expression immutability check.** Migration linter that rejects non-immutable expressions on generated-index paths.
6. **GIN list-size observability.** A dashboard tracking GIN pending-list size, with alerts on runaway values that indicate an unhealthy `fastupdate` balance.

## Validation evidence

1. **Operator-class correctness test.** Run the application's hot queries with each operator class enabled, assert the index is selected (`EXPLAIN` shows `Bitmap Index Scan on ...`), and time the queries. Discard the operator class whose queries fall back to seq scan.
2. **Workload replay.** Replay a production-shaped workload and confirm both write throughput and query latency match the predicted trade-off. If write throughput dropped more than expected, reconsider the operator class.
3. **Stale fastupdate test.** Insert rapidly without vacuuming the GIN, then run a query; assert results are correct (GIN pending list does not lose entries) and latency degrades within tolerance.
4. **`jsonb_path_ops` containment test.** For each `@>` query, confirm that the right-hand side structure matches the indexed shape; a small set of representative payloads suffices.
5. **Combined-index test.** Verify that queries combining `data @> ...` and an ordering on `(data->>'created_at')::timestamptz` use both the GIN and the B-tree expression index in the right plan.

## Failure modes and correction

1. **Wrong operator class for the workload.** Symptom: `EXPLAIN` shows `Bitmap Heap Scan` with a sequential scan fallback because the operator is unsupported. Correction: drop the index and recreate with the correct operator class; choose `jsonb_ops` for key-existence queries and `jsonb_path_ops` for `@>`-only.
2. **Index bloat from heavy updates.** Symptom: index size grows faster than table size, query latency drifts up. Correction: schedule `VACUUM` of the table and consider disabling `fastupdate` for steady-state, or partition the table so old `jsonb` rows live in rarely-indexed partitions.
3. **GIN pending list grows unbounded.** Symptom: query latency rises sharply after a write burst, then drops after autovacuum. Correction: tune `gin_pending_list_limit` and ensure autovacuum runs frequently enough; consider disabling `fastupdate` on tables whose update pattern never benefits from batching.
4. **`jsonb_path_ops` returns false for a query the application believes should match.** Symptom: queries that worked with `jsonb_ops` return no rows after switching. Correction: check the right-hand-side structure; in many cases the difference is array-vs-object ordering or key order, which `jsonb_ops` normalises and `jsonb_path_ops` is stricter about.
5. **A scalar field inside `jsonb` becomes the dominant query target, but the planner still uses GIN.** Symptom: an equality on `data->>'email'` is slow because the GIN matches more broadly than necessary. Correction: add the expression index, and confirm with `EXPLAIN` that the planner picks it.
6. **Application passes `jsonb` from user input that triggers expression-immutability edge cases.** Symptom: queries fail with errors. Correction: validate the input at the application boundary and store normalised `jsonb`; the index then operates on the canonical form.

## Limitations

1. **GIN indexes do not accelerate ordering or range queries on `jsonb` paths directly;** an expression B-tree is required for those access patterns.
2. **`jsonb_path_ops` is more restrictive than `jsonb_ops`;** it is the wrong choice for queries that ask about specific keys or use JSONPath existence.
3. **`jsonb` is slower to write than `text`;** every write must parse the JSON, regardless of indexes. The choice of `jsonb` is justified by query flexibility, not by write efficiency.
4. **GIN indexes are not unique;** uniqueness constraints cannot be built on a `jsonb` GIN. Use partial unique indexes or a generated scalar column.
5. **JSONPath expressions (`@?`/`@@`) have planner coverage that varies by version;** some complex paths will not use the index even when logically supported. Test with `EXPLAIN` rather than assume.

## Canonical sources

- PostgreSQL Documentation, JSON Types and JSON Functions: https://www.postgresql.org/docs/current/datatype-json.html
- PostgreSQL Documentation, Built-in GIN Operator Classes (jsonb): https://www.postgresql.org/docs/current/gin-builtin-opclasses.html
- PostgreSQL Documentation, GIN Indexes: https://www.postgresql.org/docs/current/gin.html