# Guardrail Layering

Layer agent safety checks instead of relying on one monolithic validation step.

## Checklist
- Separate input, tool-use, and output checks.
- Fail closed for privileged actions.
- Make guardrail results traceable.
- Test bypass attempts and conflicting policy states.

## Primary source
- OpenAI `openai/openai-agents-python` guardrail concepts.
