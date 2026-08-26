# Desktop file replacement must respect platform locking semantics

**Issue**

Replacing a preferences database or downloaded asset with rename-based logic behaves differently when antivirus, indexers, preview handlers, or another app instance holds the destination open.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Write new contents to a same-volume temporary file, flush it, validate it, then use the platform's supported replacement primitive.
- Lock the logical resource, not only a temporary pathname; include process identity and stale-lock recovery rules.
- Keep recovery metadata beside the durable target and never assume rename across volumes is atomic.
- On Windows, handle sharing violations with bounded retry and preserve the original file until replacement succeeds.
- Do not use advisory locks as an authorization boundary.

## Verification

1. Kill the process after each write, flush, rename, directory-sync, and cleanup boundary.
2. Hold source or destination handles with different sharing flags and verify bounded failure behavior.
3. Test network shares, removable media, case-insensitive paths, and disk-full conditions separately from local system disks.

## Gotchas

- Atomic namespace replacement does not prove bytes reached stable storage.
- Unix advisory locks require cooperating processes.
- Deleting a lock file does not release a live kernel lock.
- Cross-volume moves can degrade to copy-and-delete.

## Official sources

- [Microsoft ReplaceFile](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-replacefilew)
- [Apple File System Programming Guide](https://developer.apple.com/library/archive/documentation/FileManagement/Conceptual/FileSystemProgrammingGuide/)
