# pair-programming-remote

**Issue:** Remote pair programming is uncomfortable and unproductive without explicit structure
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Two remote engineers "pair" by screen-sharing but the navigator is passive and bored. The driver gets no real feedback. Sessions run long with no clear output. Pairing feels like a waste compared to working alone.

## Pattern / Solution
Remote pairing requires more explicit role contracts and tooling than in-person pairing.

**Roles:**
- **Driver:** Writes code, narrates decisions out loud ("I'm making this a class because...")
- **Navigator:** Reviews in real time, asks questions, spots bugs, suggests direction — does NOT type

**Session structure:**
```
0:00 – Agree on goal for this session (one concrete deliverable)
0:05 – Navigator sets up shared context (ticket, design doc, relevant code)
0:10 – Start coding; switch roles every 25 min (Pomodoro cadence)
     – 5 min break between each rotation
End  – Driver commits or stashes; navigator writes a brief session note
```

**Tooling:**
- Screen share with cursor sharing: VS Code Live Share, JetBrains Code With Me, Tuple
- Audio quality matters more than video — use headsets
- Shared scratchpad (Excalidraw, Miro) for navigator to sketch without interrupting the driver
- Timer displayed to both (e.g. Pomofocus.io or a shared timer in chat)

**When to pair:**
- Onboarding a new engineer on an unfamiliar subsystem
- Debugging a gnarly issue where a second set of eyes breaks tunnel vision
- Designing an approach for a high-stakes feature
- Knowledge transfer before someone leaves the team

**Async pair alternative:**
When timezones differ, use "async pairing": driver records a short Loom of implementation, navigator responds with a Loom of review feedback. Slower but maintains the collaborative dynamic.

## Gotchas
- Sessions longer than 90 minutes produce diminishing returns — hard stop and continue the next day
- Don't pair on boilerplate or mechanical work; pair on the interesting parts
- If one person is doing all the talking, the other needs to be invited in explicitly

## Related
- `mob-programming-patterns.md`
- `async-communication-guidelines.md`
- `engineering-onboarding-template.md`
