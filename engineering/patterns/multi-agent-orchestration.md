# multi-agent-orchestration

**Issue:** Patterns for orchestrating multiple AI agents / subagents
**Date:** 2026-08-09
**Repo:** example-org/example-repo at 196e96e
**Author:** the platform team
**Status:** verified-live (https://thepromptshelf.dev/blog/claude-code-multi-agent-orchestration-patterns-2026/)

## The 2026 orchestration primitives

Three primitives are standard in 2026:

| Primitive | Scope | Communication | Best for |
|---|---|---|---|
| **Subagents** | Within a session | Report to orchestrator only | Quick parallel workers, context isolation |
| **Agent teams** | Separate sessions | Direct peer messaging + shared task list | Complex parallel work requiring debate |
| **Background agents** | Long-running, monitored | Agent View (web/desktop) | Autonomous tasks, CI-style workflows |

The user's fleet in this repo implements the **subagent**
primitive (Claude Code's `Agent` tool). The `packages/mcp-server/`
plus the `McpAgent` class on Cloudflare also implement
subagents. The user can extend to agent teams or background
agents later.

**Source:**
- hidekazu-konishi: https://hidekazu-konishi.com/entry/claude_code_subagents_and_orchestration_guide.html
- tembo 2026: https://www.tembo.io/blog/claude-code-multi-agent-orchestration
- Shipyard 2026: https://shipyard.build/blog/claude-code-multi-agent/
- thepromptshelf 6 patterns: https://thepromptshelf.dev/blog/claude-code-multi-agent-orchestration-patterns-2026/
- digitalapplied 5 patterns: https://www.digitalapplied.com/blog/multi-agent-orchestration-5-patterns-that-work
- Claude docs: https://code.claude.com/docs/en/sub-agents
- akaranjkar: https://dev.to/akaranjkar08/claude-code-multi-agent-coordination-build-ai-teams-that-ship-2026-16b9
- explainx: https://explainx.ai/blog/claude-code-subagents-multi-agent-workflows-2026

## The 5 orchestration patterns (2026 production set)

### 1. Fan-out (parallel scatter-gather)

Orchestrator spawns N subagents, waits for all, aggregates.
Best for: independent subtasks, shared deadline, cost of
N-way token spend justifies walltime gain.

```
Orchestrator → 3 parallel subagents (each handles one slice)
              → wait for all
              → 1 aggregator subagent (receives all 3 outputs)
              → return aggregator's result
```

**Token cost:** ~N (one per peer) **Wall-clock:** bounded by slowest peer

### 2. Pipeline (sequential chain)

Subagents run in sequence, each consuming the previous
one's result. Best for: research before implementation,
state-dependent tasks.

### 3. Debate (multi-perspective critique)

3+ reviewers simultaneously, each applying a different
lens. Best for: high-stakes validation, security review.
**Cost:** ~2.5x (multiple reviewers on the same artifact).

### 4. Supervisor (hierarchical delegation)

Orchestrator + worker subagents. Workers don't know about
each other. **This is the 2026 production default.** Claude
Code subagents (one level deep), LangGraph Supervisor, and
OpenAI Agents SDK handoffs all use this topology.

### 5. Swarm (dynamic peer agents)

50+ concurrent agents, peer-to-peer. **Rarely the right
choice.** Only when task population genuinely exceeds 50
concurrent agents and you have the infrastructure to manage
it.

## The 4 subagent agent types (Claude Code)

- **Sync subagents** — blocking execution, parent waits
- **Async agents** — background, parent notified on completion
- **Fork subagents** — inherit parent context (cache-identical prefix)
- **Teammates** — named agents with direct inter-agent messaging
- **Remote agents** — separate Claude Code Runner (CCR) environments

## When to use vs not

| Use subagents | Don't use subagents |
|---|---|
| Task produces verbose output you won't reference | Quick targeted change in 2-3 files |
| Want tool restrictions per scope | Simple sequential operations |
| Self-contained work reducible to a summary | Tasks need frequent back-and-forth |
| Independent investigations to fan out | Shared state that requires coordination |

## Decomposition rules

A good subagent decomposition has:
- **Clear boundaries** — each subagent owns a non-overlapping slice
- **Independent inputs** — no hidden dependencies between subtasks
- **Bounded scope** — cap tool calls, max output length, time-box
- **Concrete success criteria** — "npm test passes" not "implement the feature"

For each subtask:
- **Input:** exactly what gets passed
- **Output:** exactly what gets returned
- **Constraint:** scope limit
- **Done when:** verifiable condition

## The 20K context tax

Every subagent starts with ~20K tokens of context loading
before the actual work begins. Parallelism caps at 10
concurrent subagents. The 20K tax is a hidden cost —
factor it in when comparing subagent vs inline.

## Token efficiency metric

Track this weekly: **Total tokens consumed by the subagent
vs tokens the main session would have used doing the same
work inline.** Ratio should be better than 1:1 for
subagents to be worth the coordination overhead.

If the ratio is worse, you're delegating the wrong tasks
(probably stuff that should stay in main, or stuff that's
too small).

## The 5 anti-patterns

1. **Subagents with shared mutable state** — race conditions, lost work. Use sequential or restructure.
2. **Subagent for 2-3 specific files** — overhead exceeds savings. Stay in main.
3. **Vague task brief** — "improve this" wastes hours. Specific scope + success criteria.
4. **No subagent entry in AGENTS.md** — model can't reliably trigger. Define each subagent explicitly.
5. **Unbounded subagent retries** — no `attempts: 2` rule. Same failure twice = call a person.

## Related
- `patterns/agent-skill-design.md` — SKILL.md design (orthogonal to subagents)
- `patterns/agent-context-engineering-2026.md` — context isolation in subagents
- `patterns/agent-iteration-discipline.md` — the loop that contains the subagents
- `patterns/codex-connector-integration.md` — Codex's self-improving skills use sub-agents
- `packages/fleet/src/eval-harness.js` — implementation reference (the fleet IS a multi-agent system)
- The shipped `packages/zcode-plugin/skills/research-with-agents/SKILL.md` — working fan-out example
