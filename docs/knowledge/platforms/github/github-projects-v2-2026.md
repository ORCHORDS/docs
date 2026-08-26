# github-projects-v2-2026

**Issue:** The org tracks work spread across a dozen repos using a mix of per-repo milestones, a spreadsheet, and stale label queries. Nobody can answer "what is in flight this iteration?" without manual stitching. GitHub Projects (the new Projects experience, formerly "Projects v2") can union issues, PRs, and draft items from many repos into one table/board/roadmap, but teams that only touch the UI end up manually triaging every new issue into the project and manually moving Status — which decays within weeks. The durable setup combines built-in workflows, custom fields (especially iterations), and API-driven automation.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Structural choices before automation

1. **Org-level vs repo-level project.** Create the project at org level (organization projects) so items from any repo can be added; repo-level projects are fine for single-repo teams but cannot become the cross-repo portfolio view that motivated the migration.
2. **Field model drives everything.** Built-in fields (Title, Assignees, Labels, Milestone, Repository, Reviewer status, Linked pull requests, Tracked issues) sync automatically from the underlying issue/PR. Custom field types are: single select (Status-like workflows), date, number, text, and iteration. Choose custom field names deliberately — renames are easy but automations reference fields by ID, not name.
3. **Status is a single-select field.** Unlike classic Projects, the Todo/In Progress/Done column behavior is just a single-select field named Status; built-in workflows key off it. You can add extra values (Blocked, In Review) and reorder them.
4. **Iterations beat milestones for cadence.** Iteration fields auto-generate repeating periods (1–2 weeks typical) with start/end dates, optional break weeks, and a current-iteration default. Unlike milestones (`github-milestone-tracking.md`), iterations live in the project, support upcoming/current/completed color states, and aren't duplicated per repo.
5. **Views are saved slices.** Table, board, and roadmap views with per-view grouping (by Status, by Iteration, by repo), filtering, sorting, and field visibility. Group-by + filter per team is cheaper than maintaining many projects.

## Built-in workflows

1. **Auto-add.** A workflow that pulls new issues/PRs from chosen repositories into the project when they match a filter (e.g. `label:tracked`, or everything). This replaces the "someone forgot to add it" failure mode; scope by repo plus filter to keep noise out.
2. **Status: set to Todo on add.** Combined with auto-add, every ingested item starts in Todo — no manual column hygiene for intake.
3. **Auto-close / Done transitions.** Default workflows set Status to Done when an item's issue is closed or its PR is merged; a companion workflow can close the underlying issue when its project Status changes to Done (issue closed from the board).
4. **Auto-archive.** Archives items matching a filter (e.g. Status is Done for N days) to keep active views clean without periodic purge rituals.
5. **Editing workflows.** Project → kebab menu (⋮) → Workflows → edit a default workflow's target field/values → "Save and turn on workflow". Each workflow shows its trigger and the field it writes — audit these after any Status value rename.

## API and Actions automation

1. **`actions/add-to-project`.** The first-party action adds issues/PRs to a project by URL/id, with a labeled-input for an App token (GitHub App or PAT with project scope). Pair with `alex-page/githlabel` or `dorny/paths-filter` for conditional intake rules too complex for the built-in filter syntax.
2. **GraphQL mutations are the write path.** Core mutations: `addProjectV2ItemById` (add issue/PR/draft), `updateProjectV2ItemFieldValue` (set single-select/iteration/date/number/text on an item), `deleteProjectV2Item`, and `archiveProjectV2Item`. Reads go through `ProjectV2` / `ProjectV2Field` / `ProjectV2Item` queries.
3. **Field IDs, not names.** `updateProjectV2ItemFieldValue` takes the field's ID and the single-select option ID — query the project's fields first, cache the ID map, and resolve names to IDs at runtime; hard-coded IDs break when fields are recreated.
4. **Draft items for unbaked work.** `addProjectV2DraftIssue` creates card-only items (no issue yet) — useful for roadmap placeholders that later get converted to real issues via the UI's "Convert to issue".
5. **Token scopes.** Automation needs a token with project permissions: classic PAT with `repo,write:org` + project scope, fine-grained PAT with Projects write, or (best) a GitHub App installation token — see `github-apps-installation-tokens.md` and `github-fine-grained-personal-access-tokens.md` for the trade-offs.
6. **Insights for reporting.** Project Insights (burn-up, cumulative flow, configurable charts over fields like Status/Iteration) replace the spreadsheet dashboard; snapshots are computed server-side so charts stay live without scraping.

## Adoption and hygiene checklist

1. **Seed, then automate.** Bulk-add existing open issues via `gh project item-add` (`gh project` CLI supports list/add/edit with `--owner`), then enable auto-add so the backfill doesn't recur.
2. **One intake rule per repo class.** Libraries (auto-add everything) vs apps (auto-add only labeled) — encode the difference in filter syntax rather than in tribal memory.
3. **Verify automation end-to-end.** Open a test issue matching the auto-add filter → it should appear in Todo within seconds; close it → Status flips to Done; archive rule eventually moves it out of active views.
4. **Guard against silent workflow drift.** After renaming Status values or fields, re-open Workflows and confirm each enabled workflow still maps to an existing value — disabled/errored workflows fail silently in day-to-day use.
5. **Don't fork per-team projects.** One project with per-team views (filter by assignee team or custom Team field) keeps the portfolio roll-up intact; N projects means N roll-up problems later.

## Related

1. **`github-milestone-tracking.md`.** Milestone limits that motivated the Projects move; iteration fields are the fix.
2. **`github-labels-automation.md`.** Label-driven intake filters feeding auto-add workflows.
3. **`github-graphql-api-patterns.md`.** Pagination and mutation patterns for the ProjectV2 API.
