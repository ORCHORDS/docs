# systemd-tmpfiles age cleanup safety

**Issue:** Automated cleanup can delete live sockets, caches, or in-progress runner artifacts when age semantics and exclusions are assumed rather than tested.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

Keep tmpfiles rules in version control, scope paths narrowly, select entry types and age fields deliberately, and use exclusion rules for subtrees owned by another lifecycle. Run create, clean, and remove as separate reviewed operations. Prefer application locks where supported and never target an unresolved variable or broad root.

## Verification

Use `systemd-tmpfiles --dry-run` or equivalent supported test mode for the deployed version, create fixtures with controlled timestamps and locks, then confirm only expired targets are selected. Test boot and timer behavior.

## Gotchas

Age evaluation can consider multiple timestamps and filesystem behavior. `--clean`, `--remove`, and `--purge` are different operations; a rule safe for one is not automatically safe for another.

## Official sources

- https://www.freedesktop.org/software/systemd/man/latest/tmpfiles.d.html
- https://www.freedesktop.org/software/systemd/man/latest/systemd-tmpfiles.html
