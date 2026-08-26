# github-sub-issues-tasklists

**Issue:** Breaking a large issue into trackable pieces historically meant markdown checkbox lists inside the issue body — invisible to search, unassignable, unlabelable, and never syncing with the real Issues that represented the work. GitHub's sub-issues (public preview late 2024, general availability with the May 2025 "Evolving GitHub Issues and Projects" launch) replace that with a real parent/child hierarchy among actual issues, plus a REST API and Projects integration. Teams migrating from markdown tasklists, tracking epics, or scripting issue decomposition need the new model, its limits, and its 2025 behavior changes (inheritance of Project/Milestone, cross-repo parents) to use it without surprises.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The Sub-Issues Model

1. **Real issues as children.** A sub-issue is an ordinary issue attached to a parent via a dedicated relationship, not a checkbox line. Each child keeps its own assignees, labels, state, and comments; the parent renders a progress bar ("3 of 7 done") at the top of the issue page.
2. **Hierarchy limits.** The hierarchy is parent → children, one level deep: a sub-issue cannot itself have sub-issues in the UI/API as of the 2025 GA, so model epics → tasks → subtasks using Projects fields rather than nesting further.
3. **Replaces markdown tasklists.** Old-style tasklist items that were converted become real issues; unconverted checkbox lists still render but are the deprecated path. New tooling should target the sub-issue API, not body-editing hacks that rewrite checkboxes.
4. **Issue types complement it.** The same GA release brought issue types (Bug, Feature, Task, custom) and advanced search on them; combining a typed parent (e.g., custom type "Epic") with typed children is the supported epic pattern.
5. **Cross-repository support.** Since the September 2025 changelog, sub-issues can live in different repositories (and even organizations) from their parent, with the repository name shown inline — enabling a central planning repo to decompose work across service repos.

## REST API Operations

1. **List and create.** `GET /repos/{owner}/{repo}/issues/{issue_number}/sub_issues` lists children; `POST` to the same path with `sub_issue_id` attaches an existing issue as a child. There is no "create-and-attach" single call — create the child issue first, then link it.
2. **Reprioritize.** `PATCH .../sub_issues/priority` with `sub_issue_id` and a `position` (FIRST, LAST, or after a given `sub_issue_id`) reorders children within the parent, matching the UI's drag-and-drop.
3. **Remove and introspect.** `DELETE` detaches a child without closing it; `GET /repos/{owner}/{repo}/issues/{issue_number}/sub_issues/parent` finds the parent of an issue, which is the way to detect hierarchy when scanning flat issue lists.
4. **Set-with-POST gotcha.** The attach endpoint requires `Content-Type: application/json` and the child issue's numeric id (not its number in another repo), and adding sub-issues has restrictions when the child lives outside the parent's repository/organization membership — test cross-org links before relying on them (community discussion #182223 tracks the edge cases).
5. **GraphQL still richer.** Fields like `parent` and `subIssues` remain available (and were the only option pre-2025); the Projects REST API added in the same September 2025 release closes the remaining gap for scripts that previously had to speak GraphQL.

## 2025 Behavior Changes to Know

1. **Project inheritance.** Sub-issues now inherit the parent's Project and Milestone by default (September 2025). Adding a parent's child to a board no longer duplicates manual bookkeeping, but scripts that added sub-issues to projects themselves may now see double-adds or conflicts.
2. **Closing semantics.** Closing all children does not auto-close the parent, and closing the parent does not close children; automation that wants either behavior must implement it (Actions reacting to `issues` events walking the hierarchy via the parent endpoint).
3. **Projects item limits raised.** The GA raised Projects item limits, making board-per-epic patterns viable at monorepo scale without hitting the old caps mid-quarter.
4. **Notifications.** Subscribers of the parent are not auto-subscribed to children; triage automation should add watchers or rely on team-level notification settings rather than assuming propagation.

## Adoption Playbook

1. **Migrate markdown tasklists deliberately.** Convert each checkbox line into a real sub-issue (script: parse the body, create issues, attach, then remove the checklist), keeping the original text as each child's opening description; do it per-repo with a dry-run flag.
2. **Encode an epic convention.** Standardize: parent = custom type "Epic" or feature issue, children = typed tasks, estimation and iteration fields live on children only; document it in the repo's contributing notes so Copilot and humans follow the same shape.
3. **Automate progress rollups.** Use a scheduled workflow or webhook that reads each parent's sub-issue states and updates a Projects number field or posts a summary comment; the UI progress bar covers humans, but dashboards need the API.
4. **Guard the hierarchy in CI.** If sub-issues are required for stories above a size threshold, enforce with label-bot logic (the label/automation patterns in `github-labels-automation.md`) rather than trusting authors.

## Pitfalls

1. **One-level ceiling.** Teams nesting three levels deep via the UI quickly find sub-issues cannot have sub-issues; model the third level as labels or Projects grouping before the structure ossifies.
2. **Cross-org attach failures.** Attaching children from repos outside the parent's org can fail silently or with 422 depending on membership; keep epic trees inside one org where possible.
3. **Body-edit clobbering.** Legacy scripts that rewrite issue bodies to manage checklists can destroy the new sub-issue section; retire any automation that touches the sub-issue block of the body.
4. **Search blind spots.** Advanced search has first-class filters for much of Issues but hierarchies are best queried via the parent/sub_issues endpoints — do not assume `is:issue parent:*` style qualifiers exist.
