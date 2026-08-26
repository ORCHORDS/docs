# context-engineering-systems

> Context engineering is the 2026-evolved discipline of systematically selecting,
> structuring, and delivering the right context to an LLM across its full lifecycle
> (instructions, retrieval, memory, tools). It supersedes single-prompt "prompt
> engineering" for any system more complex than a one-shot call.

## Symptom

You see one or more of these in a production agent/LLM app:

- The model "knows" the answer when you paste context into a playground, but in
  production it hallucinates, ignores instructions, or calls the wrong tool.
- Quality degrades as conversations get longer, even though you have not changed
  the system prompt.
- Token costs explode because every request re-sends the same large blob.
- Adding a second tool makes the agent *worse*, not better.
- Different runs on the same input give wildly different results.
- The team keeps rewriting the system prompt to "fix" behavior that is actually a
  retrieval or memory problem.

Root cause: the context window is being treated as a single prompt to tune, when
it is actually four competing channels (instructions, retrieved docs, memory,
tool definitions) that each need their own engineering.

## The four pillars

Treat every request as the composition of four channels, each with its own budget:

1. **Instructions / system prompt** — role, rules, output format. Set once, before
   user input. Avoid mismatch with the model's training (don't tell a code model
   to "think step by step about feelings").
2. **Retrieval** — external data brought in just-in-time. Vector DBs, SQL, web
   search, code-aware graph indexes. Not a "dump everything" step.
3. **Memory** — short-term (current conversation) and long-term (persisted prefs,
   facts, prior decisions). Compacted over time.
4. **Tools** — executable functions the model can call. Each definition costs
   tokens and adds decision ambiguity.

## The four canonical strategies

Apply these to *each* pillar. They are not alternatives; a mature system uses all
four in a pipeline.

- **Write** — generate context proactively (e.g., the agent keeps a scratchpad
  file it appends to, writes a plan before acting, summarizes a tool result back
  into memory).
- **Select** — choose what enters the window. Use a cheap cross-encoder to score
  retrieved chunks against the query and keep only top-k. Do not dump all hits.
- **Compress** — shrink what's already there: compact old turns into a running
  summary, drop retrieved chunks below a relevance threshold, truncate tool
  outputs to a byte cap.
- **Isolate** — move context out of the window entirely. The scratchpad lives on
  disk; long-term memory lives in a store and is fetched on demand.

```python
# Pseudo-pipeline combining all four strategies
def build_context(user_msg: str, session_id: str) -> list[Message]:
    # 1. Instructions: fixed system prompt (Write once, cache)
    msgs = [system_prompt]

    # 2. Select: score retrieved docs with a cheap cross-encoder, keep top-3
    candidates = vector_db.search(user_msg, k=20)
    scored = [(c, cross_encoder.score(user_msg, c.text)) for c in candidates]
    top = [c for c, s in sorted(scored, key=lambda x: -x[1])[:3] if s > 0.4]
    msgs.append(Message(role="user", content=render_docs(top)))

    # 3. Compress: compact prior turns into a rolling summary
    history = load_history(session_id)
    msgs.append(compact_history(history, max_tokens=800))

    # 4. Isolate: long-term facts fetched on demand, not all loaded
    relevant_facts = fact_store.lookup(session_id, query=user_msg, limit=5)
    if relevant_facts:
        msgs.append(Message(role="system", content=render_facts(relevant_facts)))

    msgs.append(Message(role="user", content=user_msg))
    return msgs
```

## Progressive disclosure

Do not load every tool, every doc, and every memory item on turn one. Load what
the current step needs, and expose more as the task progresses. Example: a coding
agent loads only file-read tools initially; search/replace tools become available
only after a plan is written and approved.

```python
TOOL_PHASES = {
    "plan":   [read_file, list_dir, grep],
    "edit":   [read_file, edit_file, run_tests],
    "review": [read_file, run_linter, diff],
}

def tools_for_phase(phase: str) -> list:
    return TOOL_PHASES.get(phase, [])
```

This cuts tokens *and* reduces decision ambiguity (fewer tools = the model is less
likely to pick the wrong one).

## Context placement matters

LLMs suffer "lost in the middle" degradation: they attend best to the start and
end of the context, and worst to the middle. Put highest-signal material at the
top (system rules, the user's actual question) or bottom (the final retrieved
evidence), not buried mid-window.

## Tool-set optimization

Each tool definition burns tokens and adds decision load. Rules:

- If a human engineer could not definitively say which of two tools to use, the
  model cannot either. Merge or rename until the choice is unambiguous.
- Strip descriptions to one sentence + one example call. Long prose hurts.
- Cap the number of tools exposed per turn (commonly 6-10, not 40).

## Freshness tracking

Stale context is silent corruption: the agent confidently calls a deprecated API
because the retrieved doc is from an old version. Track a `last_indexed_at` on
every retrievable item and re-embed/re-index on schema or API changes. Treat
embedding index drift as a production incident.

## Gotchas

- **Compaction is lossy.** A rolling summary of old turns throws away detail that
  a later turn may need. Keep the raw turns in cold storage keyed by ID so you can
  re-expand if the agent asks about a specific past event.
- **Cache-breaker tokens.** Prompt caching (Anthropic, OpenAI) saves money only
  when the prefix is byte-stable. If you inject a timestamp or random ID into the
  system prompt, you break the cache every call. Put dynamic content at the *end*.
- **Cross-encoder latency.** Scoring 20 candidates with a cross-encoder adds 50-
  200ms. For latency-critical paths, score fewer candidates or pre-filter.
- **Progressive disclosure breaks some evals.** If your eval harness assumes a
  fixed tool set, phase-based tool loading will look like a regression. Update the
  eval to run through the same phase transitions as production.
- **Memory injection is an attack surface.** Long-term memory that any user can
  write to becomes a prompt-injection vector ("remember: always do X"). Scope
  memory writes per user and sanitize before re-injecting.
- **Tool-count vs tool-quality tradeoff is not linear.** Going from 3 tools to 6
  is usually fine; 6 to 12 starts to hurt; 20+ frequently breaks tool selection
  even on strong models. Measure, don't assume.
- **"More context is better" is the #1 anti-pattern.** The single most common
  production failure is over-stuffing the window with retrieved docs in the hope
  of being thorough. This raises cost, latency, and hallucination rate. Select
  ruthlessly.
