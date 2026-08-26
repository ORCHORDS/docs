# hierarchical-data-ltree

**Issue:** Trees in relational databases — org charts, category taxonomies, comment threads, folder structures, permission inheritance — keep being modeled as a bare `parent_id` column and then queried with recursive CTEs. That works until it doesn't: "all descendants of node X", "the full path from root to X", or "move subtree X under Y" either recurse expensively on every read or force N+1 application-side traversal. Choosing a hierarchy storage model (adjacency list, materialized path, ltree, closure table, nested sets) is a real engineering trade-off between read speed, write complexity, integrity enforcement, and storage — and the community-consensus answer in 2025 is still nuanced: adjacency for integrity, ltree for read-heavy subtree queries, closure tables when you need arbitrary depth queries plus cheap ancestor checks.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The four viable models

1. **Adjacency list (`parent_id`).** One nullable FK per row; writes and moves are trivial, referential integrity is fully enforced, cycles are prevented by the FK. The cost is reads: whole subtrees need a recursive CTE whose cost grows with tree depth, and every application query pays it. This remains the best default for write-heavy or modest-size trees.
2. **ltree (materialized path as a native type).** The Postgres extension stores a label path like `root.eng.eu.berlin` per row, with a GiST index over it. Subtree queries become index lookups on path prefixes (`path <@ 'root.eng.eu'`), ancestors are a single ordered scan, and depth is visible in the path itself. The costs: paths must be rewritten for an entire subtree on move, and integrity (path matches parent's path + own label) is not enforced by the database — you maintain it in application code or triggers.
3. **Closure table.** A separate `node_paths (ancestor_id, descendant_id, depth)` row for every ancestor-descendant pair. Any subtree or ancestor query is a single indexed join; arbitrary "friends-of-friends-style" traversal falls out for free. The costs are storage that grows O(depth × nodes) and write amplification (inserting a leaf writes one row per ancestor; moving a subtree rewrites many paths).
4. **Nested sets (and nested intervals).** Each node stores left/right interval bounds so subtrees are contiguous ranges — subtree reads are a single between predicate. But any insert or move renumbers potentially every node, which is why nested sets have fallen out of favor for mutable trees; they remain reasonable for static, read-only taxonomies.

## Choosing by access pattern

1. **Read-heavy subtree queries, shallow-to-medium depth: ltree.** Product categories, menus, location trees — where "give me everything under X, sorted by path" dominates and moves are rare. The GiST index makes prefix queries index-backed, which recursive CTEs can never be.
2. **Write-heavy or integrity-critical: adjacency list + recursive CTE.** Comment threads with heavy inserts, org charts with frequent reparenting — keep `parent_id` as the source of truth (FK-enforced), and if reads hurt, denormalize an ltree or path column maintained by trigger on top of it.
3. **Both directions queried, many-to-one and one-to-many at scale: closure table.** When you frequently need "all ancestors of X" and "all descendants of Y" with exact depth filtering, closure rows answer both from one index; the write amplification is the price of not recursing at read time.
4. **Never store a comma-separated path string in a text column and LIKE it.** The untyped version of materialized path (`WHERE path LIKE 'root/eng/%'`) defeats indexes, admits malformed paths, and reproduces ltree badly; if you want paths, use the extension that exists for exactly this.

## Making each model correct

1. **Keep the FK even when denormalizing.** Hybrid designs (adjacency as truth + ltree/path for reads) should keep the `parent_id` FK constraint so the relational invariant is enforced; the derived path is then a performance artifact, rebuildable from truth at any time.
2. **Enforce path validity for ltree with triggers or generated maintenance.** Moving node X requires updating `path` for X and every descendant; wrap it in one transaction with the recursive CTE doing the rewrite (`UPDATE t SET path = new_prefix || subpath(path, nlevel(old_prefix)) WHERE path <@ old_prefix`) so readers never see half-moved subtrees.
3. **Guard against cycles in adjacency models.** A plain FK prevents orphans, not cycles; if your model allows updates to `parent_id`, add a trigger that walks up from the new parent and rejects any path that returns to the starting row, or constrain depth to make cycles bounded.
4. **Version your moves.** Reparenting with an `expected_parent_version` check (optimistic locking) prevents two concurrent moves from interleaving path rewrites; subtree moves are exactly the kind of long-ish write transaction that loses races quietly.

## Query patterns to know before deciding

1. **Subtree including the node, with depth limit.** ltree: `WHERE path <@ 'root.eng.eu' AND nlevel(path) <= nlevel('root.eng.eu') + 3` — the depth cap falls out of path length, which recursive CTEs must thread through union arms.
2. **Ancestors ordered root-first.** ltree gives this as `path @> 'root.eng.eu.berlin'` plus an index-only scan, or `subpath` slicing in application code; adjacency requires a recursive CTE that then needs reversing.
3. **Subtree aggregates (counts, sums).** With a closure table, aggregates over a subtree are one join-and-group; with ltree, a join on the prefix predicate; with pure adjacency, a recursive CTE materializing the subtree first.
4. **Move-subtree cost budget.** Before committing to a model, estimate rows touched by a move at your expected tree shape: adjacency O(1), ltree O(subtree), closure O(subtree × average ancestor count), nested sets O(table). The model choice is usually decided by which of these you can afford.
