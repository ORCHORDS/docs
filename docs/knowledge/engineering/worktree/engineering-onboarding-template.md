# engineering-onboarding-template

**Issue:** New engineers take 2–3 months to reach productivity because onboarding is ad hoc
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A new hire joins and their onboarding is: get a laptop, get Slack access, shadow someone for a day. They spend the first two weeks hunting for docs, setting up tools, and figuring out who to ask for what.

## Pattern / Solution
A structured 30-60-90 day plan with checkpoints gives new engineers a clear ramp.

**Before Day 1 (manager + IT prep):**
- [ ] Laptop provisioned with dev environment setup script
- [ ] Access: GitHub org, Slack, Jira/Linear, 1Password, AWS/cloud console, VPN
- [ ] First week calendar blocked with onboarding sessions
- [ ] Buddy assigned (peer engineer, not manager)

**Week 1: Orientation**
- Company/product context from PM or founder (30 min)
- Architecture overview from tech lead (1 hour)
- Dev environment setup (half day; new hire follows a runbook, files issues where it breaks)
- Meet the team: 30-min 1-1 with each team member
- First PR: a small bug fix or documentation update (commit something real on Day 2–3)

**Week 2–4: Ramp**
- Shadow production deployment
- Fix one small bug independently
- Pair with a buddy on a medium complexity story
- Read key design docs and ADRs (curated list from tech lead)

**Day 30 checkpoint (with manager):**
- Is the environment fully working?
- Are there blockers to getting work done independently?
- What's confusing about the codebase or processes?

**Day 60: Independence**
- Owns a story end-to-end with minimal hand-holding
- Participates in sprint ceremonies
- Can answer basic questions from other new joiners

**Day 90: Full contribution**
- Reviews PRs from peers
- Participates in architecture discussions
- Files an onboarding retrospective (what was broken in the process)

## Gotchas
- First PR must ship real code — "add yourself to the team page" is demotivating for experienced engineers
- The buddy's job is psychological safety, not pair programming — make this distinction clear
- New hire onboarding feedback should update this template immediately

## Related
- `pair-programming-remote.md`
- `knowledge-sharing-sessions.md`
- `working-agreement-template.md`
