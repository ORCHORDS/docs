# structured-output-2026

- **Issue**: Parsing JSON out of free-form LLM text is a regex-on-a-time-bomb. The 2026 fix is **constrained decoding**: pass a JSON Schema, the model physically cannot produce invalid output. OpenAI, Anthropic, and Google all ship it. The trade-off: schema complexity vs. cost.
- **Date**: 2026-08-09
- **Repo**: example-org/example-repo
- **Author**: kb-batch-2
- **Status**: Active; complements `documentation/docs/policies/patterns/agent-eval-2026.md` and `documentation/docs/policies/patterns/agent-guardrails-2026.md`.

## Symptom

- The LLM returns text wrapped in ```json ... ``` fences, sometimes with trailing commas, sometimes with comments, sometimes with prose around it. Your parser fails half the time.
- You asked for a JSON object and got JSON, but a field is missing. Or wrong type. Or out of enum.
- The Pydantic validation runs after the model call, catches 5% of failures, you retry, the model gets it right 80% of the time, the other 20% loops until your timeout.
- A schema change breaks extraction quality and you only find out in production.

## Root cause

"Structured output" is a vendor-specific term with a specific meaning. Most teams use it to mean "ask the model to return JSON," which is Level 1. The 2026 production pattern is **Level 3 (native constrained decoding)**, which guarantees 100% schema compliance at the token level.

## The three levels

| Level | Mechanism | Compliance | Cost |
|---|---|---|---|
| **L1: JSON mode** | `response_format={"type":"json_object"}` (OpenAI) or prefill trick (Anthropic) | "Some JSON" — not schema-valid | Lowest |
| **L2: Function calling / tool use** | Define a function schema; model "calls" it | 95–99% schema-valid (a hint, not a constraint) | Standard |
| **L3: Native structured output** | Constrained decoding with JSON Schema; FSM masks invalid tokens | **100%** schema-valid | Standard |

OpenAI and Google both ship L3. Anthropic has L2; their L3 is via tool-use-as-schema (see below).

## The 2026 provider matrix

| Feature | OpenAI | Anthropic | Google Gemini |
|---|---|---|---|
| JSON Mode | `response_format: json_object` | Prefill trick | `response_mime_type: application/json` |
| Strict schema enforcement | **Yes** (`response_format: json_schema` + `strict: true`) | No explicit strict mode; **99%+** via tool-use | **Yes** (`response_schema` in generation config) |
| Function calling | `tools=[...]` + `strict: true` | `tools=[...]` + `tool_choice` | `tools=[...]` |
| Pydantic support | **Native** (SDK method) | Via 3rd-party libs (Instructor) | Via `genai` SDK |
| Guaranteed valid JSON | **100%** | ~99%+ | Yes (with schema) |
| Streaming support | Yes | Yes | Yes |
| Nested object schemas | Yes | Yes | Yes |
| Enum constraints | Yes | Yes | Yes |
| Default values | No (all fields required) | Via schema `default` | Limited |
| Max schema depth | 5 levels | No hard limit | 5 levels |

**OpenAI's structured output lifted JSON Schema compliance from 35.9% to 100%** on their evaluation set. That is the difference between regex-on-text and a constrained finite state machine.

## The Anthropic pattern (tool-use-as-schema)

Anthropic has no native JSON-mode flag equivalent to OpenAI's. Instead, the production pattern is:

1. Define a single tool whose `input_schema` matches your desired output shape.
2. Force the model to call that tool via `tool_choice: {"type": "tool", "name": "extract_meeting"}`.
3. Extract the structured data from the `tool_use` block in the response.

This is reliable (~99%+ schema compliance) but not 100% guaranteed. The recommended supplement: **Pydantic / Zod validation as a safety net**.

## The cross-provider pattern (Instructor + Pydantic)

For workloads that span providers, the **Instructor** library is the production default. It patches the client (OpenAI, Anthropic, Google, Mistral, any OpenAI-compatible endpoint) to:

1. Convert a Pydantic model to JSON Schema.
2. Send the appropriate API format (`response_format: json_schema` for OpenAI, `tool_use` for Anthropic, `response_schema` for Gemini).
3. Parse the response.
4. **Retry with validation error feedback** if parsing fails or business validation fails.

The retry-with-validation loop is the load-bearing piece. It catches the rare cases the schema doesn't.

## Code shape

### OpenAI (native L3)

```py
from pydantic import BaseModel
from openai import OpenAI

class Meeting(BaseModel):
    title: str
    date: str
    attendees: list[str]

client = OpenAI()
resp = client.responses.parse(
    model="gpt-5",
    text_format=Meeting,
    input="Extract the meeting from: 'Lunch with Alice and Bob on Tuesday at noon.'"
)
meeting = resp.output_parsed  # type: Meeting
```

### Anthropic (tool-use-as-schema + Pydantic validation)

```py
import instructor
from pydantic import BaseModel
from anthropic import Anthropic

class Meeting(BaseModel):
    title: str
    date: str
    attendees: list[str]

client = instructor.from_anthropic(Anthropic())
meeting = client.messages.create(
    model="claude-sonnet-5-2026...",
    tools=[{
        "name": "extract_meeting",
        "description": "Extract meeting details",
        "input_schema": Meeting.model_json_schema(),
    }],
    tool_choice={"type": "tool", "name": "extract_meeting"},
    messages=[{"role": "user", "content": "Extract: 'Lunch with Alice and Bob on Tuesday at noon.'"}],
)
# Instructor returns the validated Pydantic object directly.
```

### Gemini (native L3)

```py
from pydantic import BaseModel
from google import genai

class Meeting(BaseModel):
    title: str
    date: str
    attendees: list[str]

client = genai.Client()
resp = client.models.generate_content(
    model="gemini-2.5-pro",
    contents="Extract the meeting from: 'Lunch with Alice and Bob on Tuesday at noon.'",
    response_schema=Meeting,
    response_mime_type="application/json",
)
meeting = resp.parsed  # type: Meeting
```

## The five principles

1. **Use constrained decoding when available.** OpenAI's `json_schema` mode with `strict: True` is the gold standard. No retries needed for schema validity.
2. **Use Instructor for cross-provider workflows.** It abstracts the differences and adds Pydantic validation with auto-retry.
3. **Anthropic = tool-use-as-schema.** Define a tool, force it with `tool_choice`, validate with Pydantic.
4. **Schema enforcement does not replace business validation.** JSON Schema catches structural errors. Pydantic validators catch semantic errors (e.g., "the date is in the past", "the email is malformed"). You need both layers.
5. **Monitor first-attempt success rate.** A drop is the leading indicator that your prompt, schema, or model version has changed in a way that breaks extraction.

## Validation

- **First-attempt success rate** (schema + business validation) on a held-out golden set. Target ≥ 99%.
- **Retry rate** — if it climbs, your schema or prompt has changed in a way the model can't satisfy.
- **Validation error rate by field** — which field fails most often? That field needs a better prompt or a less-strict schema.
- **Schema change diff** in code review — every schema change must come with a re-run of the golden set.
- **Cost per extraction** — a complex schema can blow up token cost. Watch it.

## Gotchas

- **OpenAI's `strict: true` requires `additionalProperties: false` on every object.** Otherwise the strict mode rejects the schema.
- **All fields must be in `required`** for OpenAI strict mode. There are no default values.
- **Anthropic's tool-use-as-schema is ~99%, not 100%.** Always validate server-side with Pydantic / Zod.
- **OpenAI max schema depth is 5 levels.** Flatten deeper structures.
- **Gemini max schema depth is 5 levels.** Same flattening.
- **Instructor's retry loop is the safety net**, not the primary mechanism. Track retry rate; if it's high, your schema is the problem.
- **`gpt-4o-mini` is the minimum for OpenAI structured outputs.** Older models don't support it.
- **Watch token cost.** A complex schema with many `description` fields can double the input token count. Co-locate schemas in the prompt cache.
- **Schema versioning is your responsibility.** Bump the schema version deliberately; re-run the golden set; treat a schema change as a migration, not a config change.
- **Don't roll your own JSON parser.** Use `json.loads` with `strict=False` only as a last resort; even then, validate with a schema.
- **The Pydantic V2 `model_json_schema()` output is not directly compatible** with OpenAI's `json_schema` mode. You may need a transformer (extra fields, `additionalProperties: false`, `required` populated, etc.). Use `instructor` or a tested helper to bridge.

## Related

- `documentation/docs/policies/patterns/agent-eval-2026.md` — measuring schema compliance over time
- `documentation/docs/policies/patterns/agent-guardrails-2026.md` — Layer 4 (output filtering) includes schema validation
- `documentation/docs/policies/patterns/prompt-caching-2026.md` — co-locating schemas in the cache
- `documentation/docs/policies/patterns/agent-context-engineering-2026.md` — the broader context budget
- `documentation/docs/policies/cloudflare/ai-search-2026.md` — `ai-search` returns structured output by default

## Source URLs (verified 2026-08-09)

- "Structured Outputs実装完全ガイド2026" (AIgent Lab) — https://aigentlab.tech/articles/structured-outputs-tool-use-json-schema-guide-2026/
- "Structured Outputs from LLMs — JSON, Pydantic & Schema" (myengineeringpath) — https://myengineeringpath.dev/genai-engineer/structured-outputs/
- "LLM Structured Output in 2026" (dev.to) — https://dev.to/pockit_tools/llm-structured-output-in-2026-stop-parsing-json-with-regex-and-do-it-right-34pk
- "AI Structured JSON Output: Model Support & Code" (devtk) — https://devtk.ai/en/blog/ai-structured-output-guide-2026/
- "Tutorial: Generating Structured Output with OpenAI" (Haystack) — https://haystack.deepset.ai/tutorials/28_structured_output_with_openai
- OpenAI Structured Outputs announcement — https://openai.com/index/introducing-structured-outputs-in-the-api/
- Anthropic tool use overview — https://docs.anthropic.com/en/docs/build-with-claude/tool-use
- Instructor library — https://github.com/jxnl/instructor
