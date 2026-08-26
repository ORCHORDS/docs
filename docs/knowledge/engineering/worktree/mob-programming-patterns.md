# mob-programming-patterns

**Issue:** Whole-team collaboration on a single piece of code feels chaotic and unproductive
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A team tries mob programming but it devolves into one person typing while four others watch Slack. Or everyone talks at once and the driver freezes. The session ends without a clear output.

## Pattern / Solution
Mob programming is structured: one driver, one navigator, rest are the "mob." Explicit rotation prevents disengagement.

**Core roles:**
- **Driver:** Translates navigator instructions into keystrokes. Does not make decisions independently.
- **Navigator:** Speaks directions aloud at the appropriate abstraction level. One person at a time.
- **Mob:** Researches, reviews docs, spots issues. Feeds the navigator; does not talk to the driver directly.

**Rotation cadence:**
- Rotate every 10–15 minutes (shorter for beginners)
- Use a visible timer
- Hard rotation — no "just finish this thought"

**Session setup:**
```
1. Define the session goal (one function, one bug, one test scenario)
2. Set up shared dev environment on one machine or via VS Code Live Share
3. Agree on rotation order before starting
4. Driver shares screen; mob uses a separate read-only stream if remote
```

**Strong-style mobbing (recommended for cross-skill teams):**
The navigator must verbalize the intent, not the implementation. "Go to the auth module and add a check for expired tokens" — not "type `if token.expired`."

**When mobbing works well:**
- Onboarding: new hire is the driver, experienced engineers navigate
- Complex debugging that has stumped individuals
- Architecting a new critical path that everyone needs to understand

## Gotchas
- Mob size sweet spot is 4–6 people; larger groups lose focus
- Remote mobs need audio discipline — use a talking-stick convention
- If the mob has a strong opinion and the navigator ignores it, the session breaks down — navigator must listen to the mob

## Related
- `pair-programming-remote.md`
- `knowledge-sharing-sessions.md`
- `engineering-onboarding-template.md`
