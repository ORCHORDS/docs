# fillfactor-hot-updates

**Issue:** Update-heavy Postgres tables (counters, job rows, leaderboards, heartbeats, frequently-edited documents) degrade in a specific way: every `UPDATE` writes a new row version, and when any indexed column changed — or the new version can't fit on the original page — every index on the table gains a pointer to the new tuple. Index churn balloons, tables and indexes bloat, autovacuum falls behind, and write latency creeps up over weeks. The two levers that prevent most of this are keeping updates HOT (heap-only tuple: new version lands on the same page, indexes untouched) and reserving page space via `fillfactor` so HOT has somewhere to land. Most teams tune neither, then fight bloat with `pg_repack` forever.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## How HOT updates actually work

1. **Two conditions, both required.** An update is HOT only when (a) no column used by any index on the table was modified, and (b) the new tuple fits on a page that the old tuple's page can point to — in practice, the same page. Miss either and every index on the table must be updated with a new entry pointing at the new tuple.
2. **HOT means zero index writes.** When HOT applies, Postgres stores a line-pointer chain on the heap page: indexes still point at the old slot, which forwards to the new version. Reads cost an extra hop, but writes skip all index maintenance — this is why HOT-heavy tables can sustain update rates that non-HOT tables cannot.
3. **HOT also makes vacuum cheaper.** Dead tuples from HOT chains are prunable by any backend touching the page without a full index scan; non-HOT dead tuples require vacuum to scan every index. Keeping updates HOT is therefore an autovacuum optimization as much as a write-throughput one.
4. **Measure before tuning.** `pg_stat_user_tables` exposes `n_tup_upd` and `n_tup_hot_upd`; the ratio (hot/non-hot) is the single most diagnostic number for an update-heavy table — below roughly 50% on a hot table means either indexed columns are changing or pages have no room, and each cause has a different fix.

## The indexed-column trap

1. **One churny indexed column defeats every index.** If `updated_at` or a `status` column is indexed and changes on every update, no update can ever be HOT — and every other index on the table pays for it. Audit hot tables for indexes on mutable columns; partial indexes (e.g. only `WHERE status = 'pending'`) often express the same query need without indexing the value across all its transitions.
2. **TOASTed columns have their own rules.** Updates to out-of-line TOAST values can avoid rewriting the TOAST data when only non-TOASTed columns change, but changing a large value itself forces new TOAST writes regardless of HOT; keep volatile large columns out of update-heavy rows where possible.
3. **Counter tables are the textbook case.** A `metrics (key, value, updated_at)` table where `value` is the only indexed-key candidate can update fully HOT; the same table with an index on `updated_at` (for a "recently updated" query) drops to near-zero HOT and bloats relentlessly — replace it with a partial index or drive recency from the key space.

## Tuning fillfactor

1. **What fillfactor reserves.** `fillfactor` is the fraction of each page packed at initial insert (default 100, no reserved space); setting 70 leaves 30% free per page so updated versions can land on the same page as their predecessors. Common guidance for update-heavy tables is 70–90: benchmark your row-width delta — oversized reservations just waste memory and I/O on tables whose rows don't grow.
2. **It only affects newly-written pages.** `ALTER TABLE t SET (fillfactor = 70)` changes future page fills only; existing packed pages stay packed until rewritten. To apply the setting to current data, rewrite with `VACUUM FULL` (exclusive lock) or online with `pg_repack`, which rebuilds the table under a brief lock while traffic continues.
3. **Pick fillfactor per table, not cluster-wide.** Append-only tables (events, logs) gain nothing from reserved space — keep 100 so pages stay dense and scans stay fast; only tables with sustained in-place update patterns benefit. A blanket low fillfactor is a pessimization dressed as tuning.
4. **Free space needs vacuum to become usable.** Space freed by dead tuples can only be reused after vacuum prunes the chain; on hot tables set per-table `autovacuum_vacuum_scale_factor` low (0.01–0.05) and consider `autovacuum_vacuum_cost_delay = 0` so space is recycled promptly and HOT has room to work.

## Diagnosis and remediation loop

1. **Check the HOT ratio first.** Query `n_tup_hot_upd / n_tup_upd` from `pg_stat_user_tables` over a representative window; a high ratio with still-degrading performance points elsewhere (locks, WAL, checkpoint pressure), a low ratio points at indexed-column churn or no page space.
2. **Distinguish table bloat from index bloat.** If indexes are bloated but the table is not, HOT is likely working but old indexes accumulated garbage from a past non-HOT era; `REINDEX CONCURRENTLY` fixes it without blocking writes (Postgres 12+), as covered in the index-bloat literature (e.g. Kendra Little's 2025 guide).
3. **Repack instead of VACUUM FULL on live tables.** Vacuum never shrinks files — it only marks space reusable — so a table bloated during a misconfiguration stays big; `pg_repack` rebuilds online, reapplies your fillfactor, and returns the disk, while `VACUUM FULL` takes an `ACCESS EXCLUSIVE` lock that is rarely acceptable in production.
4. **Re-measure after changes.** Reset statistics (`pg_stat_reset()` for the table or wait for a fresh window), rerun the workload, and confirm the HOT ratio rose and index growth rate fell; fillfactor changes that don't move the ratio mean the real blocker is an indexed mutable column, not page space.
