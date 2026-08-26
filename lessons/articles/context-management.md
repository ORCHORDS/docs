# context-management

- **Issue**: Long-running agents hit the context-window wall, lose coherence, and either loop or pay 3× the tokens. Frontier models advertise 200K–1M tokens but the practical threshold for proactive management is under 50% of nominal capacity.
- **Date**: 2026-08-09
- **Repo**: example-org/example-repo
- **Author**: kb-batch-2
- **Status**: Active; complements `documentation/categories/patterns/agent-context-engineering-2026.md`.

## Symptom

- Agent quality drops sharply as the session gets long. The same prompt at turn 5 gets a different answer than at turn 50.
- Token spend grows super-linearly with session length; the cost per task at the 100th turn is 5× the cost at the 10th.
- You told the agent a critical fact in turn 1. It forgot by turn 30. Re-pasting fixes it. You have a "did you remember X?" prompt template.
- Multi-session handoff loses critical decisions. The new session re-derives things it should have inherited.

## Root cause

**Raw context size matters less than context quality.** Even 1M-token models degrade with context rot. The Anthropic, JetBrains, and SWE-agent research converges on three mechanisms that fix this — and they are not mutually exclusive:

1. **Compaction** — summarise the conversation while preserving architectural decisions
2. **Structured external memory** — progress files, checkpoints, databases
3. **Sub-agent delegation** — offload bounded subtasks; return compact summaries

## The three primitives (Anthropic 2026 model)

| Primitive | What it solves | API surface | Default trigger | When to use |
|---|---|---|---|---|
| **Tool search** | Tool definition overhead | `tool_search` (load on demand) | n/a | Tool set exceeds ~20 tools |
| **Context editing** | Accumulated old `tool_result` blocks | `clear_tool_uses_20250919` beta | 100K input tokens | Long loops with many intermediate results |
| **Compaction** | Context window nearing limit | `compact_20260112` beta | 150K input tokens (min 50K) | Task spans more than one context window |
| **Prompt caching** | Recomputation cost | `cache_control` block | n/a | Large but stable tool set |

These four **stack**. They solve problems at different points in the pipeline:

- Large but stable tool set → prompt caching. Does not reduce tokens, but reduces recomputation cost to 10% on later requests.
- Large tool set that also needs context reduction → add tool search.
- Loop produces many intermediate results → add context editing to clear them.
- Task exceeds one context window → add compaction, while keeping the prefix consistent to preserve cache hits.

### Compaction specifically (server-side)

- The API watches the input token count, generates a summary at the trigger threshold, returns a `compaction` content block.
- Default trigger: 150K input tokens (configurable; minimum 50K).
- You pass the `compaction` block back on subsequent requests. The API drops everything before it.
- Default summarization prompt writes into `<summary></summary>` tags. You can replace it via the `instructions` parameter.
- `pause_after_compaction: true` lets you append extra content (recent messages, pinned instructions) before the next turn.

### The cache-friendly compaction trick

During compaction, the API reuses the **exact same** system prompt, user context, system context, and tool definitions as the parent session. That means the cached prefix still hits. Only the compaction prompt itself is new tokens. **Never change the tool set mid-session** or you break the cache and double the cost of compaction.

## Tool-result clearing specifically

- Default trigger: 100K input tokens. Configurable.
- `keep` (default 3) tool uses are preserved; older `tool_result` blocks are cleared.
- `exclude_tools` lets you protect specific tool results (e.g., user-supplied context you need for the rest of the session).
- `clear_tool_inputs` strips the input arguments from the cleared blocks; the result is also dropped.
- The kept records still show "this tool was called" so the agent knows the history happened.

## The 2026 production pattern

Claude Code runs all of this. For a 200K-token context window split across conversation history, file reads, tool outputs, `CLAUDE.md` instructions, and auto-loaded memory:

- **Real-time monitoring** of token usage, broken down by category.
- **Automatic compaction** at the `auto_compact_limit` (default near the window).
- **Manual `/compact`** for the user-initiated case.
- **`/clear`** to start a completely fresh context — preferred when switching between unrelated tasks.
- **`/context`** to inspect current usage by category.

The two-stage threshold pattern (from production research):

- **Early warning at ~64%** — trigger memory sync; write important state to external storage while the agent still has enough context to do so coherently.
- **Session switch at ~80%** — initiate graceful handoff to a fresh session.
- The gap between stages is critical. It gives memory sync time to complete before the session must end.

## Observation masking vs LLM summarization

The JetBrains 2025 study compared two summarization strategies on 250-turn SWE-agent trajectories:

- **Observation masking** — replace older environment observations (file contents, command output) with placeholders while preserving reasoning and actions. A rolling-window approach.
- **LLM summarization** — use a separate model to compress historical interactions into a narrative summary.

Both reduced costs by >50% versus unmanaged contexts. **Observation masking is cheaper and often more effective** for code-like workloads. Apply summarization selectively for genuinely complex historical state.

## Anchored iterative summarization (Factory, Anthropic)

The structure that scores highest on accuracy for preserving technical details across compression cycles has four fields:

1. **Intent** — what the user wanted
2. **Changes made** — file paths, what was edited
3. **Decisions taken** — and why
4. **Next steps** — pending work

Anything that does not fit these four is the first thing to discard.

## Handoff quality beats storage

A good handoff is a **narrative**, not a data dump. The next session needs to know what matters right now, not just what happened. Use external files as narrative bridges (`claude-progress.txt`, JSON feature lists, structured decision logs). They cost almost nothing and dramatically reduce cold-start confusion.

## Verification

- **Cost per task by turn bucket** (turns 1-10, 11-30, 31-60, 61+). The shape should be roughly linear with a step at the compaction threshold, not exponential.
- **Compaction survival rate** — after a compaction, the model can recall facts from before the summary in N% of cases. Track N.
- **Cache hit rate after compaction** — should remain high if the prefix is preserved. If it crashes, you changed something mid-session.
- **p95 time-to-first-token** for cache-hit requests. If it climbs, your cache is missing or you're crossing a region boundary.
- **Sub-agent call rate** — how often the orchestrator delegates vs does the work itself. A healthy long-running agent offloads ≥ 30% of work to sub-agents.

## Gotchas

- **Context rot starts well before the limit.** Set early-warning thresholds at 60–70% of nominal capacity.
- **Memory sync and session switch are different operations.** Don't trigger them at the same time. Stage with a buffer.
- **Don't change the tool set mid-session** if you want prompt caching to work.
- **Compaction loses subtle context.** A bug fix in turn 12 may not survive into turn 25. For tasks where this matters, prefer sub-agent delegation over compaction.
- **Tool-result clearing keeps the record but drops the result.** If a tool call is genuinely needed downstream, exclude it.
- **Observation masking is not "delete old turns."** It replaces *observations* (file contents, output) with placeholders, but preserves the *reasoning*. That is the load-bearing part.
- **Don't paste the full system prompt into a memory entry.** The system prompt changes per-deployment; memory should not.
- **External memory files need version control.** `claude-progress.txt` without a commit history is a future incident.

## Related

- `documentation/categories/patterns/agent-context-engineering-2026.md` — the broader pattern
- `documentation/categories/patterns/prompt-caching-2026.md` — caching is the cost lever for context-heavy prompts
- `documentation/categories/patterns/agent-memory-2026.md` — long-term memory platforms
- `documentation/categories/lessons/agent-self-correction.md` — reflection fits inside the context window
- `documentation/categories/cloudflare/sandbox-2026.md` — sub-agent delegation pattern via sandboxes

## Source URLs (verified 2026-08-09)

- Anthropic cookbook: Context engineering (memory, compaction, tool clearing) — https://platform.claude.com/cookbook/tool-use-context-engineering-context-engineering-tools
- Anthropic Compaction docs — https://platform.claude.com/docs/en/build-with-claude/compaction
- Claude prompt caching docs — https://platform.claude.com/docs/en/build-with-claude/prompt-caching
- "Claude Long-Agent Context Management Toolkit" — https://claudeapi.com/en/blog/dev-guides/claude-context-management-long-agent-2026/
- "Context Window Management and Session Lifecycle for Long-Running Agents" — https://zylos.ai/research/2026-03-31-context-window-management-session-lifecycle-long-running-agents/
- "Context Management in Claude Code" (YouTube) — https://www.youtube.com/watch?v=eW3oTyfeWZ0
