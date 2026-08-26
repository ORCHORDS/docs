# prompt-role-playing

**Issue:** Using persona assignment to shape model behavior and expertise
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Generic responses lack domain expertise depth and appropriate tone.

## Pattern / Solution
```
"You are a senior security engineer with 15 years of experience in cloud infrastructure.
You communicate in concise, technical language suitable for other engineers.
You prioritize practical, battle-tested solutions over theoretical ones."

Effective persona elements:
1. Role title + experience level
2. Communication style
3. Decision-making priorities
4. What you will/won't do
```

## Gotchas
- Overly restrictive personas cause refusals on edge cases
- Personas don't grant actual expertise — models still hallucinate facts
- Test persona consistency with adversarial prompts

## Related
- `prompt-system-message-design.md`
- `prompt-injection-defense.md`
