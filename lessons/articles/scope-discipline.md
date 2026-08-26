# scope-discipline

**Issue:** Don't expand scope mid-PR
**Date:** 2026-08-09
**Status:** documented (process rule)

## Symptom
You're fixing a bug. While you're in the file, you notice
unrelated tech debt. You "drive-by" refactor it. Your PR now
touches 12 files. The review is hard. CI fails on the refactor.
You revert. Time wasted: 2 hours.

## Root cause
**The urge to fix everything at once is the enemy of shipping.**
Scope creep during a PR multiplies the risk:
- Each additional change is a place for a bug
- The reviewer has to context-switch between unrelated changes
- The PR is harder to revert (which change broke things?)

**Source:** Kent Beck — "Make it work, make it right, make it fast":
https://www.facebook.com/notes/kent-beck/make-it-work-make-it-right-make-it-fast/2395674031941189/

> "Make it work, then make it right, then make it fast. ... The
> order is important."

## Fix
Three rules:

### Rule 1: One PR = one concern
If the PR title can't fit in 60 characters without "and," split it.

✅ `fix(do-batch): pass env (not env.DB) to writeAudit at 13 call sites`
✅ `feat(do-chain): route writeAudit through per-tenant Durable Object`
❌ `fix(do): various audit chain improvements`

### Rule 2: If you see adjacent tech debt, file a follow-up
Don't fix it in the same PR. Add a comment `// TODO: <issue #>`
in the code. Open a separate issue. Move on.

```ts
// TODO: refactor this to use the new DO pattern (issue #<number>)
const oldApproach = ...;
```

### Rule 3: Drive-by fixes are allowed IF they're a 1-line change
With a clear comment in the PR description.

```ts
// In the same PR, added 1-line fix for an obvious bug:
// `if (!user) return null;` was missing. See issue #<number>.
```

Anything more than 1 line + comment = separate PR.

## Verification
- **Test:** PR diff is < 200 lines (rule of thumb; adjust per repo)
- **Test:** PR title fits in 60 chars without "and"
- **Audit:** Code review checklist includes "scope is right"

## Gotchas
- **"While I'm here" is a red flag.** If you find yourself saying
  this, stop. File a follow-up.
- **Refactors in a bug-fix PR are sneaky scope creep.** Even if
  "the refactor makes the bug fix cleaner," it doubles the
  review surface. Do them separately.
- **The exception: clearly related changes** (e.g. updating a
  function signature requires updating all callers — that's
  one concern, not scope creep).
- **"Boy Scout Rule"** (leave the code cleaner than you found it)
  is NOT a license for drive-by refactors. It's a license for
  one-line fixes you encounter.

## Related
- `lazy-fail-evidence-discipline.md` (process rule)
- `user-pivot-rule.md` (when scope changes are user-requested)
- Kent Beck: https://www.facebook.com/notes/kent-beck/make-it-work-make-it-right-make-it-fast/2395674031941189/
