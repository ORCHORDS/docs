# Git mailmap blob governance

**Issue**

Loading mailmap data from a configured blob can change contributor identity presentation without a working-tree file.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Pin the reviewed blob/ref and scope configuration.
- Treat identity mapping as presentation, not commit rewriting.
- Audit changes before release-note or ownership generation.

## Verification

1. Compare log and shortlog with file and blob mappings.
2. Test missing and malformed blobs.
3. Verify signatures and original commit identities remain intact.

## Gotchas

- Mutable refs change results.
- Mailmap does not alter objects.
- Mappings can merge distinct people incorrectly.

## Official source

- [Official documentation](https://git-scm.com/docs/gitmailmap)
