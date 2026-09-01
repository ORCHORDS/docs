# Partial Index Where Clause Rare Flag

## Scope

This article covers PostgreSQL partial indexes (`CREATE INDEX ... WHERE <predicate>`), their canonical use case (indexing the small minority of rows sharing a rare flag or value), and the conditions under which they are an unambiguous win versus a hazard. It addresses how the planner recognises the partial-index predicate and includes the index in plans, the cost of maintaining an extra index, and the operational consequences of relying on a predicate that the application stops respecting. It excludes partitioning-based row-set reduction, expression indexes (which compose with partial predicates but have their own correctness surface), and GIN partial indexes for `jsonb` and full-text workloads.

## Workflow or implementation guidance

1. **Use a partial index when the queried subset is small and stable.** The canonical use is "open orders", "pending retries", "users who opted into marketing", "rows with `deleted_at IS NULL`": rows with a particular value of a low-cardinality column or rows in a particular lifecycle state, where the partial-index population is a small fraction of the table.
2. **Match the query's predicate exactly to the index predicate.** `CREATE INDEX ... ON orders (created_at) WHERE status = 'pending'` will be considered by the planner only when the query contains `WHERE status = 'pending'` (and ideally with the same literal, though simple rephrasings may be accepted). A query that uses `status IN ('pending', 'overdue')` will not use the partial index as such, even though humans would consider it equivalent.
3. **Pick the indexed column for the work that follows the predicate.** The partial index should lead with the column the query orders by, filters by range, or joins on *after* the predicate has been applied. Indexing `created_at` while the query is `WHERE status='pending' ORDER BY id` would be the wrong shape.
4. **Combine the partial predicate with an `INCLUDE` clause to enable index-only scans.** When the partial-index population is small, an index-only scan can serve the query entirely from the index; `INCLUDE` the columns the query returns to make that possible.
5. **Plan for predicate drift.** The partial-index predicate is a contract: the application must continue to populate the predicate value as designed. If the application starts writing `'Pending'` (capitalised) or `'PENDING'` (uppercase), the index still covers only `'pending'`, and queries for the new value fall back to seq scan. The control is in the application and the migration that introduced the constant.
6. **Bound the predicate to a small, predictable fraction of the table.** A predicate that, over time, captures half the table is no longer a partial index in any meaningful sense; the index grows to a significant fraction of the table size, and the planner may stop preferring it. Reassess periodically whether the predicate is still "partial" in the practical sense.
7. **Avoid partial unique indexes without careful thought.** `CREATE UNIQUE INDEX ... ON users (email) WHERE deleted_at IS NULL` is a powerful tool for handling soft-delete conflicts, but the predicate must be exactly `WHERE deleted_at IS NULL` (not `IS NULL AND active`) for the planner and constraint enforcement to agree.
8. **Re-evaluate the index when the column's statistics drift.** If the table now has 80% rows matching the predicate, the planner's cost model may prefer a full index. Recompute, and if the partial index is no longer optimal, replace it with a regular index.
9. **Test the predicate explicitly.** Run `EXPLAIN (ANALYZE) SELECT ... WHERE <exact predicate>` and confirm the partial index is selected; if not, rephrase the query or rebuild the index with the matching predicate.

## Controls

1. **Predicate documentation.** Each partial index has a comment or migration annotation that names the application constants involved, so a code review can spot a literal change that would invalidate the predicate.
2. **Index utilisation dashboard.** A periodic report from `pg_stat_user_indexes` showing scans of each index; a partial index whose scans drop to zero is a candidate for removal or rewrite.
3. **Predicate population monitor.** A scheduled query returning the fraction of rows matching the predicate; alert when this fraction crosses a threshold that makes the index uneconomical.
4. **Soft-delete contract test.** A CI test that issues the application's hot soft-delete query and asserts the partial index is selected; fails if the predicate expression drifts.
5. **Index-size budget.** A table of partial-index sizes; a runaway index is a sign that the predicate has expanded.
6. **Migration review.** Adding a partial index requires review of the query shapes that will use it, the constants involved, and the migration that defines those constants.

## Validation evidence

1. **Index-selection test.** `EXPLAIN ANALYZE` confirms the partial index is chosen for the matching predicate and not chosen for a non-matching predicate, demonstrating the planner's respect for the predicate.
2. **Size test.** Compare the partial index's size to the full table; assert the index is a small fraction of the table size, evidencing the "partial" claim.
3. **Cost-savings benchmark.** Compare the same query with the partial index versus a full index; assert the partial-index plan is faster (or at least no slower) and consumes fewer buffers.
4. **Predicate-drift test.** Insert a row whose status value differs in case or whitespace; confirm the partial index does not cover it and the query falls back appropriately.
5. **Soft-delete conflict test.** With a partial unique index on `(email) WHERE deleted_at IS NULL`, attempt to insert a second row with the same email where one is soft-deleted and one is active; assert the constraint blocks the duplicate.

## Failure modes and correction

1. **Predicate is more permissive than the query.** Symptom: the partial index covers rows the query does not actually want; size grows but selectivity does not improve. Correction: tighten the predicate to match the query exactly, or split into multiple partial indexes if the workload genuinely has multiple predicates.
2. **Predicate is less permissive than the query.** Symptom: the query uses a different predicate, the partial index is unused, and the query is slow. Correction: align the query's predicate to the index's predicate or rebuild the index with the matching predicate.
3. **Application changes the predicate constant.** Symptom: rows still match the application logic but no longer match the index predicate; the index is silently underused. Correction: treat the constant as code, with the index's predicate as a downstream consumer; linting rejects drift.
4. **Partial unique constraint too restrictive.** Symptom: a row that the application considers a duplicate passes the constraint because the predicate excludes one of the duplicates. Correction: review the predicate and the constraint together; the partial unique index is for the soft-delete pattern, not for all uniqueness needs.
5. **Index used to be small, now large.** Symptom: index size has grown because the predicate's population has grown; the planner has stopped using it. Correction: replace with a full index or partition the table by the predicate column.
6. **Multiple partial indexes on the same table.** Symptom: write amplification is significant. Correction: review whether some of the predicates can be combined or whether a single index with an `INCLUDE` clause covers all the queries.

## Limitations

1. **Partial indexes do not generalise.** The planner uses them only for the specific predicate they encode; a workload that filters on related but different predicates does not benefit.
2. **`INCLUDE` columns are not constrained by the predicate.** The leaf entries exist for rows that match the predicate; queries that filter by the `INCLUDE` column alone cannot use the index.
3. **Partial indexes are not useful for ordering-only queries on the included columns.** A query `ORDER BY created_at` with no predicate that matches the partial index will not benefit, even if most rows match the predicate.
4. **Predicate drift is silent.** The index continues to exist and to consume write cycles even when no query uses it; only monitoring and periodic `pg_stat_user_indexes` review expose the situation.
5. **The cost model does not predict all cases.** A partial index whose population has grown but is still a minority may be chosen in dev and not in production; test on production-shaped data.

## Canonical sources

- PostgreSQL Documentation, Partial Indexes: https://www.postgresql.org/docs/current/indexes-partial.html
- PostgreSQL Documentation, Indexes on Expressions (related technique): https://www.postgresql.org/docs/current/indexes-expressions.html
- PostgreSQL Documentation, Multicolumn Indexes (INCLUDE clause): https://www.postgresql.org/docs/current/indexes-multicolumn.html