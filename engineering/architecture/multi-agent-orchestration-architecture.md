# multi-agent-orchestration-architecture

**Issue:** Teams building agent systems in 2025-26 face a protocol stack that crystallized fast: Anthropic's Model Context Protocol (MCP) for agent-to-tool/context connections and Google's Agent2Agent protocol (A2A) for agent-to-agent collaboration, plus a durable-execution layer underneath for long-running tasks. The architecture questions are now concrete — how agents discover each other, how tasks (which may run for hours or days) stay synchronized, where state lives, and what happens when one agent in a chain fails. Nothing in this knowledge base covers the agent layer; this article records the protocol split, the orchestration topologies, and the durability requirements.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The two-protocol stack

1. **MCP: agent-to-tools.** Model Context Protocol (open-sourced by Anthropic, late 2024) standardizes how an agent discovers and calls external capabilities — tools, resources, prompts — over a JSON-RPC client/server session; think of it as USB-C for context sources.
2. **A2A: agent-to-agent.** Google's Agent2Agent protocol (announced April 2025, 50+ launch partners, Linux Foundation governance thereafter) standardizes how independent agents delegate work to each other; Google's framing is explicit that A2A complements MCP rather than competing with it.
3. **The division of labor.** Per the 2025-26 consensus (Google's announcement, Elastic, Atlan): MCP connects an agent to tools and data; A2A connects agents to other agents. A single architecture typically uses both — an orchestrator agent exposing itself over A2A while calling MCP servers for its tools.
4. **A2A builds on boring standards.** Transport is HTTP with JSON-RPC and server-sent events for streaming, deliberately reusing what enterprises already run, with authentication schemes at parity with OpenAPI so existing identity infrastructure fits.

## A2A building blocks

1. **Agent Card.** Each agent publishes a JSON capability document (conventionally at `/.well-known/agent.json`) describing skills, endpoints, and auth requirements; discovery is a fetch, not a registry contract (though registries can layer on top).
2. **Task lifecycle.** Client and remote agents collaborate around a shared task object with explicit states — submitted, working, input-required, completed, failed — so both sides stay synchronized across runs that last seconds or days.
3. **Artifacts.** Task outputs are artifacts (files, structured data, media) distinct from the messages exchanged while working; separating "the conversation" from "the deliverable" keeps long tasks inspectable.
4. **Streaming via SSE.** Server-sent events deliver progress, intermediate state, and notifications during long-running tasks, which is what keeps a human in the loop instead of staring at a spinner.
5. **Peers, not tools.** A2A deliberately treats remote agents as opaque peers that may not share memory, tools, or framework with the caller; you delegate a task, you do not introspect their internals — the anti-corruption boundary of this stack.

## Orchestration topologies

1. **Orchestrator-worker.** A lead agent decomposes a goal, delegates subtasks to specialized workers over A2A, and aggregates artifacts; the most common production shape because the orchestrator is the single place where retries, budgets, and overall task state live.
2. **Hierarchical.** Orchestrators delegate to sub-orchestrators that own whole subsystems, each level only knowing its children's Agent Cards; scales organizationally but makes end-to-end latency and debugging harder.
3. **Peer handoff.** Agents forward tasks laterally (support agent hands to billing agent), carrying context in messages; good for stateless workflows, risky when no one owns the overall task lifecycle.
4. **Shared-blackboard/stateless mix.** For systems where agents coordinate through shared durable state rather than direct messaging, A2A becomes thin transport and the state store is the real architecture — decide this explicitly, because it changes failure semantics.

## Durability and failure handling

1. **Long-running tasks need durable execution.** Agent tasks routinely outlive process restarts and LLM-provider outages; the task state machine must live in durable storage (a workflow engine, a database-backed queue, or platform-level durable execution) so an orchestrator crash mid-delegation resumes rather than restarts from zero.
2. **Idempotent delegations.** Retrying a subtask must not double-charge a card or double-send an email; A2A task IDs give you a deduplication key — pair them with the idempotency discipline in `idempotency-design.md`.
3. **Bounded autonomy with human-in-the-loop.** The `input-required` task state exists precisely so agents can pause for approval; design the escalation points at delegation boundaries (spend above threshold, irreversible action, low confidence) instead of trusting guardrails alone.
4. **Budget and permission fencing per agent.** Each remote agent should run under its own scoped credentials and spend cap so a misbehaving or prompt-injected worker cannot exceed its mandate; the agent boundary is also a security boundary.
5. **Timeouts that mean something.** A stuck remote agent is invisible unless the orchestrator enforces per-subtask deadlines and surfaces partial artifacts on expiry; without this, one hung worker stalls the whole task forever.

## When this is overkill

1. **Simple tool use needs MCP only.** Elastic's guidance is representative: if the job is "call these APIs and summarize," a single agent with MCP tools is enough and A2A adds coordination overhead for nothing.
2. **One team, one deployment.** Multi-agent protocol machinery pays off when agents have independent owners, release cadences, or vendors; inside one codebase, function calls beat protocol hops.
3. **Latency-sensitive loops.** Every A2A hop adds HTTP round-trips and auth; tight interactive loops should stay in-process even in an otherwise multi-agent system.
4. **No durability requirement.** If every task completes in seconds and failure means "the user clicks retry," a plain request handler is cheaper and easier to debug than any orchestration layer.

## Related articles in this knowledge base

1. **`workflow-orchestration-patterns.md` and `saga-pattern-orchestration.md`.** The durable workflow and compensation machinery underneath long-running agent tasks.
2. **`idempotency-design.md` and `retry-pattern.md`.** Retry-safety discipline for delegated subtasks.
3. **`anti-corruption-layer.md`.** The peer-boundary thinking A2A formalizes.
4. **`ai-gateway-architecture.md`.** The LLM-routing layer these agents sit on top of.
