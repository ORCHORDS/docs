# multi-agent-repo-halting

**Issue:** Several AIs and automation loops work the same repository (owner + Claude fleet + Codex reviewer + ZCode sessions + CI). When the owner says "stop" or a cancel arrives, an agent that finishes "just one more thing" first races the other actors: pushes collide, half-states ship, and a stopped job un-stops itself on the next trigger. Learned operating the ORCHORDS multi-AI workflow across example project, example project, and example project.

**Date:** 2026-08-15
**Repo:** ORCHORDS (multi-repo workflow)
**Author:** ORCHORDS
**Status:** published

## The halting rules

1. **Stop means halt NOW, mid-edit** — no "finish this function first". Another actor may be mid-flight on the same tree; your completion is their conflict.
2. **Stop means stop EVERYTHING you spawned** — background shells, agents, cron jobs, watch loops. An orphaned watcher un-does the stop on its next tick.
3. **Never push after a stop** — a local un-pushed change is recoverable/discussable; a pushed one forces every other actor to reconcile with it.
4. **Leave a clean sign-out** — one comment/note stating where you stopped (branch, files touched, next step) so the next actor resumes instead of guessing.
5. **Cancel triggers apply to scheduled work too** — a cron that fires after a stop is the classic un-stop; delete/disable the schedule with the same urgency as killing the foreground work.

## Coordination mechanics that prevent races

1. **One writer per branch** — actors claim branches/files; the claim is visible (issue assignee, branch prefix) before the first commit.
2. **Status comments before pushes** — the other actors' next read is the issue thread; push-after-comment keeps everyone reconciled.
3. **Long jobs announce their window** — "building for ~10 min on branch X" lets others schedule around it.
4. **CI is the neutral arbiter** — nobody force-pushes main to "fix" a race; conflicts go through the same PR flow as everything else.
5. **The owner's channel outranks everything** — a stop from the owner beats an in-flight swarm target, a cron schedule, and a "nearly done" edit, unconditionally.

## Failure modes

1. **The courtesy finish** — "let me just complete this PR" is the most common violation; it converts a stop into a race.
2. **Orphaned background tasks** — the foreground obeyed, the logcat/cron/watcher kept mutating state.
3. **Assuming you're the only actor** — pushing without checking `git fetch` first because "nobody else is on this".
4. **Re-starting on a trigger after a manual stop** — automation that doesn't distinguish "cancelled by owner" from "finished normally".
5. **Silent sign-out** — stopping without a note leaves the next actor to re-derive your half-state from a dirty working tree.

## Related

- `../issues/master-issue-checkoff-followup-protocol.md` (status comments as the coordination substrate)
- `smart-merge` concepts in `../ai-ml/smart-merge-fleet-writes.md`
