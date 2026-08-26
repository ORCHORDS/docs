# changelog-communication-process

**Issue:** Stakeholders and other teams are surprised by changes because there's no consistent communication channel
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A mobile team discovers an API contract changed when their app breaks in production. Or a PM is asked "what shipped this week?" and has to dig through Jira. Or a customer support team gets user complaints about a feature change they hadn't heard about.

## Pattern / Solution
Maintain a structured changelog and a regular communication ritual that pushes it to the right audiences.

**Changelog format (CHANGELOG.md in repo):**
```markdown
# Changelog

## [Unreleased]

## [2.14.0] — 2026-08-11
### Added
- Payment retry logic with exponential backoff (#1234)

### Changed
- User profile endpoint now returns `display_name` instead of `name` (breaking change)

### Deprecated
- `GET /api/v1/users/me` — use `GET /api/v2/users/me` (removal in v3.0)

### Fixed
- Race condition in session refresh (#1198)

### Removed
- Legacy CSV export endpoint (deprecated since v1.8)
```

Follow [Keep a Changelog](https://keepachangelog.com) conventions.

**Communication channels by audience:**
| Audience | Channel | Cadence | Format |
|----------|---------|---------|--------|
| Other engineering teams | #engineering-updates Slack | On release | Link to CHANGELOG section |
| Product / stakeholders | Release notes email | Weekly | Human-written summary |
| Customers | In-app notification / blog | On significant change | Comms team drafts |
| Support team | #support-heads-up Slack | On change affecting UX | Bullet list |

**Release note template (weekly for stakeholders):**
```
## Engineering Update — Week of [Date]

### Shipped
- [Feature name]: [one-sentence description] ([ticket link])

### In Progress
- [Feature name]: Expected completion [date]

### Breaking Changes / Deprecations
- [Details and migration path]

### On-Call Health
- Incidents this week: N (P1: X, P2: Y)
```

## Gotchas
- Changelog entries must be written at PR time, not retroactively — add it to the DoD
- Breaking changes need a migration guide linked from the changelog, not just a note
- Automated changelog generators (from commit messages) only work with disciplined commit conventions

## Related
- `documentation-ownership-model.md`
- `stakeholder-update-template.md`
- `conventional-commits-2026.md`
