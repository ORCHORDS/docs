# ai-agent-safety-2026

**Issue:** A team deploys an AI agent that can take actions (file writes, API calls, code execution). The team debates sandboxes, action allow-lists, kill switches, monitor-and-rollback. The team reads about recent agent failures (auto-deletion of production DB, prompt injection in retrieved content). The team needs the 2026 reference for AI agent safety.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The 5 agent safety risks

1. **Prompt injection in retrieved content.** RAG fetches attacker-controlled page; agent follows instructions.
2. **Tool abuse.** Agent makes API calls to expensive or irreversible endpoints.
3. **Confused deputy.** Agent has access to user A's data when called by user B.
4. **Runaway loop.** Agent enters infinite tool-calling loop, racks up cost.
5. **Privilege escalation.** Agent's token includes permissions the human didn't intend.

## The 5 defense patterns

1. **Sandbox.** Restrict agent's filesystem, network, environment variables. Docker or VM.
2. **Action allow-list.** Only specific tools/paths/endpoints accessible.
3. **Confirmation gates.** Irreversible actions require human approval.
4. **Token scopes.** Agent uses scoped tokens (read-only by default, write only when needed).
5. **Rate limits and cost caps.** Hard ceilings on tool calls per session and cost per request.

## The 5 EU AI Act agent obligations

1. **Article 14 human oversight** - enable, understand, detect, decide, intervene.
2. **Article 9 risk management** - identify and mitigate agent-specific risks.
3. **Article 13 transparency** - users know they're interacting with an agent.
4. **Article 26 deployer obligations** - monitor and log agent actions.
5. **Article 27 FRIA** - fundamental rights impact assessment for high-risk agents.

## The 5-step agent safety pattern

1. **Sandbox by default** - Docker, no network, no host filesystem.
2. **Action allow-list** - explicit list of allowed tools and parameters.
3. **Token scopes** - read-only by default; write only with explicit user approval.
4. **Cost caps** - hard ceiling per session; alert at 50/80/100%.
5. **Audit log** - every tool call with prompt, response, action, outcome.

## The 5 anti-patterns

1. **"It's just an LLM, what could go wrong"** - prompt injection is real.
2. **No tool allow-list** - "let it do anything."
3. **Long-running autonomous sessions** - no kill switch.
4. **No cost cap** - $50K from a confused agent.
5. **Production data access without scoping** - confused deputy leaks.

## The 5 best practices

1. **Defense in depth** - sandbox + allow-list + scopes + caps + logs.
2. **Test prompt injection** specifically (not just accuracy).
3. **Stage agent rollouts** - read-only first, write-with-approval second, full autonomy third.
4. **Human spot-checks** during agent sessions.
5. **Post-mortem on every agent incident** - patterns matter.

## Verification

The tell that agent safety is real:

- Sandbox configured (Docker, no host access).
- Action allow-list enforced.
- Token scopes narrow.
- Cost caps in place, alerts at 50/80/100%.
- Audit log captures every tool call.
- Kill switch tested.
- Prompt injection test in eval suite.
- Human approval for irreversible actions.

The tell it isn't:

- "The LLM doesn't have permissions to do anything bad" (it does, by default).
- No audit log.
- No cost cap (or one set so high it's never hit).
- "We tested it manually."

## Gotchas

- Sandboxing JavaScript agents is harder than Python (no easy exec sandbox).
- Tool calls can chain: agent calls tool A which calls tool B which the agent didn't anticipate.
- Some agent frameworks (LangGraph, CrewAI) have built-in checkpointer for replay; use it.
- Confused deputy is a real risk in multi-user systems; per-user scopes required.
- EU AI Act Article 26 deployer obligations include monitoring - log retention matters.

## Source URLs (verified 2026-08-10)

- https://artificialintelligenceact.eu/article/14/
- https://www.anthropic.com/research/sleeper-agents
- https://simonwillison.net/2024/Jun/17/ai-worlds-fair/
- https://www.langchain.com/langgraph
- https://github.com/openai/openai-agents-python
