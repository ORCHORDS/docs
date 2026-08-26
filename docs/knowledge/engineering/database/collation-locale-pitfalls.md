# collation-locale-pitfalls

**Issue:** Text ordering in Postgres is not computed by Postgres — for `libc` (glibc) collations it comes from the operating system's locale libraries, and for ICU from the bundled ICU library. When those libraries change versions (an OS upgrade, a container base image bump, a cloud instance migration), sort order can change, and every B-tree index on text silently becomes corrupt: lookups miss rows that are visibly there. Postgres cannot detect this. It is one of the few failure modes that is simultaneously silent, catastrophic, and caused by routine infrastructure maintenance — and the 2025-era provider landscape (glibc default, ICU versioned, the PG17 builtin provider) exists almost entirely to solve it.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## How collation breaks indexes

1. **B-tree order is frozen at index time.** An index stores text sorted under the collation rules in effect when rows were inserted; a lookup uses the rules in effect at query time. If the library changed in between, the search descends the tree following stale ordering and misses rows — corruption with no error, no warning, and no crash.
2. **The glibc 2.28 event.** glibc 2.28 (2018) changed collation order for many locales; every system that upgraded underneath a running Postgres without reindexing ended up with corrupt text indexes. The PostgreSQL wiki's "Locale data changes" page documents this and every subsequent glibc release with ordering changes — the class of problem is ongoing, not historical.
3. **No detection from the server.** For libc providers Postgres has no version marker to compare, so it cannot even warn; the official guidance is effectively "if you upgraded libc, `REINDEX` everything indexed on text". `amcheck` (corruption checker) can find the damage after the fact — after rows have already gone missing.
4. **Restores and cross-version upgrades inherit it.** `pg_upgrade` between Postgres majors across an OS upgrade, or a logical restore into a cluster with a different libc version, changes the effective collation even though "the data did not change" — the index rebuild question has to be answered explicitly, not assumed away.

## The provider landscape (2025–2026)

1. **libc is still the default.** Even in PostgreSQL 18, a plain `initdb` defaults to the libc provider with the OS locale — meaning the out-of-the-box experience still inherits glibc's mutable ordering. Defaults do not protect you; the choice has to be deliberate.
2. **ICU is versioned and honest.** The ICU provider (`--locale-provider=icu`, available since PG10, first-class since PG15) is independent of glibc. ICU version changes can still alter ordering, but Postgres records the ICU version in the database catalog and warns on version mismatch — the failure mode becomes a loud `REFRESH COLLATION VERSION` plus reindex, not silence. (ICU 73 had a versioning bug that confused even this mechanism; the lesson is that version tracking makes problems visible, not that ICU is magic.)
3. **PG17's builtin provider freezes the problem.** PostgreSQL 17 added a third provider, `builtin`, supporting exactly `C` and `C.UTF-8`, implemented entirely inside Postgres. Its ordering can never change across OS or library upgrades — it is the only provider immune to the whole corruption class. The trade is real: `C.UTF-8` orders by code point, not linguistically ("é" does not sort adjacent to "e" the way users may expect).
4. **Per-database and per-column granularity.** Provider is a database-level `initdb`/`CREATE DATABASE` decision, with `CREATE COLLATION` allowing ICU variants and per-column collation overrides — a hot table can be pinned to an immutable collation while the rest of the database uses linguistic sorting.

## Choosing a provider for new databases

1. **Default to builtin `C.UTF-8` when sorting is mechanical.** If text columns are IDs, emails, tokens, enums-as-text, and machine-compared keys — the majority in service schemas — linguistic correctness never mattered, and `initdb --locale-provider=builtin --builtin-locale=C.UTF-8` permanently deletes the reindex-on-OS-upgrade tax.
2. **Choose ICU when users see the ordering.** User-facing sorted lists (names in many languages) need ICU collations (`und-u-ks-level2` and friends); accept the versioned-maintenance model and monitor for the version-mismatch warning rather than hoping.
3. **Never choose glibc consciously.** A deliberate libc choice in 2026 is only defensible for legacy compatibility; document it as debt with a scheduled migration if it must exist.
4. **Also fix `LC_CTYPE` thinking.** Case mapping and classification follow the same provider machinery; case-insensitive uniqueness and `LOWER()`-based indexes inherit the same upgrade risk as ordering.

## Defensive operations

1. **Treat every OS/base-image upgrade as a reindex event.** When the libc version changes under a cluster using libc collations, `REINDEX` all text indexes (or rebuild via `pg_dump`/restore into a fresh cluster). Put this in the runbook for image bumps — it is the step most teams skip and regret.
2. **Watch the ICU version warning.** On log review, act on "collation ... has version mismatch" immediately: `ALTER DATABASE ... REFRESH COLLATION VERSION` records the new version and reindex follows. Ignoring the warning converts a tracked change into untracked corruption.
3. **Verify with `amcheck` after suspicion.** `CREATE EXTENSION amcheck` and `bt_index_check` across text indexes detects ordering divergence after any suspected library change — cheap relative to discovering missing rows from application bug reports.
4. **Record the provider in infra-as-code.** The locale provider and locale belong in the cluster-creation config (Terraform/Ansible/compose), not in tribal memory; a recreation of the environment six months later must reproduce the same decision.

## Query-level surprises worth knowing

1. **`LIKE` prefixes need `text_pattern_ops` or C collation.** Under non-C collations, `col LIKE 'abc%'` cannot use a plain B-tree index; either a `text_pattern_ops` index or a C-collation column is required — a frequent "why is this slow" with no obvious cause.
2. **Equality is safe; range scans are not.** Hash lookups and equality comparisons do not depend on collation ordering the way range scans do, which is why corruption sometimes hides for weeks in equality-heavy workloads and detonates the first time a range query or an `ORDER BY ... LIMIT` runs.
3. **Sorting differs across providers by design.** Migrating a database from glibc to ICU (or C.UTF-8) changes result order for ties and non-ASCII text; pagination cursors keyed on sorted text must be re-verified after such a migration.
