# Android AppSearch schema migration and visibility

**Issue:** An app changes an AppSearch schema as if it were a local data-class refactor. `setSchema` then rejects incompatible changes, force override deletes data, or a visibility change exposes documents to another package or system surface.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Schema boundary

An `AppSearchSession` operates over a database and applies a `SetSchemaRequest` before documents using those schema types are written. Schema version, compatibility, migration, and visibility are deployment data—not merely Kotlin type definitions.

Never use force override as a routine production migration. It can remove incompatible schema types and their documents. Reserve it for an explicit reset flow whose data-loss impact is acceptable and measured.

## Rollout pattern

1. Open the intended database namespace and read the current schema/version before constructing the new request.
2. Define stable schema type and property names. A class or package rename must not accidentally rename persisted types.
3. Classify every change as compatible or requiring migration. Supply registered migrators for affected schema types and set a monotonically managed version.
4. Make migrations deterministic, bounded, and tolerant of documents created by every supported previous version. Do not perform network I/O inside document transforms.
5. Apply `setSchema` and wait for its asynchronous result before writing documents that require the new schema.
6. Inspect failures and migration statistics. Keep the app usable or read-only; do not retry with force override automatically.
7. Backfill/index data in controlled batches after the structural change when work cannot safely fit the migration.
8. Record database name, old/new version, changed types, migrated/failed counts, duration, and app build.

## Visibility controls

Default to private. Schema visibility methods that allow package access or system display change who can discover data. Bind any package visibility to the documented package identity/certificate mechanism, review exposed properties for personal data, and test uninstall/reinstall and signing-key rotation.

Keep search visibility distinct from Android component export rules and from runtime permissions. A queryable schema does not authorize every result to be shown in every UI context.

## Verification

Test fresh install, every supported upgrade path, downgrade/re-upgrade, interrupted startup, corrupted/invalid documents, signing variants, multiple databases, private defaults, explicitly visible schemas, and an unavailable target package. Seed enough data to exercise timeout and storage pressure.

Assert no document count loss unless the migration specification explicitly calls for deletion. Compare sampled old/new documents and query results, not only a successful future.

## Gotchas

- Schema version alone does not migrate data; registered migration logic and compatible definitions do.
- Reusing a schema type name with different semantics creates silent query errors.
- Visibility is configured at schema-type granularity and needs a privacy review.
- AppSearch implementation and feature availability can vary by backend/device; test supported Android versions.

## Sources

- [AndroidX SetSchemaRequest reference](https://developer.android.com/reference/androidx/appsearch/app/SetSchemaRequest)
- [AndroidX AppSearchSession reference](https://developer.android.com/reference/androidx/appsearch/app/AppSearchSession)
