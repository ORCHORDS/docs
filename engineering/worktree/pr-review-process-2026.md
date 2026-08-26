# pr-review-process-2026

**Issue:** A team's PRs sit open for 5 days waiting for review. The team has 200 PRs in the queue. The team debates CODEOWNERS, PR templates, mandatory reviewers, review SLAs. The team needs the 2026 reference for PR review process.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The 5 process levers

1. **PR template** with checklist (tests, docs, breaking change, screenshots).
2. **CODEOWNERS** auto-assign reviewers per path.
3. **Review SLA** (24h first response, 72h substantive review).
4. **Required reviewers count** (1-2 typical, 2 for security-sensitive).
5. **Auto-merge** for low-risk PRs (label-driven, after CI green).

## The 5 CODEOWNERS patterns

1. **Default reviewers** for the whole repo (`* @org/team`).
2. **Path-specific owners** (`/docs/ @org/tech-writers`).
3. **Optional reviewers** (no required review, just notification).
4. **Last-match-wins** rule; most specific path overrides less specific.
5. **Team handles** for org-wide reviewer rotation.

## The 5 PR template sections

1. **What** - 1-2 sentence summary.
2. **Why** - business/technical motivation.
3. **How** - implementation approach.
4. **Testing** - how to verify.
5. **Risk** - what could break, rollback plan.

## The 5 anti-patterns

1. **No PR template** - reviewers ask "what does this do?" repeatedly.
2. **Required reviewers from a team that doesn't exist** - bot-assignee with no human follow-up.
3. **Review SLA unenforced** - just documented, never measured.
4. **LGTM without reading** - rubber-stamping.
5. **PRs >1000 lines** - impossible to review well.

## Gotchas

- CODEOWNERS only triggers on PR open or push to a path with `owned` rule.
- Review SLA tooling: GitHub Insights, Sentry, custom dashboards.
- Auto-merge for security patches needs branch protection override.
- Stale PR bot (e.g., `proximity` app) closes after N days of inactivity.
- Code review != code ownership; CODEOWNERS is for both, but PR review is lighter.

## Source URLs (verified 2026-08-10)

- https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners
- https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/creating-a-pull-request-template-for-your-repository
- https://github.com/marketplace/proximity-app
