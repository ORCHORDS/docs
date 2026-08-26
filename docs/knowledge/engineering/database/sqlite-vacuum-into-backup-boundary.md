# SQLite VACUUM INTO backup boundary

**Issue:** Treating `VACUUM INTO` as an ordinary file copy can publish a partial backup after interruption, overwrite the wrong path, or hide the trade-off between a compact snapshot and an incremental backup.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Write to a newly created or empty destination on a trusted filesystem; reject caller-controlled paths, symlinks, and an existing non-empty file.
- Use `VACUUM INTO` when a compact, deleted-content-purged snapshot is wanted. Prefer SQLite's backup API when incremental copying or lower CPU cost matters.
- Budget free space and I/O, keep the source connection free of unfinished statements, and use an explicit durability policy. With source `synchronous` set to `NORMAL` or `FULL`, SQLite syncs the completed output.
- Publish the destination only after the command succeeds and a separate connection opens it successfully. Never promote the file left by an interrupted command.
- Do not use implicit rowids as durable identifiers; vacuuming may change rowids for tables without an explicit `INTEGER PRIMARY KEY`.

## Verification

Run `PRAGMA quick_check` or `integrity_check` on the output, compare required schema/application metadata and row-count invariants, record a checksum, and restore it in an isolated test. Exercise an existing destination, insufficient space, an open statement, cancellation, and process or host interruption.

## Gotchas

- The output is a transactionally consistent snapshot, but an interrupted output can be incomplete or corrupt.
- The source database is unchanged; retention and encryption of the new file are separate controls.
- A successful compact snapshot is not proof that the restore procedure meets RPO and RTO.

## Official source

- [SQLite VACUUM and VACUUM INTO](https://sqlite.org/lang_vacuum.html)
