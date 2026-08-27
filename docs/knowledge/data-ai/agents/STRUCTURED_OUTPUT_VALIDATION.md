# Structured Output Validation

Validate structured agent output before accepting it as complete.

## Checklist
- Enforce schema and required fields.
- Reject partial or malformed structures.
- Normalize known optional fields.
- Preserve validation failures for diagnosis.

## Primary source
- OpenAI `openai/openai-agents-python` structured result patterns.
