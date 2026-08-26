# Node.js permission-model native-addon boundary

**Issue**

Native addons can escape JavaScript-level assumptions and therefore require an explicit permission decision under Node's permission model.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Run supported tools with the permission model enabled and omit addon permission by default.
- Allow native addons only for pinned, reviewed dependencies.
- Keep filesystem, child-process, worker, and addon permissions separately minimal.

## Verification

1. Attempt loading allowed and denied addons.
2. Exercise transitive optional native dependencies.
3. Verify denial is surfaced without silently switching to an unreviewed fallback.

## Gotchas

- The permission model is a seat belt, not a sandbox.
- An allowed addon executes native code in-process.
- Build-time addon scripts are a separate boundary.

## Official source

- [Official documentation](https://nodejs.org/api/permissions.html)
