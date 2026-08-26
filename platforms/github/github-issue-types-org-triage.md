# github-issue-types-org-triage

**Issue:** Issue trackers degrade into a flat stream of undifferentiated work items: bugs, feature requests, chores, and support questions all look identical, so triage becomes archaeology. Labels were the historical workaround, but labels are free-form, repo-scoped, inconsistently applied, and invisible to cross-repo reporting — an org cannot answer "how many production bugs landed in the app repos this quarter" without trusting that every repo applied the same label taxonomy correctly. GitHub's org-level issue types fix the classification layer properly: a structured, single-select field (Bug, Feature, Task, plus custom types) configured once per organization, exposed in the new-issue UI, enforceable through issue forms, and — as of the 2025-2026 API expansion — manageable via REST API and GitHub CLI, and actionable by the new Issues agent automations. This article covers using issue types as the backbone of an org-wide triage system.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## What issue types are and where they live

1. **A structured field, not a label.** Every issue gets one issue type from a closed list — the built-in Bug, Feature, and Task, or custom types an org defines (Epic, Incident, Support, Debt). Because it is a distinct field, type queries compose with label, assignee, and state filters instead of competing with them.
2. **Configured at the organization level.** Org admins manage types under the organization's issue settings, and repositories inherit the type list. This is the key difference from labels: taxonomy is defined once, so "Bug" means the same thing in every repo and roll-up queries work.
3. **Required at creation.** Repos can require an issue type when a new issue is opened, either through the UI prompt or by making the type field mandatory in an issue form template. This eliminates the unclassified backlog that label-based systems inevitably accumulate.
4. **Bound into issue forms.** YAML issue form templates include a type dropdown whose selection maps to the issue's type field, so a "Bug report" template files a Bug while a "Feature request" template files a Feature — classification happens at intake with zero triager effort.
5. **Paired with sub-issues and dependencies.** Types compose with the sub-issues/tasklists model: a custom "Epic" type on the parent plus typed children is the supported epic pattern, and typed parents make portfolio queries (sum of Bug children under each Epic) possible.

## API and CLI automation

1. **REST API management since March 2025.** Issue types can now be managed using the REST API — create, update, and list org issue types, and read/write the type on individual issues. This unlocked orgs that script taxonomy changes across hundreds of repos instead of clicking through settings pages.
2. **CLI management since June 2026.** GitHub CLI gained the ability to manage issue types, parent/sub-issue links, and dependencies from the terminal, so setting a type is a scriptable one-liner in triage batches: `gh issue edit` with type assignment in bulk loops over a query result.
3. **GraphQL for portfolio queries.** The issue type field is queryable in GraphQL alongside issues and Projects v2, which is what powers cross-repo dashboards: one query returns bug counts by type across every repo in the org, feeding Project roll-ups and quality metrics.
4. **Agent automations read and write types.** The July 2026 public preview of agent automation controls in GitHub Issues lets configured agents label, type, assign, and close issues — with visibility into the reasons for changes. Triage bots can classify incoming issues by type with an audit trail, subject to the org's controls on what agents may do.

## A triage workflow built on types

1. **Intake is typed or rejected.** Every repo uses issue forms with a mandatory type dropdown; there is no generic blank issue. The untyped bucket cannot form because the intake path does not allow it.
2. **Triage moves items, not labels.** The triager's daily queue is "issues where type is empty or wrong," usually a short list created by agents misfiring or imports from old systems. Changing a type is one edit in UI or CLI, and the change history preserves the correction.
3. **Types drive views and SLAs.** Org-standard saved views filter by type: Bugs sorted by severity and age, Support sorted by last activity, Debt reviewed in quarterly planning. SLA policies key off the type field, not a fragile label convention.
4. **Custom types are few and stable.** Resist type proliferation: an org needs roughly three to six types. Anything more granular belongs in labels or custom fields (the 2026 issue fields like Priority and Effort cover ranking within a type), because a 20-type taxonomy is a label system with extra structure.

## Pitfalls and migrations

1. **Existing issues start untyped.** Bulk-backfill the type field via REST API/CLI using heuristics (label name matching, template origin) before turning on required types, or the old backlog becomes permanently unclassifiable through the normal UI flow.
2. **Type changes are visible history.** Renaming or deprecating a custom type does not rewrite history silently; plan deprecations as an explicit campaign with a mapping table, since reports comparing across time need to know the taxonomy changed.
3. **Labels still exist — define the split.** Types answer "what kind of item is this"; labels answer "what qualities does it have right now" (area, severity, blocked). Document the split once per org or contributors will encode area information into custom types.
4. **Plan gating.** Org issue types and advanced issue management features depend on the org's plan tier; verify availability for private-repo orgs before building the triage program on top of them, or the rollout stalls at the first private repository.
