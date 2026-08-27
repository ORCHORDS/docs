# Agent Context Window Management

Manage context growth deliberately during long agent runs.

## Checklist
- Prioritize current task state and authoritative evidence.
- Drop redundant or superseded context.
- Keep tool results attributable to their source.
- Detect when context pressure changes answer quality.

## Primary source
- OpenAI `openai/openai-agents-python` session/run concepts.
