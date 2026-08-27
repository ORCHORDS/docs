# Agent as Tool Pattern

Expose specialist agents as bounded tools when delegation is better than full control transfer.

## Checklist
- Give the specialist a narrow input/output contract.
- Keep caller ownership explicit.
- Prevent recursive or uncontrolled delegation.
- Trace nested runs and costs.

## Primary source
- OpenAI `openai/openai-agents-python` agents-as-tools concept.
