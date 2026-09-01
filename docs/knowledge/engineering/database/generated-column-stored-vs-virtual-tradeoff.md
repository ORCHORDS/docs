# Generated Column Stored Vs Virtual Tradeoff

## Scope

This article covers PostgreSQL generated columns, comparing stored (`STORED`) and virtual (`VIRTUAL`, sometimes called "computed at read time") variants, and the practical trade-offs in indexing, write amplification, and deterministic-expression requirements. It addresses the recurring decisions about where to materialize derived values: in the application layer, in a trigger, in a generated column, or in a view. It is scoped to PostgreSQL 12 and newer, where `GENERATED ALWAYS AS ... STORED` is supported. It does not cover MySQL/MariaDB generated columns (which have slightly different syntax and behaviour), nor application-side caching or materialization engines.

## Workflow or implementation guidance

1. **Recognise what PostgreSQL offers.** PostgreSQL supports `GENERATED ALWAYS AS (expr) STORED`, which computes the expression at row write time and stores the result on disk. It does not natively support virtual generated columns; a non-`STORED` generated column is rejected at creation time. When teams ask about "virtual" alternatives, the practical PostgreSQL choices are a plain expression index or a view, not a virtual generated column.
2. **Use `STORED` when the expression must be indexable or returned cheaply.** Indexing a stored generated column is the canonical way to support queries like `WHERE lower(email) = 'x@y'` without the planner rejecting the index or the application manually denormalizing. The expression is computed once at insert/update, the result is part of the row, and any index on it behaves like a normal column index.
3. **Use an expression index when you want to avoid the storage and write cost.** `CREATE INDEX ... ON table (lower(email))` is indexable in the same way as a stored generated column, without storing the value on disk. The trade-off is that each query that filters on the expression must use the exact expression (or a planner-recognizable rephrasing) to benefit, and the expression is recomputed for every indexed tuple at index build and update time.
4. **Use a view when the computation is expensive at scale but the result is queried as a set, not filtered on.** A view with a generated-column-style expression lets you select it but the database cannot index the view's output; the expression is re-evaluated per row scanned, which can be acceptable for analytical access and unacceptable for hot-path filters.
5. **Keep the expression immutable and deterministic.** `GENERATED ALWAYS AS ... STORED` requires `IMMUTABLE` functions, and non-immutable inputs are an error. Use simple, side-effect-free expressions. Calling `now()`, `random()`, or a volatile function in the expression is a bug pattern that PostgreSQL will reject at creation or will silently misbehave if accepted.
6. **Plan for write amplification.** Every inserted or updated row recomputes the stored value and writes it to disk. A table with several generated columns, each based on heavy expressions, pays the cost on every write. Measure the impact on bulk loads and on update-heavy tables.
7. **Account for logical replication and tooling.** Generated columns are part of the row, so they replicate with the row. Migration tools that introspect tables will see them as ordinary columns; downstream consumers should be told that a column is generated so they do not attempt to `INSERT` it.
8. **Avoid generated columns for invariants already enforced elsewhere.** If the application layer always derives the value and there is no query pattern that needs the value indexed, a generated column duplicates effort. Choose the minimum surface that the query layer needs.

## Controls

1. **Immutability rule.** A migration lint that rejects generated-column expressions containing `now()`, `clock_timestamp()`, `random()`, `txid_current()`, or any `VOLATILE` function call.
2. **Expression-index counterpart.** A documentation rule that any expression indexed for query use is paired with a comment naming the expression so that future query rephrasings preserve the match.
3. **Generated-column inventory.** A periodic query against `information_schema.columns` (filtered on `is_generated = 'ALWAYS'` or equivalent) to ensure every generated column has an owner and a justified query pattern that uses it.
4. **Bulk-load budget test.** A staging load that times a representative bulk insert with and without the generated columns, captured as part of the migration's review.
5. **No direct INSERT rule.** Generated columns must not appear in `INSERT` column lists; a database lint or test enforces this for the team's own code, while PostgreSQL itself enforces it at execution.
6. **Replication consumer notice.** A change-log entry whenever a generated column is added, identifying downstream consumers that may need schema updates.

## Validation evidence

1. **Generated-column write test.** Insert a row whose computed value would differ from the natural derivation; assert the stored value is correct and any subsequent `SELECT` returns the generated value, not the literal supplied.
2. **Index utilization test.** Create an index on the generated column, run `EXPLAIN ANALYZE` against a query that filters on the natural expression, and assert the index is chosen.
3. **Immutability rejection test.** Attempt `CREATE TABLE t (g int GENERATED ALWAYS AS (random()) STORED);` and assert PostgreSQL rejects the expression with a volatility error, demonstrating the guardrail.
4. **Update recompute test.** Update a base column whose generated counterpart depends on it; assert the generated column reflects the new value after the update, confirming the recomputation contract.
5. **Bulk load measurement.** Compare `COPY` time with and without the generated column on a 10-million-row fixture; record the multiplier to expose write-amplification cost before production.

## Failure modes and correction

1. **Application code attempts to insert into the generated column.** Symptom: insert error `column "..." cannot be listed in INSERT column list`. Correction: remove the column from the application's `INSERT` projection; PostgreSQL will compute the value automatically.
2. **Volatile expression silently accepted because of a wrapper function.** A user-defined function marked `IMMUTABLE` that actually behaves non-deterministically (calls a session variable or external state) produces wrong values without warning. Correction: audit the function's body; if non-deterministic, fix it or remove the immutability marker and remove the generated column.
3. **Write amplification slows the hot path.** Symptom: insert throughput drops after a migration adds a generated column. Correction: profile the expression cost; either simplify, drop the generated column in favour of an expression index, or move the computation to the application layer where it can be cached.
4. **Query uses a rephrased expression that does not match the index.** Symptom: `EXPLAIN` shows a seq scan even though an indexed generated column exists, because the query wrote `WHERE lower(email) = ...` while the generated column is `email_lower`. Correction: standardise the expression naming in code review or use a generated column whose expression matches the most common rephrasings.
5. **Logical replication consumer sees a generated column it does not expect.** Symptom: insert fails on the subscriber side. Correction: update the subscriber to omit the generated column from its insert list, or alter the consumer to be aware of the column's existence and treat it as read-only.
6. **Drop-and-recreate cycle during type change.** Generated columns must match the type of their expression, and altering that expression is not always supported. Correction: a planned multi-step migration that drops the column, alters the expression, and recreates with the new definition in a maintenance window.

## Limitations

1. **PostgreSQL does not support virtual (non-stored) generated columns natively**, so the comparison in this article's title is structurally asymmetric. Storage and write cost are unavoidable when using `STORED`.
2. **Generated columns cannot reference other generated columns in the same table.** The expression may reference only base columns of the same row, not other generated columns; chained derivations must be expressed in a single function or reorganised.
3. **Generated columns cannot be altered with `ALTER COLUMN ... SET DEFAULT` or `NOT NULL` reapplication while keeping the generation property intact**; some metadata changes force a column drop and recreate.
4. **Expression index and stored generated column cannot coexist on the same expression** in a redundant way without doubling write cost; pick one based on the trade-off above.
5. **Generated columns do not enforce business invariants.** They compute a value; they do not constrain it. A row's inputs can still violate assumptions baked into the expression.

## Canonical sources

- PostgreSQL Documentation, Generated Columns: https://www.postgresql.org/docs/current/ddl-generated-columns.html
- PostgreSQL Documentation, Indexes on Expressions: https://www.postgresql.org/docs/current/indexes-expressions.html
- PostgreSQL Documentation, CREATE TABLE: https://www.postgresql.org/docs/current/sql-createtable.html