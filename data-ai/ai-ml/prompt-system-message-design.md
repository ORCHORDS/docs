# prompt-system-message-design

**Issue:** Crafting effective system messages for consistent model behavior
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Without a strong system message, models behave inconsistently across sessions.

## Pattern / Solution
```
System message template:
"You are [role] at [company/context]. Your job is to [primary task].

Rules:
- Always [rule 1]
- Never [rule 2]
- When unsure, [fallback behavior]

Output format: [JSON/Markdown/plain text with schema]

Today's date: {current_date}
User context: {user_context}"
```

## Gotchas
- System messages are cached cheaply with Anthropic prompt caching
- Avoid contradictions between system and user messages
- Long system messages reduce effective context for conversation

## Related
- `prompt-engineering-fundamentals.md`
- `prompt-role-playing.md`
