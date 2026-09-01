# Covering Index Index Only Scan Explain Plan

## Scope

This article covers the relationship between covering indexes (a B-tree index whose `INCLUDE` columns carry every column the query needs) and the index-only scan plan node that PostgreSQL chooses when the visibility map cooperates. It explains why `EXPLAIN ANALYZE` reports `Index Only Scan` and what it tells you about heap visibility, the role of the visibility map and `VACUUM` in enabling the optimization, and the steps to confirm an index-only scan is really firing rather than falling back to a heap fetch. It excludes non-B-tree access methods, server-side plan cache effects, and execution-time factors that masquerade as planning problems.

## Workflow or implementation guidance

1. **Define the covering index for the specific query.** The columns referenced in the `WHERE`, `JOIN`, and `SELECT` lists must all be available without a heap visit. The natural-leading-key columns drive selectivity; the `INCLUDE` columns carry the payload. A common shape is `CREATE INDEX ... ON table (key_col) INCLUDE (col_a, col_b, col_c)`, with `key_col` first because leading B-tree columns still drive range scans.
2. **Choose `INCLUDE` rather than concatenating to the key.** Columns in the key list participate in the B-tree ordering, while `INCLUDE` columns live in leaf pages only and never affect ordering or uniqueness. Putting a payload column into the key list breaks ordering and bloats the index for no benefit; `INCLUDE` is the correct tool for "fetch without heap visit".
3. **Read `EXPLAIN ANALYZE` carefully.** A node labelled `Index Only Scan` is necessary but not sufficient: the `actual rows` and the presence of any `Heap Fetches:` sub-count indicate whether the visibility map allowed the no-fetch path. Look for `Heap Fetches: 0` in the output; non-zero fetches mean the planner still visited the heap for some tuples, typically because `VACUUM` has not yet set the all-visible bit on the corresponding pages.
4. **Run a manual `VACUUM ANALYZE` after the index is created and before benchmarking.** Newly created indexes often report `Index Only Scan` but with non-trivial `Heap Fetches`, because the table has not been recently vacuumed and the visibility map is stale. Forcing a vacuum updates the visibility map and yields the true cost of the index-only path.
5. **Set a baseline with `EXPLAIN (ANALYZE, BUFFERS)`.** The `Buffers:` line distinguishes `shared hit` (cache) from `shared read` (disk); comparing a covering index to the equivalent non-covering index under the same cache state shows the real I/O saving.
6. **Watch for `Recheck Cond:` lines on GIN/GiST-style indexes.** Index-only scans are a B-tree optimization; non-B-tree plans can still avoid heap visits, but the planner represents the conditional differently. Reading the explain plan as a contract with the planner, not as a textual grep target, prevents misinterpreting `Index Scan` plus `Filter:` as "covering index failed".
7. **Confirm the plan after parameter skew.** A prepared statement that started with a custom plan may switch to a generic plan and choose a different access path; force `SET plan_cache_mode = force_custom_plan` to test the index-only plan under the specific parameter values you expect in production.
8. **Maintain the visibility map as a first-class concern.** Index-only scan costs are paid back only if the visibility map is current; aggressive autovacuum on heavily updated tables is the operational lever, not the index design.

## Controls

1. **Plan-capture regression test.** A CI test that runs `EXPLAIN (ANALYZE, FORMAT JSON)` against a fixture query, parses the `Plan Width`, `Node Type`, and `Heap Fetches`, and asserts both the chosen node type and a low fetch count under a freshly vacuumed table.
2. **Visibility map health metric.** A dashboard tracking `pg_stat_all_tables.n_mod_since_analyze`, with alerts when it exceeds thresholds that indicate autovacuum has not kept up with write traffic.
3. **Covering-index registry.** A schema migration check that new indexes on large tables include the columns actually selected, enforced by parsing the migration against a workload query catalogue.
4. **Plan-cache mode pinning for hot queries.** Hot read paths are run with a known `plan_cache_mode` and an assertion that the plan survives subsequent replans without an unexpected flip.
5. **Bloat guard.** A bloat check before declaring the covering-index win durable, since a covering index becomes useless if it is heavily bloated and the planner falls back to seq scans.

## Validation evidence

1. **Index-only vs index-with-heatch-fetch test.** With a freshly vacuumed table, compare the latency of a query served by the covering index against the same query served by an equivalent non-covering index; assert the covering index reports `Heap Fetches: 0` and lower wall time.
2. **Visibility map experiment.** Insert a small fraction of new rows after the last vacuum, run the same query, and confirm the `Heap Fetches` count rises for the rows on those pages only, demonstrating the dependency.
3. **`EXPLAIN (ANALYZE, BUFFERS)` cost test.** Under a cold cache (drop caches or use a large working set), compare buffer hits between the covering and non-covering indexes; the saving in disk reads should match the predicted reduction in pages visited.
4. **Parameter-skew test.** Run the query with a high-selectivity parameter and a low-selectivity parameter; confirm the planner still chooses the index-only plan in both cases when the cost model agrees, and document the cases where it does not.
5. **`VACUUM` recovery test.** Force an autovacuum after heavy churn and confirm `Heap Fetches` returns to zero on subsequent `EXPLAIN`, evidencing the operational control.

## Failure modes and correction

1. **Index-only scan reports `Heap Fetches: high`.** Symptom: the node is labelled correctly but cost is comparable to an index scan. Correction: schedule autovacuum more aggressively, run a one-off `VACUUM` to refresh the visibility map, and investigate whether the workload's write rate makes index-only scans uneconomic.
2. **Plan flips between Index Only Scan and Bitmap Heap Scan.** Symptom: latency variance tied to planner cost estimates. Correction: tighten statistics by running `ANALYZE` with a higher `default_statistics_target`, force `plan_cache_mode = force_custom_plan` for that query, or rewrite the query to favour the index path you intend.
3. **`INCLUDE` columns ignored because the leading key does not match the predicate.** Symptom: planner chooses seq scan because the index does not look selective. Correction: ensure the leading column(s) match the most selective predicate, or accept that the covering index is not the right access path for this query.
4. **`Index Only Scan` falsely reported because the column was already in the key.** Symptom: an audit reports an index-only scan, but the columns were already part of the key, so the optimization was always present. Correction: the plan label is correct but the optimization was free; the real covering-index opportunity is elsewhere.
5. **Type coercion forces a non-covering path.** `WHERE int_col = $1::text` disables the index. Correction: align the parameter type to the column type so the index remains usable.
6. **Index on a frequently updated payload column bloats the index.** Symptom: write throughput drops after the covering index is added. Correction: review which columns truly need to be in the index; remove redundant ones, and consider whether the table really needs index-only scans or whether a non-covering index would suffice.

## Limitations

1. **Index-only scan is a B-tree optimization.** Hash indexes, BRIN, and GiST have different visit semantics, and `Index Only Scan` is not the right metric for them.
2. **Visibility map accuracy is required;** a long-running transaction holding tuples visible only to itself defeats the optimization for those tuples until the transaction ends.
3. **Covering indexes pay write cost.** Every additional leaf-page column increases write amplification; large `INCLUDE` lists can become a maintenance liability on high-churn tables.
4. **The plan is a snapshot, not a guarantee.** Plan changes after statistics, configuration, or workload shifts can silently regress an index-only plan to a heap-fetching plan; tests must repeat across realistic workload ranges.
5. **Index size grows with `INCLUDE` payload.** Disk, cache, and rebuild costs scale with the included columns; the optimization is not free.

## Canonical sources

- PostgreSQL Documentation, Index-Only Scans: https://www.postgresql.org/docs/current/indexes-index-only-scans.html
- PostgreSQL Documentation, Multicolumn Indexes (`INCLUDE` clause): https://www.postgresql.org/docs/current/indexes-multicolumn.html
- PostgreSQL Documentation, Using EXPLAIN: https://www.postgresql.org/docs/current/using-explain.html