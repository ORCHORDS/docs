# issue-and-pr-templates

**Issue:** GitHub issue + PR templates — structure
**Date:** 2026-08-09
**Status:** documented

## Symptom
Users open issues with no info. "It's broken." You
ask for repro. They don't respond. Triage takes
hours. You wish you had templates.

## Root cause
**No template = no structure.** Use forms.

**Source:** GitHub docs + gingiris 2026.

## The "templates" concept

GitHub templates:
- **Issue template:** Pre-formatted form
- **PR template:** Pre-formatted checklist
- **Location:** `.github/ISSUE_TEMPLATE/`
- **Format:** YAML (forms) or Markdown

The template is structure.

## The "issue forms vs markdown" pattern

For choice:
- **Forms (YAML):** Web UI, structured
- **Markdown:** Free-form
- **Use forms:** For structured data
- **Use markdown:** For open-ended

The choice is per type.

## The "issue form YAML" pattern

For form:
```yaml
# .github/ISSUE_TEMPLATE/bug.yml
name: 🐛 Bug Report
description: Report a bug
title: "[Bug]: "
labels: ["bug", "needs-triage"]
assignees: []
body:
- type: markdown
  attributes:
    value: Thanks for reporting!
- type: input
  id: version
  attributes:
    label: Version
    placeholder: "1.2.3"
  validations:
    required: true
- type: textarea
  id: repro
  attributes:
    label: Steps to reproduce
    placeholder: |
      1. Go to...
      2. Click...
  validations:
    required: true
- type: dropdown
  id: severity
  attributes:
    label: Severity
    options:
      - Low
      - Medium
      - High
      - Critical
  validations:
    required: true
```

The form is structured.

## The "form field types" pattern

For types:
- **markdown:** Static text
- **input:** Single line
- **textarea:** Multi-line
- **dropdown:** Select
- **checkboxes:** Multi-select
- **assignees:** Auto-assign
- **labels:** Auto-label

The types are per need.

## The "config.yml" pattern

For config:
```yaml
# .github/ISSUE_TEMPLATE/config.yml
blank_issues_enabled: false
contact_links:
  - name: ❓ Questions
    url: https://github.com/org/repo/discussions
    about: Ask questions here
  - name: 💬 Discord
    url: https://discord.gg/your-invite
    about: Chat with the community
```

The config forces templates.

## The "file ordering" pattern

For order:
- **1-bug.yml:** First
- **2-feature.yml:** Second
- **3-support.yml:** Third
- **10-epic.yml:** Tenth
- **Prefix:** Number for order

The order is per file.

## The "common issue types" pattern

For types:
- **1-bug.yml:** Bug report
- **2-feature.yml:** Feature request
- **3-question.yml:** Question
- **4-security.yml:** Security issue
- **5-docs.yml:** Docs issue
- **6-epic.yml:** Epic / tracking

The types are per need.

## The "PR template" pattern

For PR:
```markdown
<!-- .github/PULL_REQUEST_TEMPLATE.md -->

## TL;DR
<!-- 1-3 sentences: what changed -->

## Changes
<!-- Added / Changed / Fixed -->

## Testing
<!-- How did you test this? -->

## Screenshots (if UI)
<!-- Before → After -->

## Checklist
- [ ] Tests pass
- [ ] Documentation updated
- [ ] No console.log
- [ ] Linked issue
```

The PR has structure.

## The "PR template placement" pattern

For location:
- **`.github/PULL_REQUEST_TEMPLATE.md`** (preferred)
- **`PULL_REQUEST_TEMPLATE.md`** (root, works)
- **`.github/PULL_REQUEST_TEMPLATE/`** (multiple)

The location is `.github/`.

## The "auto-label" pattern

For labels:
```yaml
# In issue form
labels: ["bug", "needs-triage"]
```

The label is auto.

## The "auto-assign" pattern

For assignees:
```yaml
# In issue form
assignees: ["oncall", "platform-team"]
```

The assignee is auto.

## The "auto-title" pattern

For title:
```yaml
# In issue form
title: "[Bug]: "
```

The title is prefixed.

## The "good first issue" pattern

For newcomers:
- **Label:** `good first issue`
- **Effect:** 3x more contributions
- **Use:** Easy, well-scoped

The label attracts.

## The "blank_issues_enabled" pattern

For choice:
- **false:** Force template (recommended)
- **true:** Allow blank (legacy)

The default is false.

## The "48-hour response" pattern

For engagement:
- **First response < 48h:** 3x more contributions
- **Stale bots:** Auto-close after 60 days
- **Triager:** On rotation

The response is fast.

## The "duplicate handling" pattern

For dupes:
- **Search first:** Before opening
- **Close politely:** Link to original
- **Don't shame:** Newcomers may not know

The dupe is closed politely.

## The "issue template benefits" pattern

For benefits:
- **60% reduction** in "more info" back-and-forth
- **Faster triage**
- **Better quality** bug reports
- **Auto-labels** → right team
- **Auto-assign** → on-call

The benefits are real.

## The "label taxonomy" pattern

For labels:
- **Type:** bug, feature, question
- **Priority:** P0, P1, P2, P3
- **Status:** needs-triage, in-progress, blocked
- **Effort:** good-first-issue, help-wanted
- **Area:** frontend, backend, infra, security

The taxonomy is per type.

## The "PR template checklist" pattern

For checklist:
- [ ] Tests pass
- [ ] Docs updated
- [ ] No console.log
- [ ] Linked to issue
- [ ] No breaking changes (or documented)
- [ ] Migration plan (if schema change)
- [ ] Feature flag added (if risky)

The checklist is 7.

## The "no template" anti-pattern

For no template:
- **Issue:** Garbage bug reports
- **Fix:** Templates

The template is required.

## The "blank_issues_enabled: true" anti-pattern

For blank:
- **Issue:** Vague reports
- **Fix:** Force template

The blank is disabled.

## The "no labels" anti-pattern

For no labels:
- **Issue:** Can't filter
- **Fix:** Taxonomy + auto-label

The labels are required.

## The "no checklist" anti-pattern

For no checklist:
- **Issue:** Incomplete PRs
- **Fix:** Required checklist

The checklist is required.

## The "no response" anti-pattern

For no response:
- **Issue:** 48h+ = -3x contributions
- **Fix:** Triage rotation

The response is fast.

## The "duplicate ignored" anti-pattern

For dupes:
- **Issue:** Repeat issues
- **Fix:** Search + close politely

The dupe is closed.

## The "stale issue" anti-pattern

For stale:
- **Issue:** 90 days no activity
- **Fix:** Stale bot + auto-close

The stale is cleaned.

## The "PR template location" pattern

For locations:
- **Multiple:** `.github/PULL_REQUEST_TEMPLATE/`
- **One:** `.github/PULL_REQUEST_TEMPLATE.md`
- **Detect:** File alphabetically

The multiple is per type.

## The "issue template choice" pattern

For choice:
| Use case | Template type |
|---|---|
| Bug report | Form (YAML) |
| Feature request | Form (YAML) |
| Question | Markdown (open) |
| Security | External (security@) |
| Epic | Form (YAML) |

The choice is per need.

## The "bug report template" pattern

For bug:
- **Title:** "[Bug]: "
- **Steps to reproduce:** Required
- **Expected behavior:** Required
- **Actual behavior:** Required
- **Environment:** Version, OS
- **Screenshots:** Optional

The bug is structured.

## The "feature template" pattern

For feature:
- **Title:** "[Feature]: "
- **Problem:** What + why
- **Solution:** Proposed
- **Alternatives:** Considered
- **Impact:** Who benefits

The feature is structured.

## The "good template" pattern

For each template:
- **Short:** < 30 sec to fill
- **Required fields:** Minimum
- **Auto-fill:** Labels, assignees
- **Examples:** In placeholder
- **Markdown:** For guidance

The template is frictionless.

## The "triage bot" pattern

For automation:
- **Triage:** Auto-label on open
- **Stale:** Auto-close after 60d
- **Mention:** Notify team
- **Move:** To project board

The bot assists.

## The "GitHub Projects" pattern

For board:
- **Columns:** Triage, In Progress, Review, Done
- **Auto-add:** On label
- **Auto-move:** On PR
- **Sprint view:** Per team

The board is the workflow.

## The "issue templates checklist" pattern

For checklist:
- [ ] .github/ISSUE_TEMPLATE/ created
- [ ] bug.yml form
- [ ] feature.yml form
- [ ] question.yml markdown
- [ ] config.yml with blank_issues_enabled: false
- [ ] contact_links
- [ ] Auto-labels
- [ ] Auto-assignees
- [ ] Numbered order
- [ ] PR template in .github/

The checklist is 10.

## Verification
- **Test:** Forms render in UI
- **Test:** Auto-labels apply
- **Test:** Auto-assign works
- **Test:** Blank disabled
- **Audit:** Quarterly

## Gotchas
- **The "no template" anti-pattern.** Required.
- **The "blank enabled" anti-pattern.** Disable.
- **The "no response" anti-pattern.** < 48h.

## Related
- `github/branch-protection-and-codeowners.md`
- `github/github-actions-reusable-workflows.md`
- `github/dependabot-config.md`
- `github/pat-self-merge-workaround.md`
- `deploy/cab-change-management.md`
- GitHub docs: https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/configuring-issue-templates-for-your-repository
- gingiris: https://gingiris.tools/blog/2026/04/02/github-issue-template-guide/
- GitHub blog: https://github.blog/developer-skills/github/issue-and-pull-request-templates/
