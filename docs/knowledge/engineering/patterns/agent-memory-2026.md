# agent-memory-2026

- **Issue**: A long-running agent that forgets everything every turn is useless, and a 1M-token context window is not memory. Four production-grade memory platforms shipped in 2025-2026 with fundamentally different architectures. Picking the wrong one costs you a re-platform.
- **Date**: 2026-08-09
- **Repo**: example-org/example-repo
- **Author**: kb-batch-2
- **Status**: Active; complements `documentation/docs/policies/lessons/agent-self-correction.md` (memory vs reflection).

## Symptom

- You persist conversation history by stuffing it all into the context window. Latency and cost grow linearly. Pass rate drops 30%+ once you cross into prior sessions.
- You use vanilla RAG over chat logs. There is no write path, no conflict resolution, no forgetting. Two contradictory user preferences both surface; both are treated as live.
- You pick Mem0 / Letta / Zep based on a blog post without understanding the architectural difference. You regret it at scale.

## Root cause

**Context window ≠ memory.** A context window is short-term, volatile, and re-paid for at every turn. Memory is persistent across sessions, with its own storage tier, evolution rules, and forgetting policy. They are complements, not substitutes.

**RAG ≠ memory.** Classical RAG is retrieval over a *static corpus* (documents that exist before the agent talks to anyone). Memory is retrieval over the *agent's own history* (messages, tool calls, user-stated facts, derived summaries). The defining 2026 distinction is the **write path**: RAG is stateless, sessions reset, indexes are mostly append-only. Memory is stateful, accumulates across sessions, has conflicting versions over time, must be forgotten when wrong, and is written by the agent itself.

## The 2026 platform comparison

| Dimension | Mem0 | Letta (MemGPT) | Zep (Graphiti) | LangMem |
|---|---|---|---|---|
| Core abstraction | Extracted facts in vector store | Editable memory blocks + archival | Temporal knowledge graph | Tools on LangGraph storage |
| Best for | Personalization, chat history compression | Stateful long-running agents | Temporal facts, CRMs, support | LangGraph shops |
| Self-hosting | Yes (Apache 2.0) | Yes (Apache 2.0) | Yes (Apache 2.0, Graphiti) | Yes (LangGraph OSS) |
| Managed cloud | Mem0 Platform | Letta Cloud | Zep Cloud | LangSmith |
| Storage | Qdrant, pgvector, Chroma, Pinecone | PostgreSQL + pgvector | Neo4j or FalkorDB | LangGraph checkpointer backend |
| Write latency (p50) | 80–200 ms (async) | 150–400 ms (sync core update) | 300–800 ms (graph extraction) | LangGraph-dependent |
| Contradiction handling | Update-or-replace via LLM judge | Manual edits via tools | Automatic temporal invalidation | Manual via tools |
| Agent runtime included | No (memory layer only) | Yes (full agent server) | No (memory layer only) | No (LangGraph only) |
| Public benchmark | LongMemEval 94.4 at ~7K tok/query | Deep Memory Retrieval 93.4 | Deep Memory Retrieval 94.8 (beats MemGPT) | n/a |

## The three layers (every vendor covers all three, with differentiators)

1. **Episodic memory** — what happened, in time order. Conversation history, agent actions, tool calls, outcomes. Time-indexed, summarises as it ages.
2. **Semantic memory** — facts, preferences, entities. Durable, slow-moving, needs conflict resolution.
3. **Procedural memory** — learned workflows. "For this request type, do X then Y then Z." Crosses user boundaries; data-protection implications.

Plus a fourth, **working memory**, that lives in the context window itself.

## Letta's three explicit tiers (the original MemGPT model)

- **Core memory** — small, always-in-context block (persona, active task state). Agent edits via `core_memory_replace` tool.
- **Recall memory** — searchable conversation history, queryable by date or content.
- **Archival memory** — unbounded vector store, queried via `archival_memory_search`.

The agent decides when to call each tool. This is the right choice for stateful multi-day workflows.

## Mem0's two-phase pipeline

On every conversation turn:
1. **Extraction phase** — a small LLM extractor pulls candidate facts from the new exchange + prior context.
2. **Update phase** — for each candidate, retrieve top-K similar existing memories and prompt the LLM to select `ADD` / `UPDATE` / `DELETE` / `NOOP`.

This is the simplest drop-in. The right choice for personalization, chat-history compression, and teams that don't want to operate a memory service.

## Zep's temporal knowledge graph (Graphiti)

Three subgraphs:
- **Episode subgraph** — raw, high-fidelity inputs (messages, JSON documents, transactional snapshots), timestamped. Never rewritten.
- **Semantic entity subgraph** — extracted entities and facts, embedded into 1024-d vectors, connected by typed relations. Each has a validity interval.
- **Community subgraph** — clusters of related entities, used for higher-order retrieval.

Bi-temporal model: tracks both *when something happened* and *when the system learned about it*. Automatic contradiction handling via temporal invalidation. The right choice when facts shift over time and stale answers are unacceptable.

## LangMem

Memory as LangGraph tools. The agent calls `store_memory` / `search_memory` explicitly. No automatic extraction. Right choice when you are already on LangGraph and want the framework-native idiom.

## The five architectural decisions that matter

1. **Write policy** — what to write, when. "Everything" creates noise and storage cost. "Structural facts, user-stated preferences, workflow outcomes, named entities" is the production default.
2. **Forgetting policy** — episodic benefits from time-decayed summarisation; semantic only forgets on explicit user instruction or conflict; procedural retains successes, drops rejected.
3. **Conflict resolution** — newest-wins is the simple default. Production: user-stated beats inferred, recent explicit beats older implicit, cross-category conflicts trigger a clarification turn.
4. **Retrieval strategy** — vector similarity alone underweights structured memory. The production pattern is **hybrid**: structured by entity match, episodic by recency + topic, semantic by vector similarity, all blended for the prompt assembly.
5. **Privacy and governance** — user-facing controls (view, edit, erase), explicit lawful basis per memory category, retention periods, DPIA. UK ICO has been explicit through 2025-2026 that memory requires transparency, control, and explicit data-subject rights.

## Verification

- **LongMemEval** for raw recall quality; target ≥ 90.
- **Cross-session task completion** on a held-out set of multi-session tasks; measure completion rate vs a no-memory baseline.
- **Token-per-query** vs full-context; if you're not at ≤ 30% of full-context, the platform isn't doing its job.
- **p95 write latency**; if it blocks the conversation turn, it's the wrong tier.
- **Contradiction set** — feed the same user stating two contradictory preferences in two sessions. Verify the resolution matches your policy.

## Gotchas

- **Memory is not retrieval.** Write and forget are design decisions, not afterthoughts. Most teams underweight them.
- **LongMemEval shows 1M-token models drop 30%+ on prior-session recall without a memory layer.** Don't trust the context window alone.
- **Vector-only memories lose connections between facts.** Graph or hybrid for anything that needs relational reasoning.
- **Procedural memory crosses user boundaries.** A workflow learned with user A applying to user B is a data-protection event in most jurisdictions.
- **The 7K vs 25K token number (Mem0 v3 on LongMemEval)** is the kind of result that motivates this whole category; it is also vendor-reported — re-benchmark on your workload.
- **Don't store the system prompt as memory.** It changes per-deployment and pollutes retrieval.
- **Forgetting is a feature, not a bug.** A memory layer that never forgets will eventually surface stale, contradicting, or harmful entries. Build the retention policy before you build the write path.
- **Bi-temporal modeling is a big lift.** If your facts don't actually change over time, Zep's temporal model is overkill — use Mem0.

## Related

- `documentation/docs/policies/lessons/agent-self-correction.md` — reflection (intra-task) vs memory (inter-task)
- `documentation/docs/policies/patterns/agent-context-engineering-2026.md` — context window as working memory
- `documentation/docs/policies/patterns/agent-cost-optimization.md` — memory is a cost lever
- `documentation/docs/policies/cloudflare/vectorize-2026.md` — one possible vector backend for a memory platform
- `documentation/docs/policies/patterns/multi-agent-orchestration.md` — shared memory across agents

## Source URLs (verified 2026-08-09)

- "Agent Long-Term Memory in 2026: Letta, Mem0, Zep, LangMem" — https://agentmarketcap.ai/blog/2026/04/08/agent-long-term-memory-architecture-letta-memgpt-langmem-zep
- Mem0: Graph-Based Memory Solutions for AI Context — https://mem0.ai/blog/graph-memory-solutions-ai-agents
- "Agent Memory Systems 2026" (Kush Chheda) — https://www.kushchheda.com/blog/agent-memory-systems-2026-mem0-letta-zep-long-running-ai-agents-architectures
- "Mem0 vs Letta vs Zep: Agent Memory 2026" (AI Workflow Lab) — https://aiworkflowlab.dev/article/agent-memory-mem0-vs-letta-vs-zep-2026
- "AI Agent Memory in 2026: Mem0, Letta, Zep, Rakuten" (Medium) — https://buzzgrewal.medium.com/ai-agent-memory-in-2026-how-mem0-letta-and-zep-cut-tokens-90-and-rakuten-cut-errors-97-461b5d67e92e
- Graphiti (Zep's temporal graph engine) — https://github.com/getzep/graphiti
- MemoryOS paper (arXiv 2506.06326) — https://arxiv.org/abs/2506.06326
