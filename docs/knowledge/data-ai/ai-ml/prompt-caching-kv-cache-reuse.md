# prompt-caching-kv-cache-reuse

**Issue:** Agentic workloads re-send the same 50k tokens of system prompt, tool definitions, and RAG context on every turn — paying full input price and waiting through full prefill each time. Most teams know prompt caching exists but treat it as automatic, then discover cache hit rates near zero because a timestamp or growing conversation sits at the front of the prompt. This article covers how provider prompt caching and self-hosted KV-cache reuse actually work, the pricing mechanics, and the prompt-layout discipline that makes hits reliable.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## How the mechanics work

1. **Caching saves the KV-cache, not the text.** After the first request, the provider keeps the key/value tensors from prefill; a later request whose prompt shares the exact same prefix skips recomputing them and reads from cache. That is why hits cut both cost (less compute billed) and time-to-first-token.
2. **Exact prefix match is required.** Caching matches token-for-token from position 0. Any change before the cached region — a date injected first, a reordered system block, even changed whitespace — invalidates everything after it. This is the single most common cause of zero hit rates.
3. **Anthropic uses explicit `cache_control` breakpoints.** You mark up to 4 blocks (system, tools, messages) with `cache_control: {"type": "ephemeral"}`. Writes cost 1.25x base input price for the 5-minute TTL (2.0x for the 1-hour TTL via `ttl: "1h"`); reads cost 0.1x — roughly a 90% discount. Minimum 1024 tokens to activate.
4. **OpenAI caches automatically.** No markup needed; prefixes over a threshold (1024 tokens) are cached opportunistically, TTL is ~5-10 minutes of inactivity, and cached input tokens are billed at 50% off. The trade: less control over what gets pinned.
5. **Gemini offers explicit context caching with long TTLs.** Cached content can live for hours and is configurable, but you pay ongoing storage per token-hour — worth it for large stable corpora (codebases, long manuals), wasteful for chatty short contexts.
6. **Self-hosted servers replicate this via prefix caching.** vLLM (automatic prefix caching / APC) and llama.cpp (`--cache-reuse` with a shared-server prompt cache) reuse KV blocks across requests that share prefixes. Same rule applies: static content first, dynamic content last.

## Prompt layout that gets hits

1. **Order blocks from most-stable to most-volatile:** system prompt → tool definitions → retrieved documents → few-shot examples → conversation history → user message. Anything that changes per request goes to the very end.
2. **Never put a timestamp, request-id, or "current date" at the top of the prompt.** Inject volatile data after the cached region, or round timestamps to the day so the prefix stays stable within a session.
3. **Freeze tool definitions.** Tool schemas are usually the biggest stable block; auto-generating them with stable serialization (sorted keys, no injected metadata) keeps the prefix byte-identical across requests.
4. **Keep cache warm within the TTL.** A 5-minute TTL means interactive agents naturally stay warm; batch jobs spaced 30 minutes apart on the 1-hour tier (Anthropic) or using Gemini's long TTL beat re-paying prefill. The 2x write cost pays for itself after ~2 reads.
5. **In multi-turn agents, append — never rewrite.** Trimming or summarizing earlier turns mid-session rewrites the prefix and kills the cache; if compaction is needed, do it at turn boundaries and budget for one cache rebuild.
6. **Measure hit rate, not vibes.** Anthropic returns `cache_creation_input_tokens` and `cache_read_input_tokens` in usage; OpenAI returns `cached_tokens` inside `prompt_tokens_details`. Log these per request — hit rate below ~80% on a stable-prefix workload means a layout bug.

## What it is worth

1. **Cost: 50-90% off cached input tokens** depending on provider (OpenAI 50%, Anthropic ~90% on reads, Gemini variable). For a 50k-token system prompt hit every turn, this is the single largest lever on agent unit economics.
2. **Latency: TTFT down up to ~85% for long prompts** on Anthropic-class caching, since prefill of the cached prefix is skipped entirely.
3. **The math gate:** caching pays when repeated requests share a prefix longer than the provider minimum (1024 tokens) within the TTL window. Unique one-shot prompts never hit — do not add cache_control ceremony to stateless endpoints.
4. **Cascade with model routing:** cached input tokens make the cheap-first cascade pattern cheaper still, because the flagship escalation re-reads the same prefix at 10% of input price.

## Anti-patterns

1. **Injecting "today is {ISO timestamp with seconds}" at the top of the system prompt** — one line of convenience zeroes the entire cache. Place it after the cached breakpoint.
2. **Assuming OpenAI-style automatic caching means Anthropic caches too** — Anthropic needs explicit `cache_control` markers; porting the same prompt between providers silently loses the discount.
3. **Rewriting conversation history each turn (reformatting, reordering turns)** — the prefix changes, the KV-cache invalidates, and you pay full prefill every message.
4. **Caching volatile RAG results inside the stable region** — retrieved docs change per query; they belong after stable blocks, or cached per-document with content-addressed keys.
5. **Treating a cache as a semantic store** — prompt caching is exact-prefix only. Semantic similarity of prompts does nothing; that is what embedding-based semantic response caching covers, which is a separate pattern.
