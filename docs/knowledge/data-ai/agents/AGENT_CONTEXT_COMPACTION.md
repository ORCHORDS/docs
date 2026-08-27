# Agent Context Compaction

Compact long-running context without losing critical state.

## Checklist
- Preserve goals, constraints, decisions, and unresolved work.
- Mark summarized evidence separately from raw evidence.
- Avoid reintroducing superseded facts.
- Validate the compacted state before resuming.

## Primary sources
- OpenAI `openai/openai-agents-python` session concepts.
- Cloudflare `cloudflare/agents` durable state patterns.
