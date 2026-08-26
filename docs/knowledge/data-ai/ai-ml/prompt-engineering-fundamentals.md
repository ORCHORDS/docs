# prompt-engineering-fundamentals

**Issue:** Core principles for writing effective prompts
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Vague prompts produce inconsistent or low-quality outputs.

## Pattern / Solution
```
# Good prompt structure
[Role/Persona]
[Context/Background]
[Task Instructions]
[Constraints]
[Output Format]
[Examples if needed]

Example:
"You are an expert Python developer. Given the following bug report and code snippet,
identify the root cause and provide a minimal fix. Be concise. Output as JSON with
keys: root_cause, fix_code, explanation."
```

## Gotchas
- Specificity beats verbosity — precise constraints outperform long prose
- Negative instructions ("do not...") are less reliable than positive ones
- Test prompts across temperature settings before deploying

## Related
- `prompt-system-message-design.md`
- `prompt-testing-evals.md`
