# cross-team-dependency-management

**Issue:** Cross-team dependencies are discovered too late, causing blocked sprints and missed delivery dates
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Team A's feature requires an API from Team B. Team A discovers this in week 3 of a 4-week delivery window. Team B has no capacity until next quarter. The feature slips. Neither team is surprised — they just didn't surface the dependency early enough.

## Pattern / Solution
Identify and track cross-team dependencies proactively as part of planning, not reactively during execution.

**Dependency identification (quarterly planning):**
- Each team lists their upcoming deliverables and explicitly flags any external dependencies
- Dependency format: "We need [API/component/decision] from [Team] by [date] to deliver [feature] in [sprint]"
- All dependencies aggregated in a shared dependency board (linear view in Jira, Notion table, or similar)

**Dependency board columns:**
```
| Dependency | Provider team | Consumer team | Needed by | Status | Owner |
|------------|--------------|---------------|-----------|--------|-------|
| Auth token refresh API | Platform | Checkout | Sprint 14 | In progress | @alice |
```

**Status values:** Identified → Agreed → In Progress → Done → Blocked

**Weekly sync between dependent teams:**
- 15-minute standup between leads when an active dependency is in progress
- Topics: current status, risks, what would cause a slip

**Escalation path:**
1. Consumer team flags the dependency as at-risk in their stakeholder update
2. Engineering manager of consumer team contacts EM of provider team
3. If unresolved in 3 days: escalate to shared leadership

**API contract-first approach:**
- Provider team publishes an API contract (OpenAPI spec or schema) before implementation
- Consumer team builds against the contract using mocks
- Integration test happens when both sides are complete

## Gotchas
- Dependencies discovered in a sprint are almost always late — dependencies should be surfaced during sprint planning
- "We'll figure it out" is not a dependency resolution plan
- Avoid soft dependencies: if your feature works without the other team's output, it's not a dependency

## Related
- `rfc-request-for-comments-process.md`
- `sprint-planning-engineering.md`
- `stakeholder-update-template.md`
