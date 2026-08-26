# master-issue-pattern

**Issue:** A project phase has 5+ deliverables that will be worked across multiple sessions and by multiple agents. Work items get lost between sessions, two agents solve the same thing, and nobody can answer "what's left?". The team needs the pattern for a single GitHub master (tracking) issue that holds the whole phase.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## When to create a master issue #<number>. **5+ distinct deliverables.** Below that, a normal issue suffices; above it, per-item issues without a parent lose cohesion.
2. **Multi-session work.** The issue body and its comments ARE the cross-session memory — a new agent reads body + last 3 comments and is fully briefed.
3. **One phase = one master.** Search `gh issue list --search "master" --state all` first; extend the existing one, never create an overlapping second.
4. **State must survive humans and AIs.** Masters work when different agents (and the owner) take turns; the checkbox state is the single source of truth.

## Body structure that works

1. **Goal line.** One verifiable sentence ("runner CI under 5 min with zero lost checks").
2. **Scope block.** What is IN and explicitly OUT — prevents scope creep arguments later.
3. **Status line.** `Started · Last update · Progress: k/N`, edited in the same commit that ticks a box.
4. **Stage-grouped checkboxes.** Discovery → Implementation → Verification; the checkbox order is the execution order.
5. **Decision log table.** Date / Decision / Why — cheap insurance against re-litigating settled choices.

## The two tracking mechanisms

1. **Plain checkboxes** (`- [ ]` / `- [x]`) render a progress bar and suit small steps that never need their own thread.
2. **Referenced-issue checkboxes** (`- [ ] #101`) auto-check when issue #<number> closes — use for anything an agent will branch + PR on.
3. **Native sub-issues** (`gh issue create --parent 266`, `gh issue edit 266 --add-sub-issue #<number>`) are GitHub's replacement for retired tasklist blocks: dedicated section, "Tracked by" backlink, progress rollup into Projects.
4. **Limits:** up to 100 sub-issues per parent, 8 nesting levels.
5. **Swarm rule:** every worker claims a sub-issue number, never a bare checkbox — the number is the coordination key.

## Creation commands

1. `gh issue create --title "Master: <phase> — <goal>" --label tracking --body-file master-body.md`
2. `gh issue create --title "<child>" --parent 266` — child is born linked.
3. `gh issue edit 266 --add-sub-issue #<number>,341` — attach existing issues in bulk.
4. `gh issue edit 266 --remove-sub-issue #<number>` — detach without closing.
5. `gh issue view 266` — body + sub-issue progress in one read.

## Closing the master

1. **All boxes ticked** (children closed, referenced checkboxes auto-ticked).
2. **Closing summary comment** — what shipped, PR list, remaining known gaps re-filed as new issues.
3. `gh issue close 266 --reason completed`.
4. **New work goes to a NEW master** — comments on closed issues are invisible in default views.
5. Never close with children still open — they orphan; move them explicitly first.

## Related

- `master-issue-checkoff-followup-protocol.md`
- `project-stage-issue-flow-md-sync.md`
