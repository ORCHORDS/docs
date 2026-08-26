# Git rerere reused conflict-resolution review

**Issue:** Long-lived branches repeatedly encounter similar conflicts, wasting time, but an automatically reused resolution can become semantically wrong as surrounding code changes.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

With `rerere.enabled`, Git records a conflicted automerge and its manual resolution, then can reuse that resolution for a corresponding later conflict during merge or rebase. Git leaves the index for final review, so reuse never removes the obligation to inspect, test, and stage the result.

Treat rerere records as local assistance, not trusted project policy. Use `git rerere diff`, `status`, `remaining`, and `forget` to inspect and correct state.

## Controls

- Review the full combined diff after reuse.
- Run the same required checks as for a manual resolution.
- Do not share rerere state across unrelated trust domains.
- Forget a resolution when semantics changed.
- Garbage-collect old records under a deliberate retention policy.
- Preserve a clean abort path for merge and rebase.

## Verification

1. Resolve and record a controlled conflict.
2. Recreate it and confirm reuse without automatic staging.
3. Change surrounding semantics and verify review catches a stale resolution.
4. Exercise `forget` and resolve again.
5. Test abort behavior.

## Sources

- [Git: git-rerere](https://git-scm.com/docs/git-rerere)
- [Git: merge](https://git-scm.com/docs/git-merge)
