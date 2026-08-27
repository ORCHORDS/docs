# Agent Security Boundaries

Make trust boundaries between users, agents, tools, external services, and stored state explicit.

## Checklist
- Identify each boundary and data flow.
- Separate untrusted content from control instructions.
- Limit tool availability by workflow need.
- Review boundary changes when new integrations are added.

## Primary sources
- OpenAI `openai/openai-agents-python` tools/guardrails.
- Cloudflare `cloudflare/agents` runtime patterns.
