# agent-context-engineering-2026

**Issue:** Context engineering for AI agents — the discipline of curating what goes into the limited context window
**Date:** 2026-08-09
**Repo:** example-org/example-repo at 196e96e
**Author:** the platform team
**Status:** verified-live (https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)

## Symptom

The agent works fine for the first 20 turns. Then it
starts forgetting what you said an hour ago. It references
files it hasn't read. It repeats the same questions. The
context window is "200K tokens" but the agent behaves like
it has 30K. Costs spike because the agent is sending the
full 200K on every call. You add summarization, but the
summary is lossy and the agent misses key decisions. You
add RAG, but the retrieved chunks are unrelated to the
current task. You try compaction, but it fires at 98% and
the agent hallucinates a "context anxiety" panic. The bill
is $4,000/month. The team asks: "Why is this so hard?"

## Root cause

**Context engineering is not prompt engineering.** Prompt
engineering optimizes the static prompt. Context engineering
optimizes the *runtime* set of tokens — the system prompt,
retrieved chunks, tool results, conversation history,
caching, compaction, memory tiers — across the entire
session. It is the natural evolution of prompt engineering
as agents got longer-running and more complex.

**Three hard 2026 facts that change the design:**
1. Advertised 1M context ≠ effective context. RULER and MRCR v2 benchmarks show frontier models reliably use only **50-65%** of advertised window for multi-hop work. 200K-context = effective 130K, not 200K.
2. Long-context processing has **geometric cost escalation**. Claude Sonnet 4.6 charges 2x input / 1.5x output beyond 200K. Going from 100K to 500K tokens is more than 5x the cost, not 5x.
3. The field has converged on a **multi-layer cascade**: tool output compression + input eviction + LLM summarization + external memory offload. No single technique dominates.

**Source:**
- Anthropic — Effective context engineering: https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- Anthropic — Prompt caching: https://platform.claude.com/docs/en/build-with-claude/prompt-caching
- Anthropic — Tool use with prompt caching: https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-use-with-prompt-caching
- Anthropic — Prompt caching cookbook: https://platform.claude.com/cookbook/misc-prompt-caching
- Bedrock — Prompt caching: https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-caching.html
- Zylos — Long context architecture: https://zylos.ai/research/2026-02-18-long-context-ai-agents/
- Zylos — Compaction: https://zylos.ai/research/2026-04-21-agent-context-compaction-long-running-sessions/
- Zylos — Context window management: https://zylos.ai/research/2026-03-31-context-window-management-session-lifecycle-long-running-agents/
- Zylos — Long-running agent patterns: https://zylos.ai/research/2026-06-20-context-engineering-long-running-agents/
- Zylos — LLM context management: https://zylos.ai/research/2026-01-19-llm-context-management/
- Agent Patterns — Prompt caching: https://agentpatterns.ai/context-engineering/prompt-caching-architectural-discipline/
- TrueFoundry — Gateway-level context: https://www.truefoundry.com/blog/context-engineering-gateway-session-management
- arxiv 2601.06007 — Prompt caching evaluation: https://arxiv.org/abs/2601.06007
- ofox — LLM context benchmarks 2026: https://ofox.ai/blog/long-context-llm-benchmarks-200k-tokens-2026/
- Sukru — Context engineering 2026: https://sukruyusufkaya.com/en/blog/context-engineering-prompt-caching-long-context-rag-2026
- Dev.to — Anthropic dropped TTL: https://dev.to/whoffagents/anthropic-silently-dropped-prompt-cache-ttl-from-1-hour-to-5-minutes-16ao

## The "context engineering" concept

**Context engineering** is the set of strategies for curating
and maintaining the optimal set of tokens during LLM
inference, including all the other information that may
land there outside of the prompts. Coined formally by
Anthropic in September 2025; built on the prior
"prompt engineering" frame.

The problem: the context window is finite. The set of
*potentially* useful tokens is infinite. The engineering
task is to choose, at every turn, the smallest set of
tokens most likely to produce the model's desired behavior.

**4 strategies that compose (the production stack):**
1. **Tool output compression** (always-on) — truncate outputs > 2K tokens, write full to disk, replace with file path + 10-line preview
2. **Input eviction** (at ~85% fill) — offload large tool-call arguments to disk after persistence
3. **LLM summarization** (threshold-triggered) — single LLM call replaces hundreds of messages with structured summary
4. **External memory offload** (long-lived facts) — write to structured memory files as soon as facts are established

No single technique dominates. Production platforms
combine all four.

## The "prompt caching" pattern

**Anthropic prompt caching** is GA on all Claude models
since 2025 and standard in 2026. It caches the prefix
of a context window server-side with a 5-minute (or
1-hour) TTL. Subsequent calls with the same prefix get
a discount.

**Pricing (as of August 2026):**
| | Base input | 5-min cache write | 1-hour cache write | Cache read |
|---|---|---|---|---|
| **Claude Opus 5** | $5 / MTok | $6.25 / MTok | $10 / MTok | $0.50 / MTok |
| **Claude Sonnet 4.6** | $3 / MTok | $3.75 / MTok | $6 / MTok | $0.30 / MTok |
| **Claude Haiku 4.5** | $1 / MTok | $1.25 / MTok | $2 / MTok | $0.10 / MTok |

**Cache multipliers:**
- 5-min write: 1.25x base
- 1-hour write: 2x base
- Read: 0.1x base (90% discount)
- Output: unchanged

**Two ways to enable:**
```ts
// Automatic (recommended for multi-turn)
{ "cache_control": { "type": "ephemeral" }, ... }

// Explicit (for fine-grained control)
{ "tools": [..., {
  "name": "...",
  "description": "...",
  "cache_control": { "type": "ephemeral" }  // last tool
}]}
```

**Critical 2026 change (March 6, 2026):** Anthropic changed
the default TTL from 1 hour to 5 minutes. To use 1-hour
TTL, you MUST explicitly set `ttl: 3600`:

```ts
// Old (used to default to 1h, now defaults to 5min):
"cache_control": {"type": "ephemeral"}

// New (explicit 1h):
"cache_control": {"type": "ephemeral", "ttl": 3600}
```

If you disabled Anthropic's telemetry, you may also be
silently dropped to 5-min TTL — verify with
`cache_creation_input_tokens` and `cache_read_input_tokens`
in the response.

**Cache breakpoints:** up to 4 explicit markers per request.
Typical layout:
1. End of system prompt (stable)
2. End of tool definitions (stable within session)
3. End of document context (semi-stable)
4. End of conversation history (variable)

**Minimum cacheable lengths:**
- Claude Opus 5, Fable 5, Mythos 5: 512 tokens
- Claude Opus 4.7: 2,048 tokens
- Claude Sonnet 5 / 4.6 / 4.5: 1,024 tokens
- Claude Haiku 4.5: 4,096 tokens
- Claude Opus 4.5/4.6: 4,096 tokens

**Lookback window:** the system checks at most 20 positions
per breakpoint. If no match in the window, checking stops
or resumes at the next explicit breakpoint.

## The "3 cache busters" pattern

Three patterns consistently invalidate the cache:

1. **Modifying tool definitions mid-session.** Tool definitions sit in the prefix. Adding, removing, or changing a tool invalidates everything after the tool-definitions breakpoint. **Fix:** keep the tool list static across the session.

2. **Switching models mid-session.** Model-specific instructions go in the prefix. Switching from Sonnet to Opus invalidates the cache for the entire session. **Fix:** treat model switches as context boundaries; preserve the previous session's cache by not switching mid-task.

3. **Mutating the prefix to convey state.** Timestamps, session IDs, config, or per-turn metadata in early sections bust the cache on every call. **Fix:** place variable state in the dynamic tail, not the prefix.

## The "cache-friendly prompt layout" pattern

The layout that consistently achieves high cache efficiency:
- **Stable prefix (cacheable):**
  - System prompt (identity, instructions)
  - Tool definitions (static within session)
  - Project context (CLAUDE.md, AGENTS.md equivalent)
  - Static policy instructions
- **Dynamic tail (not cacheable):**
  - Retrieved documents for current task
  - Recent conversation history
  - Current user message
  - Live tool results

Put cacheable, static content at the top. Put dynamic
content at the bottom. The cache is matched as a prefix,
not a substring — one token change at the start invalidates
everything.

## The "compaction" pattern

**Compaction** is the practice of taking a conversation
nearing the context window limit, summarizing its
contents, and reinitiating a new context window with the
summary.

**The 4 viable strategies (per the field consensus):**
1. **Provider-native summarization APIs** (Anthropic `compact_20260112`, OpenAI)
2. **Structured "anchored iterative" compaction** with persistent section templates
3. **External memory offload** (MemGPT/Letta, Cognee)
4. **Retrieval-augmented episodic memory**

**Compaction threshold (THE most-important number):**
- **75% of model context limit, NOT 95-98%** — gives the model adequate output tokens to write a high-quality summary
- **Minimum size guard: 75K tokens or 10 turns, whichever comes first** — don't compact short conversations; the round-trip cost exceeds the benefit
- For a 200K model: 150K threshold
- Triggering at 98% leaves the model "context-anxious" and produces compressed, incomplete summaries

**Structured compaction template (required, not optional):**
The compaction summary MUST explicitly populate sections:
```
## Session Intent
[What the user is trying to accomplish]

## Files Modified
[Full paths, not names — paths not retained in the summary aren't recoverable]

## Key Decisions
[What was decided and why]

## Active Goals
[What's in progress]

## Next Steps
[What the agent should do next]
```

Freeform summarization is an anti-pattern. Use the structured
template.

**Compaction-aware cache invalidation (the hard part):**
Compaction is a hard semantic break. The moment compaction
fires, the entire prior cached prefix is stale.

**Anthropic's `compact_20260112` API** (beta April 2026)
handles this by placing a `cache_control` marker on the
compaction block itself. On subsequent turns, the system
prompt and the compaction summary are both served from
cache; only the new turns are billed as fresh input.

**Your responsibility:** verify that the cached prefix
the provider is serving matches the post-compaction
system prompt + compaction block, not a pre-compaction
prefix. Log every compaction event with a session token
and timestamp.

## The "memory tiers" pattern

Production agents use 4 memory tiers, each with different
storage + retrieval:

| Tier | What | Storage | Retrieval |
|---|---|---|---|
| **Working** | Current context window | The model | Implicit (in the prompt) |
| **Episodic** | Recent session summaries | Vector DB or KV | Similarity search by query |
| **Semantic** | Facts, preferences, conventions | Structured KB (your `MEMORY.md`) | Top-k by stack-word overlap |
| **Procedural** | Patterns, code, workflows | Files + RAG | Tag + search |

The `packages/shared-memory/lib.js` in this repo is a
minimal implementation: per-project `MEMORY.md` index +
`memory/<name>.md` entries + `runs/<session>.log` capture
logs. Retrieval is keyword overlap (top 5). Vector retrieval
is in the roadmap for > 500 lessons.

**Offload long-lived facts to external memory on write, not at compaction time.** Architectural decisions, user preferences, environment constants, and project conventions should be written to structured memory files (or a KV store) **as soon as they are established** — not extracted from conversation history during compaction.

## The "3-layer cascade" pattern

For long-running agent platforms, the recommended cascade
is:

**Layer 1 — Tool Output Compression (always-on):**
- Truncate tool outputs exceeding 2,000 tokens
- Write full output to disk
- Replace with a file path reference + 10-line preview

**Layer 2 — Input Eviction (at ~85% fill):**
- Remove large arguments from write-type tool calls after the content has been persisted
- Offload inputs exceeding 500 tokens to disk
- Re-inject only when the agent needs to reference the original

**Layer 3 — LLM Summarization (threshold-triggered):**
- Single LLM call replaces hundreds of messages with a structured summary
- Preserve the most recent 10% of turns verbatim as active working memory
- Use the structured template (Session Intent, Files Modified, Key Decisions, Active Goals, Next Steps)

Layers 1 and 2 are cheap (no LLM calls). Layer 3 is
expensive (one LLM call). Don't skip to Layer 3.

## The "long context window reality" pattern

**2026 benchmark reality (RULER + MRCR v2):**
- GPT-5.5, Claude Opus 4.7, DeepSeek V4 Pro: effective context ~200-400K for multi-needle
- Gemini 3.1 Pro: closest to full 1M, multi-needle degrades past 256K
- Single-needle retrieval: most frontier models fine to 1M

**Treat advertised windows as upper bounds, not effective ones.** Reliable retrieval up to roughly 200-400K tokens for multi-hop work.

**When to use long context vs RAG:**
- **Use long context (200K+) when:**
  - Self-contained, static corpora that fit
  - Multi-document reasoning where chunking destroys connections
  - Single-session analysis
- **Use RAG (even with 200K available) when:**
  - Corpora > 1M tokens
  - Dynamic data (news feeds, live databases)
  - Interactive agents where latency matters
  - Cost-sensitive, high-volume workloads
- **Hybrid (2026 best practice):**
  - RAG for factual retrieval
  - Compressed observation log for agent memory
  - Live context window for current task
  - Most production systems need both

## The "2-stage monitoring" pattern

For long-running agents, don't wait for context exhaustion.
Monitor usage in real time and trigger rotation proactively:

- **Early warning (e.g., 64% usage):** Trigger memory sync — write important state to external storage while the agent still has enough context to do so coherently
- **Session switch threshold (e.g., 80% usage):** Initiate graceful handoff to a fresh session

**Two-stage is best practice** because:
- Single-trigger-at-95% leaves no time for coherent handoff
- Single-trigger-at-50% wastes context
- The 64%/80% split gives a buffer window for the handoff narrative

## The "compaction anti-patterns" anti-patterns

### 1. Compacting at 95-98% (context anxiety)
- **Issue:** Agent has inadequate output tokens to write a coherent summary; "context anxiety" hallucination
- **Fix:** Threshold at 75%; minimum 75K tokens

### 2. Freeform summarization
- **Issue:** Key details lost; the next session doesn't know what matters
- **Fix:** Structured template (Intent, Files, Decisions, Goals, Next Steps)

### 3. Putting dynamic data in the prefix
- **Issue:** Cache invalidation on every call; 90% discount gone
- **Fix:** Timestamps, session IDs, per-turn metadata → last user message, not prefix

### 4. Switching models mid-session
- **Issue:** Cache invalidation; full cost of new session
- **Fix:** Treat model switches as context boundaries; finish current task first

### 5. Modifying tool definitions mid-session
- **Issue:** Tool list lives in the prefix; modifying it busts the cache
- **Fix:** Static tool list across the session; version-bump tools on the next session

### 6. Compacting short conversations
- **Issue:** Round-trip cost exceeds the benefit
- **Fix:** Minimum size guard (75K tokens or 10 turns)

### 7. Skipping layers 1 and 2
- **Issue:** LLM summarization is expensive; doing it on the full conversation wastes tokens
- **Fix:** Truncate tool outputs and evict inputs first; summarize only the residual

### 8. Inconsistent cache_control placement
- **Issue:** Cache hit rate drops; the 90% discount evaporates
- **Fix:** One consistent breakpoint at the end of the system prompt; explicit breakpoints only when you need fine-grained control

### 9. Assuming 1M context is effective
- **Issue:** RULER/MRCR show 50-65% effective for multi-needle; quality degrades past 200K
- **Fix:** Target 200K as the practical ceiling; use RAG beyond

### 10. Disabling telemetry silently dropping 1-hour TTL
- **Issue:** Your "1-hour cache" is actually 5 minutes
- **Fix:** Explicit `ttl: 3600` in cache_control; verify in usage response

## The "context engineering checklist" pattern

For a production agent:
- [ ] System prompt is byte-for-byte identical across turns (cacheable)
- [ ] Tool definitions are static across the session (cacheable)
- [ ] All variable data (timestamps, session IDs, per-turn metadata) is in the dynamic tail
- [ ] `cache_control: { type: "ephemeral" }` placed on the last cacheable block (automatic caching)
- [ ] Explicit `cache_control` breakpoints at: end of system prompt, end of tool defs, end of conversation history (explicit caching)
- [ ] For sessions > 5 min between calls: explicit `ttl: 3600`
- [ ] Tool output compression at 2K-token threshold (always-on)
- [ ] Input eviction at 85% fill
- [ ] LLM summarization at 75% threshold (with structured template)
- [ ] External memory offload on write (not at compaction time)
- [ ] 4-tier memory: working (context), episodic (vector), semantic (KB), procedural (files)
- [ ] Compaction events logged with session token + timestamp
- [ ] Post-compaction cache hit rate verified
- [ ] Token usage monitored per request, not just per session
- [ ] 30-40% target context utilization, not 90%+
- [ ] Tool exposure gated to current task phase
- [ ] Cache hit rate in observability (cache_read / total input > 0.5)
- [ ] Effective context budget (advertised × 0.5-0.65) used as the actual ceiling

## Verification
- **Test:** Cache hit rate > 0.5 on the second call in a session
- **Test:** Compaction fires at 75%, not 95%
- **Test:** Compaction summary uses the structured template
- **Test:** Cache invalidation on tool definition change
- **Test:** `cache_read_input_tokens > 0` after the second call
- **Test:** Tool output compression truncates outputs > 2K tokens
- **Live:** RULER/MRCR pass rate on the effective window, not advertised
- **Audit:** Re-read Anthropic's context engineering doc quarterly (the field moves fast)

## Gotchas
- **The "1M context" gotcha.** Advertised ≠ effective. RULER shows 50-65% for multi-needle.
- **The "1-hour cache default" gotcha.** As of March 6, 2026, default is 5 minutes. Explicit `ttl: 3600` required.
- **The "compact at 98%" gotcha.** Context anxiety; threshold should be 75%.
- **The "freeform summary" gotcha.** Use the structured template.
- **The "dynamic in prefix" gotcha.** 90% cache discount gone on the next call.
- **The "switch model mid-session" gotcha.** Cache invalidation; full cost of new session.
- **The "modify tool defs" gotcha.** Cache invalidation; static tool list across session.
- **The "disable telemetry" gotcha.** Silently drops 1-hour TTL.

## Related
- `cloudflare/mcp-on-workers.md` — the Cloudflare deployment target for an MCP server with context engineering
- `patterns/mcp-server-patterns.md` — the MCP design pattern (tool descriptions are context)
- `patterns/agent-iteration-discipline.md` — the iteration loop that consumes context
- `patterns/agent-skill-design.md` — the skill description is context
- `patterns/agent-skill-design.md#codex-skills-format` — same pattern in Codex Skills
- `patterns/codex-connector-integration.md` — Codex's prompt caching + compaction hooks
- `lessons/agent-iteration-discipline.md` — the meta-loop that includes compaction
- `packages/shared-memory/lib.js` — the minimal implementation of memory tiers
- `packages/mcp-server/src/index.js` — local MCP server that returns minimal context
- `packages/router/src/classify.js` — the classifier that decides which model gets which context
- `packages/router/src/server.js` — the prompt caching hooks for the router

**Source URLs (verified 2026-08-09):**
- Anthropic — Effective context engineering: https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- Anthropic — Prompt caching: https://platform.claude.com/docs/en/build-with-claude/prompt-caching
- Anthropic — Tool use + caching: https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-use-with-prompt-caching
- Anthropic — Prompt caching cookbook: https://platform.claude.com/cookbook/misc-prompt-caching
- Bedrock — Prompt caching: https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-caching.html
- Zylos — Long context architecture: https://zylos.ai/research/2026-02-18-long-context-ai-agents/
- Zylos — Compaction: https://zylos.ai/research/2026-04-21-agent-context-compaction-long-running-sessions/
- Zylos — Context window management: https://zylos.ai/research/2026-03-31-context-window-management-session-lifecycle-long-running-agents/
- Zylos — Long-running agents: https://zylos.ai/research/2026-06-20-context-engineering-long-running-agents/
- Zylos — LLM context management: https://zylos.ai/research/2026-01-19-llm-context-management/
- Agent Patterns — Prompt caching: https://agentpatterns.ai/context-engineering/prompt-caching-architectural-discipline/
- TrueFoundry — Gateway-level context: https://www.truefoundry.com/blog/context-engineering-gateway-session-management
- arxiv 2601.06007 — Prompt caching eval: https://arxiv.org/abs/2601.06007
- ofox — LLM context benchmarks 2026: https://ofox.ai/blog/long-context-llm-benchmarks-200k-tokens-2026/
- Sukru — Context engineering 2026: https://sukruyusufkaya.com/en/blog/context-engineering-prompt-caching-long-context-rag-2026
- Respan — Claude prompt caching 2026: https://www.respan.ai/articles/claude-prompt-caching
- Dev.to — Anthropic dropped TTL: https://dev.to/whoffagents/anthropic-silently-dropped-prompt-cache-ttl-from-1-hour-to-5-minutes-16ao
- Vellum — Prompt caching: https://www.vellum.ai/llm-parameters/prompt-caching
- Claude Code Camp — Cache in Claude Code: https://www.claudecodecamp.com/p/how-prompt-caching-actually-works-in-claude-code
- explainx — Context engineering 2026: https://explainx.ai/blog/context-engineering-clean-prompts-generator-2026
- Beri — Effective context engineering: https://www.beri.net/learning/anthropic-effective-context-engineering-agents
