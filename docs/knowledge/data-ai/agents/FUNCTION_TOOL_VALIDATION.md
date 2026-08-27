# Function Tool Validation

Validate function-tool inputs and outputs at the agent boundary.

## Checklist
- Use explicit input schemas.
- Reject malformed arguments before execution.
- Validate returned data before reuse.
- Make unsupported states visible to the agent.

## Primary source
- OpenAI `openai/openai-agents-python` function tools.
