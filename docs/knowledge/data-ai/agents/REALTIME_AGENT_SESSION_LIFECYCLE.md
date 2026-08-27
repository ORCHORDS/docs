# Realtime Agent Session Lifecycle

Define connection, active, closing, and terminated states for realtime agent sessions.

## Checklist
- Make session start and stop explicit.
- Handle reconnects and stale sessions.
- Distinguish transport errors from agent errors.
- Preserve a final session outcome.

## Primary source
- OpenAI `openai/openai-agents-python` realtime agents.
