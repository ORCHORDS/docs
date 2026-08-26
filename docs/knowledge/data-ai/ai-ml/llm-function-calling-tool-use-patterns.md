# LLM Function Calling and Tool Use — Schema Design, Error Handling, and Retry Patterns

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your AI agent has 80 tools registered. Every API call sends all 80
tool definitions, adding 12,000+ tokens to every request — 40% of
your token budget goes to tool schemas before the model sees the
user's question. The agent calls a payment tool with malformed
parameters, gets a raw stack trace back, retries with the same bad
parameters, loops 15 times, and burns $2 in tokens on a task that
should cost $0.01. Nobody notices until the monthly bill arrives.

## Context

Function calling (tool use) lets LLMs invoke structured operations
by emitting typed arguments that your application executes. In 2026,
all major providers (OpenAI, Anthropic, Google) support tool use with
JSON Schema parameter definitions. The BFCL V4 leaderboard ranks
models on function calling accuracy — top models score 70%+ but still
struggle with memory across long conversations and knowing when NOT
to use a tool. MCP (Model Context Protocol) adoption surged from
100K downloads at November 2024 launch to 97 million monthly downloads
by December 2025. The critical engineering challenge is not calling
tools — it is managing errors, retries, token budgets, and security
at production scale.

## API comparison

```python
# OpenAI — Responses API
tools = [{
    "type": "function",
    "name": "get_order_status",
    "description": "Look up order status by ID.",
    "parameters": {
        "type": "object",
        "properties": {
            "order_id": {"type": "string"}
        },
        "required": ["order_id"],
        "additionalProperties": False
    }
}]

response = client.responses.create(
    model="gpt-4o-mini",
    input="Status of order A-94821?",
    tools=tools,
    tool_choice="auto"
)
```

```python
# Anthropic — Messages API
tools = [{
    "name": "get_order_status",
    "description": "Look up order status by ID.",
    "input_schema": {
        "type": "object",
        "properties": {
            "order_id": {"type": "string"}
        },
        "required": ["order_id"]
    }
}]

response = client.messages.create(
    model="claude-sonnet-4-5",
    max_tokens=1024,
    tools=tools,
    messages=[{"role": "user", "content": "Status of order A-94821?"}]
)
```

```
Key differences across providers:

                 OpenAI              Anthropic           Google
─────────────────────────────────────────────────────────────────
Definition:      type: function      name + input_schema  type: function
Call output:     function_call       tool_use block       function_call
Correlation:     call_id             tool_use_id          call_id
Result return:   function_call_output  tool_result msg    function_result
Strict mode:     strict: true        additionalProperties  response_schema
```

## Schema design best practices

```
Naming:
  ✓ crm_get_customer_profile      (action-based, namespaced)
  ✗ get_data                      (ambiguous)
  ✗ customerProfileFetcherV2      (too verbose)

Descriptions:
  ✓ "Retrieves profile when customer ID is known;
     excludes billing and support tickets"
  ✗ "Gets customer data"

Parameters:
  → Always set additionalProperties: false
  → Use enums for controlled values
  → Include format specs (ISO 8601 dates, units)
  → Mark required fields explicitly

Token cost per tool: 100-300 input tokens
  15 tools ≈ 1,500-4,500 tokens per request
  Dynamic tool loading reduced consumption 34-64%
```

## Error handling taxonomy

```
Error categories for tool results:

retryable-transient:
  429, 500-504, timeouts
  → Exponential backoff: min(base * 2^attempt + jitter, max)
  → Respect Retry-After headers on 429s
  → Max 5-7 attempts

retryable-modified:
  Logic errors fixable with adjusted parameters
  → Return correction hints, not stack traces
  → Max 2 attempts with modified input

terminal-permanent:
  400, 401, 403 — fail fast
  → Return structured error to the model

terminal-budget:
  Token/cost budget exhausted
  → Return best partial result
```

```json
// Structured error response — gives the model enough to self-correct
{
  "status": "error",
  "error_code": "INVALID_DATE_FORMAT",
  "message": "Requires ISO-8601 format (YYYY-MM-DD)",
  "correction_hint": "Please use format like '2024-12-15'",
  "field": "delivery_date"
}
```

## Retry storm prevention

```
Critical numbers:
  Uncontrolled retries: up to 200x token cost vs single success
  A flaky API can escalate $0.01 task to $2 in under a minute
  Healthy retry ratio: below 0.1 (1 retry per 10 calls)
  Alert threshold: sustained ratio exceeding 0.3
  Waste tokens should be <5% of total spend

4-layer defense:

  Layer            Scope              Budget
  ─────────────────────────────────────────────────────
  Tool-level       Per individual     3 attempts, 1s/2s/4s backoff
  Agent-level      Across tools       5 failures = escalate to human
  Orchestration    System-wide        Concurrency limits per service
  Circuit breaker  Provider           Open at >10% error rate / 60s

Fallback chain:
  1. Primary provider (highest quality)
  2. Second provider (separate infrastructure)
  3. Third provider (different rate limit pool)
  4. On-premises model or human escalation
  → Switch providers, not just models — shared pools = correlated failures
```

## Token budget management

```
Four dimensions to enforce:

  Dimension        Purpose                    Typical ceiling
  ────────────────────────────────────────────────────────────
  Token budget     Per-workflow consumption    Split input/output
  Cycle budget     Max reasoning steps         25-30 steps
  Wall-clock       Elapsed time limit          Task-dependent
  Cost budget      Per-request USD ceiling     Provider-dependent

When any budget exhausts → return best partial result
Observability-driven optimization reduces waste ~40%
```

## Structured output vs tool use

```
Structured output:
  → Constrains entire response to JSON Schema
  → OpenAI strict: true guarantees 100% conformance
  → Best for: extraction, typed planners, eval datasets
  → No free-form text outside the schema

Tool use:
  → Model decides when/which function to call
  → Mix of free-form text and function calls
  → Best for: interactive agents, multi-step workflows
  → More flexible but requires argument validation

Choose structured output when you need every response typed.
Choose tool use when the model needs decision-making flexibility.
```

## Anti-patterns

- **Registering all tools in every request** — 80+ tool definitions
  consume 12,000+ tokens before the model sees the prompt. Use
  dynamic tool loading to include only relevant tools per request.
- **Raw error responses** — returning stack traces
  (`NullPointerException at line 142`) instead of structured
  correction hints. Models cannot parse traces for self-correction.
- **Stateful tool sequences** — `set_active_project()` followed by
  `archive_current_project()`. Make every tool call include all
  required context explicitly. Keep operations idempotent.
- **Data firehose returns** — a 2MB JSON response equals 500K-700K
  tokens, exceeding most context windows. Use pagination, filters,
  and enforce max output sizes (~2000 tokens per call).

## Gotchas

- **Parallel tool calls** — models may emit multiple tool calls in
  one turn. A February 2026 study showed 4x speedup for parallel
  execution vs sequential. Use `disable_parallel_tool_use` in
  Anthropic's API when order matters.
- **Tool definition token cost is per-request** — every API call
  pays the full cost of all registered tool schemas. This compounds
  in multi-turn conversations.
- **Models still struggle with "when NOT to call"** — top models
  sometimes force a tool call when the answer is in context. Include
  clear instructions about when tools are unnecessary.
- **MCP security** — 82% of tested MCP servers were vulnerable to
  path traversal in a 2025 audit. Scope filesystem permissions and
  validate all tool inputs server-side.
- **Hallucinated tool arguments** — validation gates catch
  approximately 70% of hallucinated outputs pre-execution. Always
  validate arguments before calling the underlying function.

## Verification

- Tool definitions use namespaced, action-based naming conventions.
- Each tool description includes purpose AND scope limitations.
- Error responses include structured correction hints, not stack traces.
- Retry budgets enforced at tool, agent, and orchestration layers.
- Token budget tracked per-workflow with partial result fallback.
- Dynamic tool loading limits schemas to relevant tools per request.

## Related

- `documentation/docs/policies/ai-ml/rag-chunking-strategies-embedding-models.md`
- `documentation/docs/policies/security/content-security-policy-csp-modern-deployment.md`
- `documentation/docs/policies/architecture/event-sourcing-projections-snapshots.md`

## Source URLs (verified 2026-08-16)

- LLM Function Calling in 2026 — https://futureagi.com/blog/llm-function-calling-2025/
- Function Calling: OpenAI vs Anthropic vs Google — https://qveris.ai/guides/function-calling/
- Tool Use and Function Calling Standards and Benchmarks — https://zylos.ai/research/2026-04-07-tool-use-function-calling-standards-benchmarks/
- The Retry Storm Problem in Agentic Systems — https://tianpan.co/blog/2026-04-10-retry-storm-problem-agentic-systems
