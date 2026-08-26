# ai-agent-token-economics-finops

> AI agents burn 3-10x more tokens than equivalent chatbots because every
> reasoning step, tool call, and retrieved document is context that gets
> re-processed — often repeatedly. The gap between an unoptimized and an
> optimized deployment can reach ~200x in cost. This article is the FinOps
> playbook for taming agent token spend without sacrificing quality: the five
> savings levers, where the big money is, and the budgeting pattern that
> prevents runaway bills.

## Symptom

You deployed an agent and the cloud LLM bill is climbing faster than usage:

- A single agent task that should cost $0.02 is costing $0.40, and you cannot
  explain where the tokens went.
- The same system prompt and the same retrieved docs are re-sent on every turn,
  re-billed at full input-token price.
- Every request goes to the flagship model, even the trivial "summarize one
  sentence" steps.
- One buggy agent looped 12 times overnight and racked up a four-figure bill
  before anyone noticed.
- Finance is asking for per-team, per-feature cost attribution and you have
  nothing.

Root cause: agents multiply token usage at every layer (planning + retrieval +
tool outputs + reflection), and naive deployments treat each call as an
independent chat completion instead of engineering the whole pipeline for cost.

## Why agents cost more

A chatbot: 1 call, prompt + reply.
An agent: 1 planning call + N tool calls (each returns tokens that become input
to the next call) + a synthesis call, all re-sending the system prompt and
growing context each step. A 6-step agent easily processes 30-50k tokens for a
task whose chatbot equivalent is 800.

## The five savings levers (with measured impact)

| Lever | Typical savings | When it applies |
|---|---|---|
| Prompt caching | up to ~90% on cache hits | Repeated prefix (system prompt, fixed docs) |
| Model routing | ~40-70% | Mixed task difficulty |
| Context compaction | ~50-70% token reduction | Long conversations, large retrievals |
| Prompt optimization | variable | Overly verbose prompts/instructions |
| Batch processing | up to ~50% | Non-real-time, offline jobs |

Apply in roughly that priority order — caching and routing are the biggest, most
reliable wins.

## Lever 1: Prompt caching

Anthropic and OpenAI both offer prompt caching: if the *prefix* of your request
is byte-identical to a recent one, the cached prefix is billed at a steep
discount (often ~10% of normal input price).

```python
# Anthropic example: cache the system prompt + fixed tool defs
response = client.messages.create(
    model="claude-...",
    system=[
        {
            "type": "text",
            "text": SYSTEM_PROMPT,                 # large, stable
            "cache_control": {"type": "ephemeral"} # mark as cacheable
        }
    ],
    messages=[{"role": "user", "content": user_msg}],  # dynamic, last
)
```

Rules for cache effectiveness:
- Keep the prefix **byte-stable**. Any change (a timestamp, a request ID, a
  randomized greeting) invalidates the cache. Put all dynamic content at the end.
- The cacheable prefix must be large enough to be worth it (typically >1k tokens;
  provider minimums vary).
- Caches are per-organization and short-lived (minutes). High-volume, repeated
  prefixes benefit most.

## Lever 2: Model routing

Not every step needs the flagship. Route by difficulty.

```python
def pick_model(step: str, complexity: float) -> str:
    # complexity from a cheap classifier or heuristic (0..1)
    if step == "final_answer" or complexity > 0.7:
        return "claude-opus"     # expensive, high quality
    if step == "classify" or complexity < 0.3:
        return "haiku"           # cheap, fast
    return "sonnet"              # middle

# Or a router that decides per-query
model = router.classify(user_msg)  # returns cheap | mid | flagship
```

Empirically, routing only the genuinely hard ~20% of steps to the flagship and
the rest to a cheap model yields 40-70% savings with negligible quality loss.
Measure quality on a golden set before and after — routing that drops quality is
a false economy.

## Lever 3: Context compaction

Don't re-send the full conversation every turn. Compress old turns into a running
summary and drop low-relevance retrieved chunks before they enter the window.
(See `context-engineering-systems.md` and `rag-context-compression.md` for the
patterns.) This cuts both cost and latency.

```python
def compact_if_large(history: list[Message], max_tokens: int = 2000) -> list[Message]:
    if count_tokens(history) <= max_tokens:
        return history
    old, recent = history[:-4], history[-4:]          # keep last 4 turns raw
    summary = summarizer.summarize(old)               # one cheap call
    return [Message(role="system", content=f"Prior summary:\n{summary}")] + recent
```

## Lever 4: Per-task token budgets

The single most effective guard against runaway spend: every agent task gets a
hard token (and dollar) budget. When exceeded, the agent stops, not the credit
card.

```python
class TokenBudget:
    def __init__(self, max_input_tokens: int, max_cost_usd: float):
        self.max_input = max_input_tokens
        self.spent_input = 0
        self.spent_usd = 0.0
        self.max_cost = max_cost_usd

    def charge(self, input_tokens: int, cost_usd: float):
        self.spent_input += input_tokens
        self.spent_usd += cost_usd
        if self.spent_input > self.max_input or self.spent_usd > self.max_cost:
            raise BudgetExceeded(self.spent_usd, self.max_cost)

def run_agent(task, budget: TokenBudget):
    for step in plan(task):
        resp = llm.complete(step.prompt)
        budget.charge(resp.usage.input_tokens, resp.usage.cost_usd)
        if step.is_loop and step.iterations > MAX_ITERS:
            raise AgentLoopDetected(step.iterations)
```

Pair this with a **max-iterations** cap so a stuck agent fails fast instead of
looping indefinitely. Both the budget and the iteration cap are non-negotiable
for production.

## Lever 5: Batch + cost attribution

- **Batch APIs** for offline workloads (evals, bulk classification, backfills)
  give ~50% discounts in exchange for hours of latency. Never call the
  real-time endpoint for a job that doesn't need real-time.
- **Tag every call** with team, feature, user, and environment so finance can
  attribute spend. Without tags you cannot tell which feature is 80% of the bill.

```python
resp = client.chat.completions.create(
    model="...",
    messages=...,
    extra_headers={
        "X-Team": "support-bot",
        "X-Feature": "ticket-triage",
        "X-Env": "prod",
    },
)
```

## Gotchas

- **Caching breaks if you put ANY dynamic token in the prefix.** The most common
  cache-bust is a hidden timestamp, request ID, or "today is {date}" in the
  system prompt. Audit your prefix for anything that changes per request.
- **Routing to a weaker model can silently regress quality.** Always re-run your
  eval suite (see `llm-as-judge-trace-evaluation.md`) after changing the routing
  policy. A 50% cost cut that drops task-success from 92% to 78% is a loss.
- **Tool outputs are the hidden token sink.** A `search` tool returning 10 full
  documents can be 15k tokens, all re-processed on the next step. Truncate tool
  outputs aggressively and summarize before re-injecting.
- **Reflection loops multiply cost.** "Have the agent critique and revise its own
  answer" can double or triple token usage per task. Cap reflection iterations and
  measure whether each round actually improves quality on your eval set — often
  round 2 adds nothing.
- **Budgets must be enforced server-side, not in the prompt.** Asking the model
  "please be efficient" does not control spend. The `TokenBudget` must wrap the
  call site.
- **Cost dashboards lag the bill.** By the time you see the spike in the
  provider console, the money is spent. Set real-time alerts on dollars-per-hour
  per feature, with an auto-kill switch.
- **Free-tier / local models shift cost to compute.** Routing to a local Ollama
  model saves API spend but adds GPU/electricity/ops cost. Track total cost of
  ownership, not just the API line item.
- **Compaction is lossy and can break later turns.** If a user references a
  detail from 10 turns ago that you summarized away, the agent cannot answer.
  Keep raw history in cold storage keyed by ID so you can re-expand on demand.
- **Don't optimize before you measure.** Install per-call token + cost logging
  first. Most teams find 80% of spend comes from 20% of calls (usually a single
  heavy feature or a looping agent). Optimize that, not everything.
