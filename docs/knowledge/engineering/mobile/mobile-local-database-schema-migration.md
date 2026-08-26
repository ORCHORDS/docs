# mobile-local-database-schema-migration

**Issue:** Every app with a local database (Room, Core Data, SQLite, WatermelonDB, Realm, MMKV key migrations) eventually ships a schema change — and the migration runs on hundreds of thousands of unattended devices with real user data, at app launch, often on cheap hardware. A bad migration is the worst class of mobile bug: it silently corrupts or wipes user data, it cannot be "re-deployed" like a server migration (the broken version is already staged on devices), and downgrades are impossible because users who restore a backup from a newer version onto an older app binary hit a schema the old code cannot read. This article covers migration strategy per stack, the failure modes that destroy data, and how to test migrations so v3→v5 paths are proven before release.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why on-device migrations differ from server migrations

1. **You deploy one migration to N schema versions simultaneously.** Users skip app versions: a device on v2 auto-updates straight to v5. Every released schema version must be able to reach the current one — meaning migrations compose stepwise (2→3→4→5), and each step must tolerate any data state its predecessor could have produced.
2. **Migration runs on the launch critical path.** Room and Core Data block the first DB access on migration; a slow migration (rebuilding a large table, per-row rewrites) adds seconds to cold start on old devices and can trigger ANRs or watchdog kills (see `mobile-app-startup-time-optimization.md`, `mobile-app-lifecycle-process-death.md`). Budget and measure migration time on the biggest realistic dataset.
3. **Backups restore newer schemas onto older binaries.** Android auto-backup and iOS encrypted device backups carry the database file across devices and app downgrades. If v5 writes schema the v3 binary cannot parse, restoring a new-phone backup onto an old-phone app produces a crash loop. The standard mitigation: detect a too-new schema version on open and fall back to a "database incompatible" state rather than crash-looping (or set backup rules to exclude/restore-aware-include the DB).
4. **There is no dry-run and no instant rollback.** Unlike a server database, you cannot snapshot-then-migrate: by the time telemetry shows the migration failed, the affected cohort's data is already transformed (or wiped). Hence destructive migrations (`fallbackToDestructiveMigration`, Core Data `NSInferMappingModelAutomaticallyOption` failures silently wiping) must be a deliberate, product-approved decision — never a default.
5. **Multi-process access doubles the risk.** Widgets, notification-service extensions, and app clips opening the same SQLite file can race a migration. Room and Core Data both serialize on the first connection, but a second process reading a half-migrated file with a stale schema expectation is a real corruption vector — open/migrate in one place, and version-gate extensions.

## Room (Android) migration patterns

1. **Always export schema JSON and commit it.** `room.schemaLocation` in KSP options writes a versioned schema snapshot per version; without it, Room cannot generate automated migrations or run `MigrationTestHelper`. Treat the exported schemas like source code — reviewed, versioned, never deleted.
2. **Prefer automated migrations; hand-write the rest.** Room 2.4+ generates correct migrations for additive changes (new table, new column with default) from the schema deltas — `AutoMigration(from = 3, to = 4)`. Non-additive changes need a `@Spec` (deletes/renames) or a manual `Migration(3, 4)` object with explicit SQL; renames without a spec drop data (Room sees delete+add).
3. **Every column addition needs a default or a two-step plan.** Adding a `NOT NULL` column requires a default value in the ALTER statement; anything derived per-row (e.g., backfilling `user_id` from another table) belongs in a manual migration's UPDATE statement, batched if the table is large. Forgetting the version bump on an entity change is the #1 crash: `IllegalStateException: Migration didn't properly handle...` detected only at first open.
4. **Never enable destructive fallback in production.** `fallbackToDestructiveMigration()` wipes the DB when a path is missing — appropriate only for caches with no user data. If you truly must reset, do it explicitly (detect version, copy to a `.bak` first, then drop) so support can recover the file.
5. **Test every path with `MigrationTestHelper`.** Instrumented tests create a DB at version N from the exported schema, insert representative fixture rows, run the migration, and assert both integrity and content (see "Testing migrations" below). Also cover the pre-populated-database case if you ship one: the `createFromAsset` DB's version must be below current and have a migration path like any other origin.

## Core Data (iOS) migration patterns

1. **Lightweight migration covers additive changes — and little else.** Adding entities/attributes, making attributes optional, and renames *with `renamingIdentifier` hints* are lightweight-eligible; type changes, splits, and relationship restructuring need a mapping model or custom code. Enable via `NSMigratePersistentStoresAutomaticallyOption` + `NSInferMappingModelAutomaticallyOption`, but understand its limits rather than treating it as a black box.
2. **Version the model explicitly.** Every schema change = Editor > Add Model Version; shipping a changed model without a new version is the classic "model incompatible with store" crash. The second-to-last-resort is `NSPersistentStoreCoordinator` failing with "Can't find model for source store"; the last resort is a wipe you didn't choose.
3. **Custom migrations run through an `NSMappingModel` or manual store-to-store copy.** For big restructures, the 2020s-Apple-recommended path (WWDC "Evolve your Core Data Schema") is staged migration or a custom migration iterating store entities — do it on a background context, show migration UI if it exceeds ~1s, and never block the main thread for large stores.
4. **NSPersistentContainer changed defaults you must know.** `shouldMigrateStoreAutomatically` and `shouldInferMappingModelAutomatically` default to `true` on `NSPersistentContainer` (many teams don't realize), meaning silent destructive-ish behavior can hide a failed inference. Also, CloudKit-synced stores have *additional* schema constraints (no unique constraints, all relationships optional) — a schema valid locally can break sync entirely.
5. **Watch the store URL and options drift.** Changing store type (SQLite→binary), file location (app container→app group for widgets), or protection class during a migration release creates a second store where users' data "disappears." Any change to where/how the store opens must ship in the same, tested migration as the schema change.

## Cross-platform storage and the app-shell layer

1. **WatermelonDB/Realm ship their own migration syntax — version everything.** JS-side `schemaVersion` + `schema.migrations` (Watermelon) or `Realm.Configuration.schemaVersion` + migration function must be bumped *with* the shipped JS (and OTA updates constrained — see `react-native-over-the-air-updates.md` — because an OTA bundle expecting schema N on a binary that created N-1 is a support incident).
2. **AsyncStorage/MMKV/UserDefaults need a version key, not a schema engine.** Key-value stores have no migration machinery: maintain `storage_version: Int` and hand-write step functions (`migrateV2toV3(keys)`), deleting dead keys and re-shaping values. Unversioned KV stores rot until someone ships a `JSON.parse(undefined)` crash.
3. **Gate the app shell on migration outcome.** The launch path should be: open DB → migrate → on failure, enter a "repair" state (restore from `.bak`, resync from server, or show a recovery screen) instead of a white screen. Log migration duration + outcome (version-from, rows affected) — this telemetry is the only post-hoc visibility you get.
4. **Server-resyncable data changes the risk calculus.** If the local store is a pure cache of server truth, destructive migration costs a resync; if it holds user-created offline content (drafts, queues per `mobile-offline-sync-conflict-resolution.md`), destruction is unrecoverable data loss. Classify each store before choosing strategy — this single decision determines how cautious the migration must be.

## Testing migrations before they ship

1. **Generate fixtures at every released schema version.** Keep per-version fixture builders (`createV2Data(db)`) so tests start from realistic old data, including edge states the old version permitted (nulls, duplicates, orphaned rows the old code could create).
2. **Test all pairwise-to-latest paths, including multi-step skips.** v1→v4 and v3→v4 must both pass; stepwise composition bugs (a v3 default overwritten by the v4 step) only surface in multi-step tests. `MigrationTestHelper` (Room) and store snapshots (Core Data — keep a `.sqlite` fixture per version) make this mechanical.
3. **Assert content, not just integrity.** "Migration didn't crash" is not done: assert the backfilled column's values, the renamed entity's row count, and that user-created rows survived. Count rows before/after — a migration that silently drops a table passes integrity checks.
4. **Test with the largest realistic dataset and on the slowest matrix device.** A migration that takes 80ms with 100 test rows can take 8s with 50k real rows on a low-RAM phone (per `mobile-device-fragmentation-test-matrix.md`). Measure on device, and if slow, chunk the work or show migration progress UI.
5. **Rehearse the downgrade/backup path.** Restore a backup taken on the new version onto a build of the previous version and verify the graceful-incompatibility branch, not a crash loop. This is the scenario QA never runs and support always gets.

## Related

- `android-room-database.md`
- `ios-core-data-patterns.md`
- `react-native-mmkv-storage.md`
- `mobile-offline-sync-conflict-resolution.md`
- `mobile-app-startup-time-optimization.md`
