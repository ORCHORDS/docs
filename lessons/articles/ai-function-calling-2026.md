# ai-function-calling-2026

**Issue:** A team deploys an LLM agent with function calling. The model emits `"maybe"` for a boolean field. A `quantity: 5` arrives as `quantity: "5"`. The tool executes; downstream breaks. The team blames the model.
**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

LLM function calling is unreliable without explicit schema enforcement. The original OpenAI function calling (June 2023) was "best effort" — the model tried to match the schema but wasn't guaranteed. Production teams hit the reliability gap constantly.

## Root cause

OpenAI's Structured Outputs (`strict: true`, August 2024) and Anthropic's `input_schema` (similar) combine **constrained decoding** with model training to guarantee 100% schema conformance. Without these, the model can emit malformed JSON, wrong types, or hallucinated fields.

The architectural pattern: define strict JSON schemas, generate them from a single source of truth (Zod, Pydantic), pass to the provider for constrained decoding, validate again server-side, log violations, retry on failure with corrective context.

## The three-gate pattern

1. **Provider-side constrained decoding** — `response_format: {type: "json_schema", strict: true}` (OpenAI) or `input_schema` (Anthropic)
2. **Server-side validation** — Zod `safeParse` (Node) or Pydantic (Python) before executing
3. **Database constraints** — CHECK constraints and types in the underlying table as the last line

The provider's constraint reduces malformed output to near zero. Server-side validation catches what slips through (semantics the schema can't). DB constraints catch the rest.

## The single source of truth

```typescript
import { z } from 'zod';

const ExtractSchema = z.object({
  doc_id: z.string().min(1),
  page: z.number().int().min(1),
  bbox: z.array(z.number()).length(4),
  format: z.enum(['csv', 'json'])
});
```

Generate JSON Schema from this and pass to the provider:

```typescript
import { zodToJsonSchema } from 'zod-to-json-schema';
const jsonSchema = zodToJsonSchema(ExtractSchema);

// Pass to OpenAI
const completion = await openai.chat.completions.create({
  model: 'gpt-4o-2024-08-06',
  response_format: {
    type: 'json_schema',
    json_schema: { name: 'extract', strict: true, schema: jsonSchema }
  },
  messages: [...]
});
```

## The retry pattern

```python
def call_with_validation(payload, schema, max_retries=2):
    for attempt in range(max_retries + 1):
        result = tool.execute(payload)
        parsed = schema.safe_parse(result)
        if parsed.success:
            return parsed.data
        # Inject error back as corrective context
        payload = inject_error(payload, parsed.error.message)
    # Fall back to deterministic path
    return deterministic_fallback(payload)
```

Two retries on validation error, then escalate. More retries and the agent is confused — they don't help.

## The five tool architecture patterns

| Pattern | When it fits |
|---|---|
| Sequential chain | Fixed field order, predictable layout |
| Parallel fan-out | Independent extraction tasks, no field dependencies |
| Router/dispatcher | Variable document types on the same pipeline |
| Retry with fallback | High-confidence threshold with escalation |
| Human-in-the-loop | Confidence below threshold, routed to reviewer |

## The five security best practices

1. **Least privilege per tool** — only the permissions for its specific function
2. **Separate read/write** — never bundle unless task requires both
3. **Explicit user confirmation for high-risk actions** — writes, deletions, network sends
4. **Path scoping for filesystem tools** — 82% of tested MCP servers were vulnerable when filesystem permissions were not scoped (2025)
5. **Code execution in sandboxes** — isolated environment for any code-execution tool

## The Tool Search Tool pattern

Loading hundreds of tool definitions into context is expensive and degrades reasoning quality. The Tool Search Tool pattern: give the model a single "search for tools" capability initially; the model queries for relevant tools on demand. In production benchmarks, this achieved 34-64% reduction in total token consumption.

Anthropic's MCP formalized this in December 2025. The protocol defines JSON-RPC communication with four primitives: Tools (callable functions), Resources (data sources), Prompts (reusable templates), Sampling (model invocation through the server).

## The validation metrics

Three independent scores per test case:

| Metric | Question | How to score |
|---|---|---|
| Tool selection accuracy | Did the model pick the right tool (or no tool)? | Exact match on tool name |
| Argument correctness | Given the right tool, are arguments right? | Field-by-field; strict for IDs/enums, normalized for free text |
| Schema adherence | Is the output structurally valid? | Validate against the JSON Schema with `ajv` or `jsonschema` |

Aggregate into per-tool accuracy. Gate in CI so a model or prompt change can't silently break tool use.

Target schema-violation rate < 0.1% with constrained decoding.

## Verification

The tell that function calling is working:

- Schema-violation rate is <0.1%
- Type errors in tool arguments are near zero
- Tool selection accuracy is high on the labeled eval set
- Invalid calls auto-retry and recover
- Database constraints never trigger (proves upstream gates work)

The tell it isn't:

- Tool arguments have type mismatches ("5" vs 5)
- "maybe" appears in a boolean field
- Schema violations are caught only in production
- The agent hallucinates tool names that don't exist

## Gotchas

- **Use `strict: true` or equivalent.** Without it, the model is "best effort."
- **Validate server-side, not just provider-side.** Provider constraints are probabilistic; your validation is deterministic.
- **Two retries max.** More retries mean the agent is confused.
- **Test negative cases.** 20-30% of eval cases should be "no tool called" or "wrong tool exists."
- **Mark which arguments are strict.** IDs and enums need exact match; free text needs fuzzy.
- **Tools are contracts first, code second.** Strong schema beats strong implementation.
- **Database constraints as the last line.** The other two gates can fail; the database is deterministic.

## Related

- `lessons/ai-red-teaming-2026.md` — adversarial testing of tool misuse
- `lessons/prompt-injection-defense-2026.md` — defense in depth around tool calls
- `patterns/agent-eval-2026.md` — eval set for tool accuracy

## Source URLs (verified 2026-08-10)

- https://callsphere.ai/blog/vw5g-tool-call-schema-validation-patterns-2026
- https://www.extend.ai/resources/tool-calling-patterns-document-processing-agents
- https://zylos.ai/research/2026-04-07-tool-use-function-calling-standards-benchmarks/
- https://qaskills.sh/blog/tool-calling-accuracy-testing-guide-2026
- https://skywork.ai/blog/ai-agents-using-tools-ultimate-guide-2026/
