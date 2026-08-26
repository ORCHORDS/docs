# llm-structured-output-vs-function-calling

> In 2026, getting reliable structured data out of LLMs is the single most common
> production task. There are two API mechanisms — **structured outputs** (response
> format / JSON schema enforcement) and **function calling** (tool-use) — and teams
> routinely pick the wrong one or assume either guarantees correctness. The core
> lesson: **schema compliance is not semantic reliability.** This article covers
> when to use each, how to design schemas that actually work, and the validation
> layer you still need on top.

## Symptom

You ask an LLM for JSON and hit one of:

- The model returns valid JSON matching your schema, but the values are
  confidently wrong, hallucinated, or semantically off.
- Schema enforcement (strict mode / constrained decoding) silently degrades
  answer quality — the model forces a value into a required field it cannot
  actually fill.
- Function calling returns tool calls with missing or malformed arguments, even
  though you "gave it a schema."
- Nested optionals and long enums cause the model to loop, emit empty strings, or
  refuse to answer.
- You used function calling for a task that was purely formatting, paying extra
  latency and schema-parse failures for no benefit.

Root cause: conflating two different mechanisms, and assuming that because the
JSON is well-formed the content is correct.

## The two mechanisms

### Structured outputs (response format / JSON mode)

You constrain the *entire response* to conform to a JSON schema. The model's
output is the data object. Best when the task is **formatting / extraction** —
the model's job is to produce structured data, not to take an action.

```python
from pydantic import BaseModel

class CustomerInfo(BaseModel):
    name: str
    email: str
    signup_source: str

result = client.beta.chat.completions.parse(
    model="gpt-4o",
    response_format=CustomerInfo,   # schema enforced
    messages=[{"role": "user", "content": raw_email}],
)
info: CustomerInfo = result.choices[0].message.parsed  # typed object
```

### Function calling (tool use)

You declare callable tools with parameter schemas. The model decides *whether*
and *which* tool to call, and fills in the arguments. Your code executes the
tool. Best when the task is an **action** — there is a side effect or a live data
lookup the model cannot do alone.

```python
tools = [{
    "type": "function",
    "function": {
        "name": "get_order_status",
        "description": "Look up the status of a customer order by ID.",
        "parameters": {
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
        },
    },
}]
resp = client.chat.completions.create(model="...", messages=..., tools=tools)
for call in resp.choices[0].message.tool_calls or []:
    args = json.loads(call.function.arguments)  # still must validate!
    result = dispatch(call.function.name, args)
```

## Decision rule

- **Pure formatting / extraction / classification** with no side effects and no
  external data needed -> **structured output**. Higher reliability, lower
  latency, zero schema-parse errors in strict mode.
- **Needs an action or live lookup** (query a DB, send an email, call an API) ->
  **function calling**.
- **Open-source / weaker model that lacks strict mode** -> a two-stage pattern:
  structured output to extract intent, then your code maps it to an action. More
  reliable than forcing function calling on a model that supports it poorly.

## Schema design (this is where most failures live)

Empirically, simpler schemas perform dramatically better. Rules:

1. **Flat over nested.** Prefer `{street, city, country}` over
   `{address: {street, city, country}}`. Each nesting level increases failure
   rate.
2. **Few required fields.** Every `required` field forces the model to produce a
   value even when it doesn't know one -> hallucination or empty string. Make
   only the truly essential fields required; mark the rest optional.
3. **Short enums.** A 40-value enum breaks constrained decoding and causes loops.
   If you need many categories, use a free-text field plus a downstream
   classifier instead.
4. **Avoid optional-of-optional and unions where possible.** `oneOf`/`anyOf`
   with overlapping shapes confuse the sampler.
5. **Add `description` and an example** to each field. This is context the model
   uses to fill it correctly, not just documentation.

```python
# Good: flat, few required, short enum, described
class OrderExtraction(BaseModel):
    """Extract order details from an unstructured email."""
    order_id: str = Field(..., description="e.g. 'ORD-12345'")
    customer_email: str | None = Field(None, description="Leave null if not present")
    intent: Literal["refund", "status", "cancel"] = Field(
        "status", description="The customer's primary intent"
    )
```

## The validation layer you still need

Schema enforcement guarantees shape, not truth. Always validate semantics:

```python
def parse_and_validate(raw_email: str) -> OrderExtraction:
    info = client.beta.chat.completions.parse(
        model="...", response_format=OrderExtraction, messages=[...]
    ).choices[0].message.parsed
    # Semantic checks schema enforcement cannot do:
    if info.order_id and not ORDER_RE.match(info.order_id):
        raise LLMOutputError(f"bad order_id: {info.order_id}")
    if info.customer_email and "@" not in info.customer_email:
        info.customer_email = None  # model hallucinated a non-email
    if info.intent not in {"refund", "status", "cancel"}:
        info.intent = "status"  # fallback
    return info
```

Retries with the error fed back to the model work better than blind re-rolls:

```python
for attempt in range(3):
    try:
        return parse_and_validate(raw_email)
    except LLMOutputError as e:
        messages.append({"role": "assistant", "content": last_output})
        messages.append({"role": "user",
                         "content": f"That failed validation: {e}. Fix and retry."})
```

## Gotchas

- **Schema compliance != semantic reliability.** This is the #1 trap. Valid JSON
  with the right types can still be confidently wrong. Always add semantic
  validation and do not treat "parsed successfully" as "correct."
- **Strict mode can lower answer quality.** When the model does not know a
  required field, constrained decoding forces it to emit something — often an
  empty string or a guess — instead of being able to say "unknown." Prefer
  optional fields + a downstream null-check.
- **Long enums break constrained decoding.** Beyond ~10-15 enum values the
  sampler struggles; you'll see timeouts, empty values, or repeated tokens. Use a
  shorter enum or a free-text field.
- **Function-calling argument schema is still just a hint on some models.**
  OpenAI strict mode enforces it; many open-source "function calling" models do
  not strictly enforce argument schemas. Validate `tool_calls[].function.arguments`
  yourself before dispatching.
- **Don't use function calling to "make it return JSON."** A common misuse is
  declaring a single `respond(data: object)` tool just to force structured
  output. This adds latency, a round-trip, and a parse step for no benefit over
  native response_format.
- **Empty-string vs null conflation.** Models often emit `""` for a missing
  string field instead of `null`. Decide your convention and normalize in
  validation; downstream code that does `if value:` treats both the same, which
  may hide a hallucination.
- **Token cost of large schemas.** Every field, enum value, and description is
  tokens on every call. A 60-field monster schema can cost more in input tokens
  than the rest of the prompt. Split into per-task schemas.
- **Streaming + structured output is fragile.** Partial JSON mid-stream is not
  parseable. Either buffer until completion or use the provider's structured-
  streaming deltas explicitly.
- **Schema changes invalidate cached prompts.** If you cache prompts and then
  change the response schema, the cache key must include a schema version or you
  serve stale-validated outputs.
