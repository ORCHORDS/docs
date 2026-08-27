# Trace Correlation

Correlate agent, tool, handoff, and workflow events under one run identity.

## Checklist
- Use stable trace/run identifiers.
- Link nested agent and tool spans.
- Capture failure boundaries and timing.
- Redact secrets and unnecessary user data.

## Primary source
- OpenAI `openai/openai-agents-python` tracing.
