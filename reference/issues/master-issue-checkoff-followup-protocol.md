# master-issue-checkoff-followup-protocol

**Issue:** A master tracking issue exists, but agents check boxes when PRs open (not merge), status comments are sporadic, and dropped items vanish silently. Progress lies, sessions duplicate merged work. The team needs the checkoff and follow-up discipline.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Checkoff discipline

1. **Check on MERGE, not PR-open.** An item with an open PR is still `- [ ]`; tick it only when the PR lands on main.
2. **Referenced checkboxes self-tick** — `- [ ] #101` completes automatically when #101 closes; verify it did, and edit plain checkboxes by hand.
3. **Strike dropped items, never delete:** `- [ ] ~~Obsolete~~ (dropped 2026-08-20, superseded by #400)` — future readers must distinguish dropped from done.
4. **Regressions un-check.** A re-opened (or re-filed) child puts the master back to incomplete.
5. **Same-edit Status bump.** The edit that ticks a box also updates the `Last update` date and `Progress: k/N` line — one `gh issue edit`, both changes.

## The gh edit cycle

1. `gh issue view 266 --json body --jq .body > body.md` — fetch current body.
2. Edit `body.md` — tick/strike boxes, bump Status line.
3. `gh issue edit 266 --body-file body.md` — push back.
4. Never hand-merge an older copy over a newer body — always fetch fresh in the same session.
5. Checkboxes in **comments** render but do NOT feed the issue progress bar — only body edits move the bar.

## Dated status comments (the cross-session memory)

1. **End of every session + every blocker**, post a comment on the master.
2. Fixed sections: date line, **Done / In flight / Blockers / Next / Progress** — even when a section says "none".
3. **Master for phase state, child for technical detail** — don't put per-item specifics in the master thread.
4. **Post BEFORE pushing** when another AI or the owner may touch the repo — nobody works on stale state.
5. Blockers state a numbered issue + the exact owner action needed (`#326 needs GHAS billing, owner-only`), never a vague note.

## Reading order for a new session

1. Master body (Goal, Scope, Status, checkboxes) — current state.
2. Last 3 comments — recent deltas and blockers.
3. Open children referenced by unchecked boxes — the actual backlog.
4. CONTRIBUTING/README — repo-specific rules that override defaults.
5. Only then start work; claim one sub-issue before touching anything.

## Anti-patterns

1. Ticking on PR-open (progress lies, work gets duplicated).
2. Deleting dropped items (history becomes unauditable).
3. Sporadic comments (next session re-auditors everything from scratch).
4. Closing master with open children (orphans).
5. Logging new work on a closed master (invisible in default views).

## Related

- `master-issue-pattern.md`
- `project-stage-issue-flow-md-sync.md`
