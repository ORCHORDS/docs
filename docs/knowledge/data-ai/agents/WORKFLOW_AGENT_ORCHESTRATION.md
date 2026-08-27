# Workflow Agent Orchestration

Use workflows to coordinate multi-step agent tasks that span time or retries.

## Checklist
- Make each step's inputs and outputs explicit.
- Persist only required progress state.
- Define retry and compensation behavior per step.
- Surface terminal success and failure clearly.

## Primary source
- Cloudflare `cloudflare/agents` workflow-oriented orchestration.
