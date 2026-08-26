# async-communication-guidelines

**Issue:** Distributed teams default to meetings for everything, fragmenting engineers' focus time
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
An engineer is pulled into three 30-minute sync calls to answer questions that could have been a Slack thread. Their calendar has no uninterrupted block longer than 45 minutes. Deep work never happens. Velocity suffers.

## Pattern / Solution
Default to async communication. Treat synchronous time as a scarce resource reserved for decisions and high-bandwidth collaboration.

**Decision matrix:**
| Situation | Async | Sync |
|-----------|-------|------|
| Status update | ✅ Slack / Confluence | |
| Code review feedback | ✅ GitHub comments | |
| Disagreement on approach | ✅ First; escalate to sync if no resolution | |
| Incident response | | ✅ Bridge call |
| Complex decision with many unknowns | | ✅ 30-min call |
| Pair debugging | | ✅ Screen share |

**Async communication best practices:**
- **Complete thought, complete message:** Write as if the other person is asleep. Don't send "Hey" and wait for a response.
- **Signal urgency explicitly:** "No rush, when you get to it" vs. "Need this by EOD" vs. "Blocking me now"
- **Use threads:** Keep channels clean; reply in thread, not in the main channel
- **Meeting alternatives:** Loom for demos, Miro for whiteboarding, Notion comments for feedback rounds
- **Response time norms:** Set explicit expectations in the working agreement (e.g., 4h for DMs during core hours)

**Protect deep work time:**
- Block 2-hour no-meeting windows daily on shared calendars
- "Focus time" blocks are respected; colleagues check async before interrupting
- On-call rotation is the only valid interrupt during focus blocks

**Async-first does not mean no meetings:**
Kickoffs, retrospectives, incident response, and high-stakes decisions benefit from synchronous interaction. Async-first means you default to async and switch to sync with intention.

## Gotchas
- Async fails when the message quality is low — short, incomplete async messages create more round-trips than a single sync call
- Time zone overlap is necessary for async to work — at least 2 hours of overlap per team
- "Quick call?" is often not quick — protect yourself and others by defaulting to async

## Related
- `meeting-efficiency-patterns.md`
- `working-agreement-template.md`
- `pair-programming-remote.md`
