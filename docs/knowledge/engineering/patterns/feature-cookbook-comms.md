# feature-cookbook-comms

**Issue:** Team communication — Slack, PR, status, async
**Date:** 2026-08-09
**Status:** documented

## Symptom
You ship a feature. The team doesn't know. The user
support team gets questions they can't answer. Marketing
asks "is X shipped?" You say yes; they were about to
ship a conflicting email. Confusion.

## Root cause
**Communication is a feature.** Without it, the team is
out of sync.

**Source:** Various team communication guides.

## The "PR description" pattern

For a good PR description:
```markdown
## What
Brief description of the change.

## Why
The problem this solves. Link to the issue.

## How
The approach. Any trade-offs.

## Testing
How the change was tested. Screenshots, repro steps.

## Risk
What's the risk? How to roll back?

## Checklist
- [ ] Tests added
- [ ] Docs updated
- [ ] Migrations applied
- [ ] Feature flag added
- [ ] Monitoring added
```

The description is the context for the reviewer.

## The "PR review" pattern

For a good PR review:
- **Review within 24h** of opening
- **Approve, request changes, or comment** (no silent
  approvals)
- **Be specific** in feedback
- **Be kind** in tone
- **Focus on the design**, not the style

A review is collaboration, not gatekeeping.

## The "Slack channel" pattern

For Slack:
- **Per-team:** `#team-platform`, `#team-product`
- **Per-service:** `#service-user`, `#incidents`
- **Per-topic:** `#deploys`, `#alerts`, `#metrics`

The channel structure is the team's directory.

## The "status update" pattern

For an async status update:
```markdown
## Status update: 2026-08-09

### Done
- Shipped new dashboard (10% rollout)
- Reduced p99 latency by 200ms
- Closed 5 issues

### In progress
- A/B test for new checkout (50% complete)
- Migration to new DB schema (90% complete)

### Blocked
- Vendor X API change; need to negotiate

### Next week
- Increase rollout to 50%
- Ship A/B test
```

The status update is the team's pulse.

## The "incident communication" pattern

For an incident:
1. **Acknowledge:** "We are aware of the issue."
2. **Update every 30 min:** "We are investigating X."
3. **Resolution:** "The issue is fixed."
4. **Post-mortem:** "We're writing a post-mortem."

The communication is regular, not silent.

## The "deployment announcement" pattern

For a deploy:
```markdown
## Deploying to production

**When:** Today at 14:00 UTC
**What:** v1.2.3 — new dashboard
**Risk:** Medium (new feature; flag-protected)
**Rollback:** Disable the feature flag

**Smoke test:** Will run after deploy
**Monitoring:** Watching the new feature for 1h
```

The announcement is the team's awareness.

## The "design review" pattern

For a design review:
1. **Write an RFC** (the proposal)
2. **Share in #team** (async feedback)
3. **Hold a meeting** (discussion)
4. **Update the RFC** (incorporate feedback)
5. **Get approval** (sign-off from key stakeholders)
6. **Implement** (start coding)

The design review prevents building the wrong thing.

## The "knowledge sharing" pattern

For knowledge sharing:
- **Tech talks:** weekly or monthly
- **Blog posts:** written for the team
- **Wiki:** updated docs
- **Pair programming:** for tricky problems
- **Lunch & learn:** for new tools / libraries

The team's knowledge is shared, not siloed.

## The "decision record" pattern

For decisions, use ADRs:
```markdown
# ADR-001: Use D1 over Postgres

## Status
Accepted (2026-08-09)

## Context
We need a database...

## Decision
We use D1.

## Consequences
- Cheaper
- Single-region writes

## Alternatives
- Postgres
- DynamoDB
```

The ADR is the audit trail.

## The "release notes" pattern

For release notes:
```markdown
## v1.2.3 (2026-08-09)

### New
- New dashboard (10% rollout)
- AI-powered recommendations (beta)

### Improved
- 200ms faster p99 latency
- New error messages

### Fixed
- Login button on Safari 16
- Memory leak in image upload
```

The release notes are user-facing.

## The "retrospective" pattern

For retros:
1. **What went well?** (celebrate the wins)
2. **What didn't go well?** (learn from the issues)
3. **What will we do differently?** (improve the process)

The retro is blameless; the focus is the system.

## The "1:1" pattern

For 1:1s:
- **Weekly or biweekly**
- **Engineer-driven** (their agenda)
- **Manager listens** + takes notes
- **Action items** (follow-up)

The 1:1 is a relationship, not a status meeting.

## The "async vs sync" choice

For communication:
- **Async** (Slack, PR, doc): default
- **Sync** (meeting, call): for complex discussion

Default to async; sync is for the hard stuff.

## The "documentation" pattern

For documentation:
- **Code comments** (for the code)
- **API docs** (for the API)
- **Architecture docs** (for the system)
- **Runbooks** (for operations)
- **ADRs** (for decisions)

The docs are the team's memory.

## The "time zone" pattern

For distributed teams:
- **Overlap hours:** shared working hours
- **Async first:** don't require sync
- **Recorded meetings:** for those who can't attend
- **Written updates:** for time-shifted teams

Time zones are a fact; plan for them.

## The "remote vs in-person" pattern

For remote / in-person:
- **Remote-friendly:** default
- **In-person for:** kickoffs, retros, social
- **Tools:** Slack, Zoom, Notion, GitHub

The team can be anywhere; the work is what matters.

## Verification
- **Process:** The team has a communication playbook
- **Live:** Status updates are regular
- **Audit:** Quarterly review of communication

## Gotchas
- **The "no communication" anti-pattern.** The team is
  out of sync; bugs slip through.
- **The "over-communication" anti-pattern.** So many
  Slack messages that nobody reads them.
- **The "status meetings" anti-pattern.** A 30-min meeting
  that could be a doc. Use async.
- **The "decision in a meeting" anti-pattern.** A decision
  made in a meeting is forgotten. Use ADRs.
- **The "no follow-up" anti-pattern.** An action item
  without an owner is a wish. Assign + follow up.
- **The "broadcast channel" anti-pattern.** A channel for
  everything. People tune out. Use specific channels.

## Related
- `pr-template-and-issue-templates.md`
- `safe-deploy-checklist.md`
- `incident-response.md`
- `feature-architecture-decisions.md`
- `documentation-as-code.md`
