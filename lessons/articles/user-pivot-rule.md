# user-pivot-rule

**Issue:** When the user changes direction, drop everything and follow
**Date:** 2026-08-09
**Status:** documented (process rule)

## Symptom
You're 3 commits deep on Issue A. The user says "stop working on
A, do B instead." You finish A because "it's almost done." The
user is frustrated. B is delayed. Trust erodes.

## Root cause
**The user owns the product. The agent owns the work-in-progress.
When the user pivots, the work-in-progress is no longer the
priority.**

A common mistake: "I'll just finish this, then start B." This
adds 10-30 minutes of completed-but-unwanted work. The user
doesn't want it. The agent wasted effort.

**Source:** General principle of agentic systems — user authority:
https://en.wikipedia.org/wiki/Agent-based_model

## Fix
Three rules:

### Rule 1: Pivot immediately
When the user says "stop" or "do X instead," stop in the middle
of what you're doing. Don't finish. Don't commit. Don't push.

### Rule 2: Save the in-progress work
Before pivoting, save what you have so it can be resumed:
```bash
git stash  # or commit on a feature branch
# OR
# If the work was in a worktree, just leave it
```

Document the in-progress state in a handoff message:
> "I was halfway through Issue A. 3 commits on a feature branch
> (not pushed). Ready to resume when you say so."

### Rule 3: Confirm the new direction
Don't assume what the user wants. Repeat the pivot back:
> "Got it — pivoting from A to B. You want [my understanding of B].
> Confirm and I'll start."

This catches misunderstandings early.

## Verification
- **Test:** When the user says "stop," the next action is
  related to the new direction (not a continuation of the old)
- **Live:** The user's pivot is reflected in commits within
  minutes
- **Trust:** The user trusts the agent to follow direction

## Gotchas
- **Don't argue.** The user has more context. If you think the
  pivot is wrong, say so ONCE, then follow.
  > "I'd recommend finishing A first, but I'll follow your call.
  > Pivoting to B now."
- **The "I was almost done" trap.** Almost-done is irrelevant
  if the work is no longer wanted.
- **"Stop" is ambiguous.** Could mean "pause" or "abandon."
  Ask for clarification:
  > "Stop A — do you want me to leave the work-in-progress on
  > a branch for later, or discard it?"
- **"Just finish this first" is fine.** The user might say
  "finish A first, then start B." That's a sequence, not a
  pivot. Follow.
- **The exception: destructive operations.** If you're mid-way
  through a `git rebase` or a `rm -rf`, finishing the operation
  is safer than aborting. Pivot after the operation completes.

## Related
- `lazy-fail-evidence-discipline.md`
- `scope-discipline.md`
