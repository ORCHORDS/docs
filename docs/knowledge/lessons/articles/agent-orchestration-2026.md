# agent-orchestration-2026

**Issue:** A team builds a multi-agent system. Five agents, two supervisors, a handoff protocol. The supervisor runs out of context window mid-task. A worker loops indefinitely. The team debugs a "swarm" that produces one answer and twenty tool calls. The system is more orchestration than work.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

Multi-agent systems over-engineer. The 2026 production shape is one of six patterns; the literature cites 30+. Picking wrong wastes weeks; picking right ships in days.

## Root cause

The taxonomy stabilized in 2024-2026 around a small set of canonical patterns. The mistake is to start with the framework (LangGraph, CrewAI, AutoGen) instead of the pattern.

## The 6 patterns in 2026 production

The agenticorgchart.com taxonomy, the paiteq production survey, and the digitalapplied 8-pattern reference converge on the same canonical set.

| Pattern | Structure | When to use | Failure mode |
|---|---|---|---|
| Single-agent ReAct | one LLM + tools, think-act-observe loop | default; covers 80% of use cases | tool error, infinite loop |
| Single-agent + Reflexion | ReAct + episodic memory of past failures | failure modes repeat across runs | memory bloat |
| Single-agent + Plan-and-Execute | plan first, then execute each step | planning is the bottleneck | plan is wrong, no recovery |
| Supervisor-worker (hierarchical) | one supervisor, N specialist workers | heterogeneous specialists | supervisor OOM |
| Graph orchestration | agents as nodes in a directed graph | explicit control flow, auditability | graph complexity |
| Swarm / handoff | peer agents hand off to each other | genuinely parallel tasks, hard termination rule | infinite handoffs |

4 of every 5 production multi-agent systems in 2026 are supervisor-worker. Swarm and blackboard are research-tier; hierarchical and graph are production-tier.

## The selection decision tree

1. **Can a single ReAct agent with parallel tool calls handle it?** If yes, ship that. Don't add coordination overhead.
2. **Does the failure mode repeat across runs?** Add Reflexion (episodic memory). One agent still.
3. **Is planning the bottleneck?** Switch to Plan-and-Execute. Still one agent.
4. **Does the work decompose into heterogeneous specialist roles?** Switch to supervisor-worker. Most common multi-agent shape.
5. **Is the supervisor's context window not enough for the plan?** Switch to hierarchical (supervisor of supervisors). Rare.
6. **Are subagents truly independent and parallel?** Use swarm with a hard termination rule (count, time, consensus).
7. **Are the subagents owned by different teams / services?** Use blackboard with shared structured workspace.

If you can't answer "why not single-agent?" in one sentence, stay single-agent.

## The 3 framework choices

| Framework | Strength | Pick when |
|---|---|---|
| LangGraph | explicit state graph, strong observability via LangSmith | supervisor / hierarchical with audit, state persistence, complex branching |
| CrewAI | role-task metaphor, lowest learning curve | small team, sequential pipeline, fast prototype |
| AutoGen | group chat, research-flavoured | research-style, iterative refinement, code execution |

LangGraph for production. CrewAI for prototyping. AutoGen for research-flavoured work. The 2026 default stack is LangGraph + LangSmith for the outer loop; OpenAI Agents SDK or Anthropic SDK for the inner loop.

## The supervisor pattern code

```python
# LangGraph supervisor-worker
from langgraph.graph import StateGraph, END
from typing import TypedDict, Literal

class AgentState(TypedDict):
    task: str
    next_action: str
    worker_output: str
    iteration: int

def supervisor_node(state: AgentState) -> AgentState:
    """Central coordinator that routes to specialists."""
    decision = llm.invoke([{
        "role": "system",
        "content": """You are a supervisor. Decide the next action:
        - 'research': need more information
        - 'draft': ready to write
        - 'review': need quality check
        - 'complete': task is done"""
    }, {
        "role": "user",
        "content": f"Current state: {state}"
    }])
    return {"next_action": decision.content, "iteration": state.get("iteration", 0) + 1}

def should_continue(state: AgentState) -> Literal["research", "draft", "review", "complete", "__end__"]:
    if state["iteration"] > 10:
        return "__end__"  # hard cap
    return state["next_action"]

graph = StateGraph(AgentState)
graph.add_node("supervisor", supervisor_node)
graph.add_node("research", research_agent)
graph.add_node("draft", draft_agent)
graph.add_node("review", review_agent)
graph.add_conditional_edges("supervisor", should_continue)
graph.set_entry_point("supervisor")
app = graph.compile()
```

The hard cap (iteration > 10) is mandatory. Without it, a confused supervisor loops forever.

## The 4 production hard caps

Every multi-agent system needs explicit termination rules.

1. **Max iterations per run** (e.g., 10 turns)
2. **Max tokens per run** (e.g., 100k input + 20k output)
3. **Max dollars per run** (e.g., $2.00)
4. **Max dollars per day** (e.g., $500 total spend)

Set these in code, not in the prompt. A prompt-level "be efficient" is not a cap.

## The 5 anti-patterns

1. **Starting multi-agent before single-agent baseline.** Measure single-agent quality first; only add coordination when a measured quality dimension needs it.
2. **No termination rule.** A confused supervisor loops forever. Cap iterations.
3. **Sharing mutable state across agents without locks.** Use a blackboard pattern or single-writer state.
4. **Using the same model for every agent.** Pin the cheapest competent model per role; the supervisor can be a small model, the drafter a large one.
5. **No observability.** Without LangSmith or Langfuse, multi-agent debugging is impossible. Wire up tracing on day one.

## The DORA correlation

The 2025-2026 DORA research shows that elite performers use trunk-based development with feature flags. The same discipline applies to multi-agent systems: short, observable, capped agent runs beat long, opaque ones.

## Verification

The tell that multi-agent orchestration is real:

- The pattern matches a canonical 6-pattern taxonomy
- Hard caps on iterations, tokens, dollars are in code
- Tracing (LangSmith, Langfuse) is wired up before the second agent is added
- Single-agent ReAct was the baseline; multi-agent is justified by a measured gap
- Each agent has a pinned model (small for routing, large for generation)

The tell it isn't:

- "We have N agents" where N > 5
- No termination cap
- The supervisor and workers use the same model
- The system produces 10x the tool calls of a single-agent baseline
- Debugging requires reading the prompt template

## Gotchas

- **Coordinator context OOM.** The supervisor's context grows with every worker reply. Cap the per-worker reply length and the supervisor context window.
- **Error propagation.** If the researcher agent fails, the workflow hangs. Add per-node error handlers.
- **Cost surprises.** A 10-iteration loop at $0.20/iteration is $2/run. 1,000 runs/day is $2,000/day. Set a per-day cap.
- **Handoff ambiguity.** In swarm, agents hand off to each other. The hand-off message must be explicit; a confused handoff loops forever.
- **Test coverage.** Multi-agent is harder to test than single-agent. Test each agent independently (unit) and the full orchestration (integration).

## Related

- `lessons/ai-agent-memory-2026.md` — memory layer for cross-session context
- `lessons/structured-output-2026.md` — constrained outputs for inter-agent messages
- `lessons/ai-observability-otel-2026.md` — observability for multi-agent traces
- `lessons/ai-function-calling-2026.md` — tool use discipline within agents

## Source URLs (verified 2026-08-10)

- https://agenticorgchart.com/ — 2026 production pattern taxonomy
- https://www.paiteq.com/blog/multi-agent-orchestration-patterns/ — production survey
- https://www.digitalapplied.com/blog/agent-architecture-patterns-taxonomy-2026 — 8-pattern reference
- https://dev.to/pockit_tools/langgraph-vs-crewai-vs-autogen-the-complete-multi-agent-ai-orchestration-guide-for-2026-2d63
- https://ayinedjimi-consultants.fr/static/pdf/multi-agent-orchestration-2026.pdf
- https://levelop.dev/blog/ai-agent-orchestration-frameworks-guide-2026
- https://algorithmine.com/learn/multi-agent-orchestration-langgraph-autogen-crewai-2026
- https://www.anthropic.com/research/building-effective-agents — Anthropic's Building Effective Agents (December 2024)
