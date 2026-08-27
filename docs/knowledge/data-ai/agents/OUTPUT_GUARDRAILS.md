# Output Guardrails

Validate agent output before it becomes user-visible or triggers downstream work.

## Checklist
- Check schema, policy, and required evidence.
- Prevent secret or unnecessary sensitive-data disclosure.
- Reject malformed structured output.
- Record validation failures for debugging.

## Primary source
- OpenAI `openai/openai-agents-python` output guardrails.
