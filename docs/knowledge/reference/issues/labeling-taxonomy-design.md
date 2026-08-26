# labeling-taxonomy-design

**Issue:** The repo has 74 labels accumulated over four years: three variants of "bug" (`bug`, `type/bug`, `defect`), priority words nobody defines, area labels for modules that were renamed or deleted, and one-off joke labels applied to exactly one issue. Contributors cannot guess the right labels, triagers apply them inconsistently, and no query like `is:issue is:open label:bug -label:triaged` returns anything trustworthy. Labels were meant to make the tracker searchable; instead the taxonomy has become its own unmanaged codebase. The team needs a deliberate, small, enforced label scheme where every label has one dimension, one definition, and an owner.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Design principles

1. **One label, one dimension.** A label should encode exactly one fact — kind, area, or state — never a blend like `urgent-backend-bug` that makes filtering impossible once two of the three facts change.
2. **Prefix by category.** Namespaced prefixes (`kind:`, `area:`, `state:`, `prio:`) keep the picker scannable and let humans and automation parse the taxonomy structurally, as recommended by widely-cited label guides (Sane GitHub Labels, trstringer's prefix-enforcement writeups).
3. **Mutual exclusion within a dimension.** Two `kind:` labels on one issue is a modeling error; the design should make conflicts visible (or impossible via automation) rather than tolerable.
4. **Small by design.** A workable starting set is roughly 5 kind labels, one per source area, and a handful of state markers; if the list no longer fits on one screen, it will not be applied consistently.
5. **Prefer native features over labels.** GitHub issue types, milestones, assignees, and Projects fields now encode kind, iteration, and ownership natively — pushing those dimensions out of labels removes a whole class of drift.
6. **Define every label in its description.** The label's description field carries the one-sentence definition and the rule for when NOT to use it; undefined labels converge to meaning "something the maintainer felt".

## Reference scheme

1. **`kind:bug` / `kind:feature` / `kind:chore` / `kind:docs` / `kind:question`.** The type axis, mirroring native issue types so reports classify cleanly at creation.
2. **`area:<component>` per load-bearing module.** Only for components real enough to own code — one area label per issue, renamed when the module renames.
3. **`state:triaged`, `state:confirmed`, `state:blocked`, `state:parked`.** Lifecycle facts a query can trust; `state:parked` also doubles as the stale-bot exemption set.
4. **`needs:repro`, `needs:info`, `needs:design`.** Signals for what the issue is waiting on, which converts "ignored" into "blocked on X".
5. **`good-first-issue` and `help-wanted` as capacity signals.** Applied only when a maintainer has actually verified the task is scoped and doable — these are promises, not categories.
6. **No priority labels until forced.** Generic `low/medium/high` labels become meaningless without shared calibration; when prioritization is real, prefer an ordered Project field or milestones, which carry sequence natively.

## Migration and pruning

1. **Inventory and group first.** The OpenRefine-style cleanup: export all labels with usage counts, group into candidate dimensions, then delete — grouping before deleting prevents recreating the same mess.
2. **Delete zero- and one-use labels on sight.** A label applied to one issue is a comment wearing a costume; reclaim it and say the thing in prose.
3. **Merge synonyms with a scripted rename.** `bug`/`type/bug`/`defect` collapse into one canonical label via API or a bulk tool like git-labelmaker; announce the merge so saved queries get updated.
4. **Retire area labels with their modules.** When code is deleted or restructured, its `area:` label dies in the same PR — stale area labels are dead documentation.
5. **Freeze additions behind review.** New labels require a proposal (what dimension, what definition, what query uses it) approved in a maintainer channel; uncontrolled label creation is how the 74-label graveyard happened.

## Enforcement and automation

1. **Check labels in CI or workflows.** A lightweight action can flag issues missing a `kind:` label or carrying conflicting dimension values, and auto-apply defaults where safe.
2. **Enforce the prefix convention.** Automation can reject non-conforming labels and lint label-adding workflows, keeping the namespace parseable by tooling.
3. **Back taxonomy with saved queries.** Publish the canonical filter set (triage inbox, confirmed bugs by area) so the taxonomy's value is visible daily and breakage is noticed immediately.
4. **Report label drift quarterly.** A short script listing labels by usage and age feeds the pruning ritual; drift you measure is drift you control.
5. **Document the taxonomy in-repo.** A `docs/labels.md` table (label, definition, dimension, owner) is referenced from CONTRIBUTING so external contributors apply labels correctly the first time.

## Anti-patterns

1. **Status-board labels like `in-progress` or `done`.** These duplicate assignees/Projects state and instantly rot; if the board and the labels disagree, both are wrong.
2. **Severity inside labels.** Severity belongs to triage fields with definitions (see the existing severity-classification article), not to an open label namespace where everyone invents their own scale.
3. **Person-named labels (`maria-looking`).** Ownership is what assignees are for; person labels outlive the person every time.
4. **Mood labels (`annoying`, `wontfix-maybe`).** Anything that cannot appear in a trustworthy query does not deserve a label — put it in the comment thread.
