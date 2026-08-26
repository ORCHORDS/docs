# Git ref inventory pagination with start-after

**Issue**

Large reference inventories need deterministic pagination; naive line splitting or mutable traversal can duplicate or omit refs.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Sort by refname and use `--start-after` only with a compatible ordering contract.
- Persist the last complete refname, not a display-formatted label.
- Treat concurrent ref mutation as a new snapshot requirement.

## Verification

1. Page synthetic refs across boundary names and Unicode.
2. Add/delete refs between pages and detect snapshot drift.
3. Compare concatenated pages with one full inventory.

## Gotchas

- Start-after is incompatible with some sort/filter combinations.
- Ref names are bytes with Git constraints, not arbitrary UI strings.
- Pagination is not a consistency snapshot.

## Official source

- [Official documentation](https://git-scm.com/docs/git-for-each-ref)
