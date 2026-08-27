# MCP Tool Boundaries

Treat MCP-connected tools as external interfaces with explicit contracts.

## Checklist
- Validate declared tool schemas.
- Limit each connection to required capabilities.
- Record failures and unsupported responses.
- Keep user-facing and internal tool output distinct.

## Primary source
- OpenAI `openai/openai-agents-python` MCP support.
