# prompt-caching-2026

- **Issue**: LLM bills grow linearly with the prefix tokens that get re-sent every turn. Anthropic, OpenAI, and Google all ship a prompt-cache product, with different TTLs, write fees, and minimum-prefix rules. The break-even is around 2 hits per write, but only if the prefix is byte-stable.
- **Date**: 2026-08-09
- **Repo**: example-org/example-repo
- **Author**: kb-batch-2
- **Status**: Active; complements `patterns/agent-cost-optimization.md`.

## Symptom

You add a multi-turn agent. The system prompt is 6 KB, the tool schemas are 4 KB, retrieved context is 8 KB. The first turn costs $X in input. The second turn repeats all of it. By turn 10, you have paid for the system prompt 10 times. Token bills balloon, latency does not improve, and rate-limit budget is consumed by the same prefix on every request.

## Root cause

Prefix tokens are paid for in full on every call unless the model provider identifies a byte-identical prefix against a recent entry in its cache. The cache is keyed by exact bytes, including whitespace, JSON key order, and the SHA-256 of any embedded images. **A single byte change anywhere in the cached block invalidates everything from that point forward.**

## The 2026 provider matrix

| Provider | Discount on read | Write cost | Min prefix | Default TTL | 1-hour TTL |
|---|---|---|---|---|---|
| Anthropic Claude | 0.1× (90% off) | 1.25× (5 min) or 2× (1 hr) | 512–4,096 tokens (model-dependent) | 5 min, refreshes on read | Yes, via `cache_control: { ttl: "1h" }` |
| OpenAI GPT-5.5/5.6+ | 0.1× (90% off) | 1.25× (GPT-5.6+); free on automatic pre-GPT-5.6 | 1,024 tokens; 128-token increments | 5–10 min in-memory; up to 24 hr extended (mandatory on GPT-5.5+) | Up to 24 hr via extended retention |
| OpenAI GPT-4.1 (legacy) | 0.5× (50% off) | Free on automatic | 1,024 tokens | In-memory | No |
| Google Gemini 2.5+ | 0.1× (90% off) | Standard input rate + $1.00–$4.50 / MTok / hour storage | 2,048–4,096 tokens | 60 min default (explicit) | Up to 24 hr |
| AWS Bedrock (Claude) | 0.1× (90% off) | 1.25× (5 min) or 2× (1 hr) | 1,024–4,096 tokens | 5 min | GA on Sonnet 4.5 / Haiku 4.5 / Opus 4.5 since Jan 2026 |

The headline 2026 rule: **cached reads are 0.1× base input across all three majors** for current-generation models. The 2024-era "OpenAI is 50%, Anthropic is 90%" shorthand is now wrong for new models.

## Anthropic specifics (use the explicit `cache_control` breakpoints)

- Up to **4 cache breakpoints per request**. Place them in staircase order: persona → persona+tools → persona+tools+examples → persona+tools+examples+conversation. Anything below a breakpoint that changes re-reads the prefix; anything above is cached.
- **When mixing TTLs, longer TTLs must appear before shorter ones** in the prompt. Otherwise billing is wrong.
- **Minimum cacheable length is model-dependent**:
  - 512 tokens: Claude Fable 5, Claude Mythos 5 (native API)
  - 1,024 tokens: Claude Opus 4.8, Sonnet 5, Sonnet 4.6, Sonnet 4.5, Sonnet 4
  - 2,048 tokens: Claude Mythos Preview, Claude Opus 4.7
  - 4,096 tokens: Claude Opus 4.6, Opus 4.5, Haiku 4.5
- 1-hour cache break-even: **switch when your effective request frequency for a given prefix drops below one request per 90 seconds**. Above that frequency the 5-minute cache is cheaper (you save the 0.75× write premium).
- Cache hits are **not deducted against rate limits** (Anthropic). This is a free side benefit at high QPS.

## OpenAI specifics (mostly automatic)

- Caching is automatic for prompts ≥ 1,024 tokens. No flag. Discount appears in `usage.prompt_tokens_details.cached_tokens`.
- **GPT-5.6+ charges 1.25× uncached input for cache writes** on both automatic and explicit modes. Pre-GPT-5.6 automatic cache writes are free.
- Extended retention (up to 24 hr) is mandatory on GPT-5.5 and later. Use it for predictable hot paths that exceed the 5–10 min in-memory window.
- Cached tokens **still count against your tokens-per-minute cap** (Anthropic does not). Plan for this at high QPS.

## The break-even and the staircase

The break-even point is **~2 cache hits per cache write**, because the read is 0.1× and the write is 1.25× or 2× depending on TTL. In practice, well-placed breakpoints see 50–500 hits per write — the published case studies (Tufail Khan, Stack Stories) report **78% and 84% bill reductions** for steady traffic.

The four breakpoints, in this order:
1. **System prompt** (changes ~monthly)
2. **Tool schemas** (changes ~monthly)
3. **Retrieved RAG context** (changes per session)
4. **Conversation history** (grows within session)

If you have a fifth candidate (examples, few-shot library, persona-conditioned docs), put it between #2 and #3.

## Verification

- **Instrument the response**: read `usage.cached_tokens` (OpenAI) or `usage.cache_creation_input_tokens` + `usage.cache_read_input_tokens` (Anthropic) on every response. If both are zero after 50+ requests, your prefix is not stable.
- **Per-route hit rate**. If your highest-volume agent has <80% cache hit rate, you have an architecture problem, not a provider problem. Common causes: timestamp injection in system prompt, random user IDs above the breakpoint, dynamic tool lists.
- **Latency**: cache hits reduce time-to-first-token. If you do not see this, the cache is missing or the model is on a cold path.
- **Cost per task**, not cost per token. A route that uses more cache but more total tokens can still be cheaper end-to-end.

## Gotchas

- **Bytes are bytes.** Whitespace, JSON key order, and image hashes are part of the key. Do not dynamically generate the prefix.
- **The cache is per-region and per-organization.** A cache hit in `us-east-1` is not a hit in `eu-west-1`. Plan multi-region accordingly.
- **Bumping a model version invalidates the entire cache** even if the prompt is identical. Be ready for a cold-cache spike on model upgrades.
- **Cache reads do not improve model quality.** They improve cost and latency. Do not pretend a "fast mode" exists.
- **Don't cache the volatile suffix.** If you put per-turn user data above the breakpoint, you pay 1.25× to write it every turn and never benefit. Stable prefix only.
- **1-hour cache is not always a win.** If your request frequency keeps the 5-minute cache warm, the 0.75× write premium on the 1-hour tier is wasted money.
- **Anthropic cached entries are isolated between workspaces within an organization.** Test before assuming a hit in staging will hit in prod.
- **OpenAI GPT-5.6+ 1.25× write cost is new.** If you are budgeting on a pre-2026 number, update it.

## Related

- `documentation/docs/policies/patterns/agent-cost-optimization.md` — caching is one of four levers (caching, routing, batching, model tier)
- `documentation/docs/policies/patterns/agent-context-engineering-2026.md` — what to put in the cached prefix vs the volatile suffix
- `documentation/docs/policies/cloudflare/ai-gateway-best-practices.md` — Cloudflare AI Gateway's caching layer complements provider caching
- `documentation/docs/policies/lessons/agent-self-correction.md` — self-correction can multiply the cost that caching helps amortize

## Source URLs (verified 2026-08-09)

- Anthropic prompt caching (Claude Platform docs) — https://platform.claude.com/docs/en/build-with-claude/prompt-caching
- OpenAI prompt caching guide — https://developers.openai.com/api/docs/guides/prompt-caching
- AWS Bedrock 1-hour prompt caching (Jan 2026) — https://aws.amazon.com/about-aws/whats-new/2026/01/amazon-bedrock-one-hour-duration-prompt-caching/
- "Anthropic vs OpenAI Prompt Caching 2026: Cost Math" — https://ofox.ai/blog/prompt-caching-cost-math-anthropic-vs-openai-2026/
- "Prompt Caching breakdown: Cut token spend in 2026" (Flexera) — https://www.flexera.com/blog/ai/prompt-caching-breakdown/
- "Cutting our Claude API bill by 78% with prompt caching" — https://dev.to/tufailkhan457/cutting-our-claude-api-bill-by-78-with-prompt-caching-1fon
- "How I Cut Our Anthropic Bill by 84%: A Prompt Caching Playbook for 2026" — https://www.thestackstories.com/blog/prompt-caching-claude-cost-cuts-2026
- "OpenAI Prompt Caching: How It Works and What It Saves" — https://proxyllm.ai/blog/openai-prompt-caching-explained
- "OpenAI vs Claude prompt caching cost" (aifreeapi) — https://www.aifreeapi.com/en/posts/openai-vs-claude-prompt-caching-cost
