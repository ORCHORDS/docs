# Partition Pruning List Partition Cost Savings

## Scope

This article covers partition pruning for PostgreSQL LIST-partitioned tables: the planner's ability to skip irrelevant partitions during planning and execution, the conditions under which pruning activates, and the cost-savings outcomes that follow. It addresses how to design the partition key and how to express predicates that the planner can prune on, with attention to the difference between static pruning (at plan time) and dynamic pruning (during execution). It excludes RANGE pruning (which follows similar mechanics) and HASH pruning (which prunes less aggressively by design), both of which have separate considerations worth their own treatment.

## Workflow or implementation guidance

1. **Pick a partition key whose values are known and bounded.** A LIST-partitioned table suits discrete values: region codes, tenant identifiers in a small bounded set, or status enums. The key should be stable; renaming the discrete key invalidates partitions.
2. **Declare the parent table with `PARTITION BY LIST (<column>)`.** The column type should match exactly what the application writes; a type mismatch causes the row to fall into the default partition or to fail outright.
3. **Create one child partition per value or per small group of values.** `CREATE TABLE orders_2026 PARTITION OF orders FOR VALUES IN ('EU', 'UK');`. A separate default partition catches out-of-range values; treat it as a monitoring target, not as a production destination.
4. **Write predicates that the planner can prune on.** The strongest form is `WHERE region = 'EU'`. The planner can prune statically when the predicate references the partition key with a literal; dynamic pruning activates when the planner learns the actual value at execution time (for example, a parameter from a prepared statement).
5. **Avoid functions on the partition key.** `WHERE upper(region) = 'EU'` prevents pruning because the planner cannot determine the partition from the function's output without evaluating every partition. A generated column with the uppercased value, indexed, is the workaround if you truly must uppercase.
6. **Use `EXPLAIN` to verify pruning.** `EXPLAIN` shows the partitions considered; if the plan lists every partition, pruning is not happening. `EXPLAIN (ANALYZE)` shows the partitions actually scanned, which is the real evidence.
7. **Combine predicates.** A query like `WHERE region IN ('EU','UK') AND created_at > now()` lets the planner prune by region first and then apply the date filter within the surviving partitions. Combining predicates on partition key and non-key columns is a common and effective pattern.
8. **Default partition discipline.** A growing default partition is a sign of misplaced rows; monitor its row count and triage the values that landed there. A larger default partition also degrades the benefit of the rest of the partitioning strategy.
9. **Indexes propagate to children, but partial indexes do not auto-rebalance.** An index declared on the parent is created on each child; a partial index must be declared on each child (or via a template mechanism) and must be re-evaluated as the partition population changes.
10. **Move partitions in and out of the parent's read path.** `ALTER TABLE ... DETACH PARTITION` removes the partition from query plans without dropping data, useful for archival; `ATTACH PARTITION` brings it back. Detach is metadata-only and fast regardless of row count.

## Controls

1. **Default partition size alert.** Alert when the default partition exceeds a threshold of rows; values that land there are mis-classified.
2. **Per-partition row counts in dashboards.** A view of `pg_inherits` joined to `pg_class` showing row counts per partition; balance alerts indicate skewed partitioning.
3. **Pruning verification in CI.** A regression test that runs `EXPLAIN` against representative queries and asserts the partition set is the expected one; a query that scans the entire partitioned set is caught before deploy.
4. **Partition template policy.** A documented convention for naming (`<parent>_<key>_<value>`) and for whether partitions are created by migration or by a runtime partition manager.
5. **Detach safety check.** Before `DETACH PARTITION`, an automated check that no active long-running transactions are reading the partition.
6. **Replica-lag awareness.** Bulk loads into a partition on the primary cause lag spikes on replicas during the load; monitor lag and pause or throttle loads.

## Validation evidence

1. **Pruning assertion.** Run `EXPLAIN ANALYZE` on `SELECT * FROM orders WHERE region = 'EU'` against a partitioned table with ten children; assert only the `orders_eu` partition appears in the plan and the others do not.
2. **Cost-savings measurement.** Compare the same query against a non-partitioned table with identical row count and index strategy; assert the partitioned query's `Buffers:` and `actual time` are lower in proportion to the fraction of rows that fall into the targeted partition.
3. **Dynamic pruning test.** Prepare the statement with `PREPARE q AS SELECT * FROM orders WHERE region = $1;` and execute it with different values; assert pruning still applies in `EXPLAIN ANALYZE` (Postgres plans prepared statements with parameterised pruning since v11).
4. **Default partition triage test.** Insert a row with a value outside the explicit partition list and confirm it lands in the default; assert the monitoring surface fires.
5. **Detach-and-re-attach test.** Detach a partition, run a query that previously included it, confirm the result set is now smaller; reattach, confirm the row set is restored.

## Failure modes and correction

1. **Function on the partition key disables pruning.** Symptom: `EXPLAIN` lists every partition. Correction: rewrite the predicate to compare against the literal or use a generated column whose value the planner can match.
2. **Default partition silently grows.** Symptom: pruning still works but the default partition's share of cost rises. Correction: investigate which values are landing there, create the missing partitions, and reroute the data.
3. **Bulk insert loads hit the wrong partition.** Symptom: a long bulk insert is slower than expected because it triggers per-partition autovacuum and constraint checks. Correction: partition the bulk by the partition key so each load lands in its target partition; consider `COPY` per partition.
4. **Prepared statement stops pruning after plan-cache switch.** Symptom: a previously fast query becomes slow after `pg_stat_statements` re-aggregation. Correction: confirm `EXPLAIN (GENERIC_PLAN)` shows pruning; if it does not, use a custom plan or rewrite the query.
5. **Index missing on a new partition.** Symptom: queries against the new partition are slow because the index that exists on the parent was not propagated or the partial-index predicate excludes the new partition's rows. Correction: re-attach the partition with the matching index, or use `CREATE INDEX ... ON ONLY <partition>` carefully.
6. **`DETACH PARTITION` blocked by a long-running query.** Symptom: the detach waits. Correction: identify and end the blocking query, or schedule the detach during a maintenance window.

## Limitations

1. **Partitioning does not automatically improve performance** if the workload does not include a predicate that the planner can prune on. A full scan of every partition is no faster than a scan of a single table of the same total size.
2. **`LIST` partitioning is most useful with bounded key sets.** A column with millions of distinct values should be `RANGE` or `HASH` partitioned instead.
3. **Cross-partition operations are expensive.** A query that joins the partitioned table with itself on a non-partition key may scan all partitions; unique constraints across the whole table require the partition key in the constraint.
4. **Partitioning adds operational surface.** Pre-creation, monitoring, default-partition hygiene, and detach/attach discipline all need an owner; a team that does not commit to these will see partitioning as a net cost.
5. **Foreign keys into a partitioned table have constraints;** a row in another table cannot reference a specific partition's row without including the partition key.

## Canonical sources

- PostgreSQL Documentation, Table Partitioning: https://www.postgresql.org/docs/current/ddl-partitioning.html
- PostgreSQL Documentation, Partition Pruning (under Query Planning): https://www.postgresql.org/docs/current/ddl-partitioning.html#DDL-PARTITION-PRUNING
- PostgreSQL Documentation, Partitioning Considerations: https://www.postgresql.org/docs/current/ddl-partitioning.html#DDL-PARTITIONING-CONSTRAINTS