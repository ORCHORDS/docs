# working-agreement-template

**Issue:** Team norms are implicit, causing friction when expectations differ between members
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
One engineer sends Slack messages expecting immediate replies. Another has their notifications off during deep work. One person thinks standups are mandatory; another considers them optional. Nobody has explicitly agreed on these norms, so every violation feels personal.

## Pattern / Solution
A working agreement is a team-authored document of explicit norms. It's created collaboratively and revisited regularly.

**Creation workshop (60 min):**
1. Each person writes answers to the prompts on sticky notes / shared doc
2. Group the answers by theme
3. Discuss and agree on a team norm for each theme
4. Document the agreed norms and share the link with the team

**Working agreement template:**
```markdown
# [Team Name] Working Agreement
**Last updated:** YYYY-MM-DD
**Next review:** YYYY-MM-DD (quarterly)

## Communication
- Core hours (when everyone is available): 10am–3pm [timezone]
- Async-first: use Slack for non-urgent, meetings for decisions
- Expected response time: Slack DM within 4h; mention in a channel within 24h
- Urgent (production incident): call or text, don't expect Slack monitoring

## Meetings
- All meetings have an agenda 24h in advance or we decline
- Decisions are documented in a shared doc within 24h of the meeting
- Recurring meetings are reviewed for value every quarter

## Code Review
- Review requested → first comment within 1 business day
- Reviews should be thorough, not rubber stamps
- Use `nit:` prefix for optional suggestions

## Work Hours
- No expectation of responses outside core hours
- On-call is the only exception
- PTO communicated in calendar and team channel 1 week in advance

## Conflict Resolution
- Disagreements in code review → discuss in the PR, then escalate to a 1-1
- Team-level disagreements → raise in retrospective
- Manager involved only after peer resolution has been attempted

## What we value
- Psychological safety: it's safe to say "I don't know"
- Over-communication of blockers
- Shipping over perfection
```

## Gotchas
- Working agreements drift without a quarterly review — put it on the retro calendar
- Don't create a working agreement that nobody will follow — better to have 5 real norms than 20 aspirational ones
- New team members should review and comment on the working agreement in their first week

## Related
- `async-communication-guidelines.md`
- `meeting-efficiency-patterns.md`
- `team-health-check-retrospective.md`
