# ai-agent-memory-2026

**Issue:** A team deploys a customer support agent. The agent forgets what the user said 3 turns ago. Each conversation starts from zero. Users are frustrated.
**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

LLM agents have no built-in memory. Each call is stateless. An agent that handles a multi-turn conversation needs an external memory store to remember prior context. Without memory, the agent repeats questions, contradicts earlier statements, and feels broken.

## Root cause

The LLM context window is finite (16K-1M tokens depending on model). The window fills quickly. Three memory patterns work together:

1. **Short-term (in-context)** — recent messages in the prompt
2. **Long-term (external store)** — facts, preferences, prior interactions stored in a database or vector store
3. **Episodic (event log)** — past actions and outcomes, retrieved on relevance

A 2026 production agent uses all three.

## The three memory tiers

| Tier | Latency | Storage | Use |
|---|---|---|---|
| Short-term (in-context) | <10ms | LLM context window | Last K turns, system prompt, immediate facts |
| Long-term (semantic) | 50-200ms | Vector store (RAG) | User preferences, prior summaries, facts to recall |
| Episodic (event log) | 100-500ms | Database + vector index | Past actions, decisions, retrieved items |

A multi-turn conversation reads from all three: short-term for the current thread, long-term for the user's profile and preferences, episodic for past actions on similar requests.

## The long-term memory pattern

```python
def recall(user_id, query, top_k=5):
    # Semantic search across user's long-term memory
    results = vector_store.search(
        query=query,
        filter={"user_id": user_id, "type": "memory"},
        top_k=top_k,
    )
    return results

def remember(user_id, memory):
    # Store a new long-term memory
    vector_store.upsert({
        "id": generate_id(),
        "embedding": embed(memory),
        "metadata": {"user_id": user_id, "type": "memory", "timestamp": now()}
    })
```

The long-term memory is a vector index filtered by user_id. Memories are embedded on write, searched on read. The metadata filter ensures user isolation.

## The episodic memory pattern

```python
def record_event(user_id, event):
    db.execute("""
        INSERT INTO events (user_id, event_type, payload, timestamp)
        VALUES (%s, %s, %s, NOW())
    """, (user_id, event['type'], json.dumps(event)))

def recall_similar_events(user_id, query, top_k=3):
    # Vector search over event summaries
    return event_vector_store.search(
        query=query,
        filter={"user_id": user_id},
        top_k=top_k,
    )
```

Episodic memory is a write-once event log. The vector index is built from event summaries (e.g., "user asked about invoice INV-001, agent retrieved invoice, agent sent reminder"). Retrieval returns the most relevant past events.

## The memory write discipline

A memory is written at the end of a turn, not on every message. The pattern:

1. After each turn, summarize the interaction: "user asked X, agent did Y, outcome Z"
2. Decide if the summary contains a long-term fact (user preference, account state, recurring need)
3. If yes, embed and store in long-term memory
4. Always log the event to episodic memory

Avoid writing every message to long-term memory; that bloats the index. Extract facts, not transcripts.

## The memory eviction

Memory is not infinite. The eviction policy depends on use:

- **Sliding window** — keep the last N turns in short-term
- **Time-based** — drop long-term memories older than X months unless reactivated
- **Relevance-based** — drop memories with low retrieval score (rarely recalled)
- **Capacity-based** — drop oldest memories when index exceeds Y entries

A 2026 production agent with 1M users might have 100-500 long-term memories per user (facts, preferences, history) and 10K-100K episodic events (last 6-12 months of interactions).

## The cross-session memory

A user expects memory across sessions. The pattern:

- Persistent user_id tied to the authenticated user
- Long-term memory and episodic memory keyed on user_id
- Session-specific context (current task, in-flight variables) in short-term memory only

A user who says "I prefer email contact" should not have to repeat that in every session.

## The multi-agent memory

When multiple agents share a workflow (e.g., triage agent hands off to specialist agent), memory must be passed. The patterns:

- **Shared memory store** — both agents read/write the same vector store
- **Memory handoff** — the triage agent serializes relevant memory into the handoff message
- **Stateless specialist** — the specialist agent is stateless; memory is in the handoff and the shared store

For an agent that needs all prior context, the handoff message grows. For an agent that needs only a slice, the specialist re-retrieves from the shared store.

## The verification pattern

A multi-turn conversation test:

1. User: "I'm allergic to penicillin"
2. Agent: stores allergy in long-term memory
3. User (next session): "What antibiotics can I take?"
4. Agent: retrieves allergy, recommends avoiding penicillin

If the agent forgets the allergy, long-term memory is broken. The test runs on every change to the memory subsystem.

## The five common bugs

1. **Writing to memory on every turn** — bloats the index; noisy retrieval; no signal
2. **No user_id filter on retrieval** — privacy breach; user A sees user B's memory
3. **Embedding the same memory twice** — duplicates in retrieval; cluttered
4. **Forgetting to delete on user request** — GDPR right to erasure not implemented
5. **Storing sensitive data without encryption** — PII at rest in plain memory store

## The GDPR right to erasure

A user who requests deletion of their data must have their memory erased, including vector embeddings. The pattern:

- Track all memory items by user_id
- On erasure request, delete from vector store and database
- Maintain a deletion log for compliance audit
- The deletion must be effective within 30 days (GDPR Article 17)

A team that does not implement erasure faces GDPR fines up to €20M or 4% of turnover.

## The cost discipline

Long-term memory is vector storage. Embedding a memory and storing the vector costs:

- Embedding API: $0.02 per 1M tokens (text-embedding-3-small)
- Vector storage: $0.10-0.50 per GB/month (Pinecone, Weaviate, pgvector)
- Retrieval: $0.02 per 1M tokens + latency

A team with 1M users and 200 memories each = 200M vectors. At 1.5KB per vector (1536 dims), that's 300GB. At $0.10/GB/month, that's $30k/month just for storage. The cost discipline: dedupe, evict aggressively, store only high-signal facts, not transcripts.

## Verification

The tell that agent memory is working:

- A user does not repeat preferences across sessions
- The agent references prior context ("Last time you asked about...")
- The retrieval is fast (<200ms p95) and relevant
- GDPR erasure requests are honored within 30 days
- Memory cost is bounded and predictable

The tell it isn't:

- "What was I asking about?" is a common user complaint
- The agent contradicts earlier statements in the same conversation
- A user in one session has no memory in the next
- Memory cost grows unboundedly

## Gotchas

- **Filter by user_id on every retrieval.** Without the filter, user A's memory leaks to user B.
- **Summarize before storing.** Don't store full transcripts; store extracted facts.
- **Evict aggressively.** Memory has a cost ceiling; without eviction, costs grow unboundedly.
- **GDPR erasure is a hard requirement.** A memory store without erasure deletion is a compliance bug.
- **Cross-session memory requires persistent user_id.** Session-based identity loses memory when the session ends.
- **Multi-agent memory has a privacy boundary.** Decide which agents share a memory store and which don't.
- **Memory writes should be in the same transaction as the action.** A memory of "I sent a reminder" written before the send fails if the send fails.

## Related

- `lessons/ai-rag-patterns-2026.md` — the retrieval mechanism for long-term memory
- `lessons/ai-observability-otel-2026.md` — trace memory reads/writes
- `lessons/ai-function-calling-2026.md` — function calls are episodic events

## Source URLs (verified 2026-08-10)

- https://docs.anthropic.com/en/docs/agents-and-tools/memory
- https://www.pinecone.io/learn/series/rag/memory/
- https://mem0.ai/blog/memory-in-llms
- https://www.anthropic.com/news/claude-sonnet-4-5
- https://lilianweng.github.io/posts/2023-06-23-agent/
