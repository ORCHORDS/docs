# AI and LLM Inference Monitoring

Monitoring an LLM-powered feature is fundamentally different from a
traditional API. A normal endpoint has bounded latency and predictable cost;
an LLM call streams tokens over seconds, bills per input+output token, can
return valid-looking-but-wrong answers (hallucinations), and can be abused via
prompt injection. Tools built for this in 2026 include LangSmith, Arize Phoenix,
Langfuse, Helicone, and the OpenLLMetry/OpenTelemetry GenAI semantic
conventions.

## Symptom

- LLM feature latency p99 is 30s but p50 is 1s — a few outlier generations
  are dragging the experience, and your APM span shows only "1 LLM call" with
  no breakdown.
- Token costs are 3x what you budgeted but you cannot tell which prompt
  template, which user, or which model variant is responsible.
- Users report "the bot gave wrong answers" but you have no record of the
  actual prompt, model, temperature, or retrieved context that produced it.
- A model provider degrades silently (slower, lower quality) and your
  feature's error rate stays at 0% — there's no "error," just bad output.
- Prompt injection or jailbreak attempts are not detectable because you don't
  log the raw user input separately from the system prompt.

## Gotchas

- **Token cost is not a metric most APMs capture natively.** You must emit
  `gen_ai.usage.input_tokens` and `gen_ai.usage.output_tokens` as span
  attributes (per the OTel GenAI semantic conventions) and multiply by your
  provider's per-token price in a dashboard. Without this, cost is invisible
  until the invoice arrives.
- **Stream latency ≠ request latency.** A streaming response can take 8s
  total but feel instant (good time-to-first-token) or feel dead (bad TTFT).
  Track **time-to-first-token (TTFT)** and **tokens-per-second** separately
  from total request duration. TTFT > 2s is what users perceive as "slow."
- **Hallucination is a quality metric, not an error.** Traditional error
  tracking (Sentry, etc.) won't catch it. You need either human eval scores,
  LLM-as-judge scoring on a sample of outputs, or regex/rule-based output
  validation logged as a custom metric.
- **Prompt versioning is mandatory.** Log `prompt_template_id` and
  `prompt_version` as tags on every span. Without it you cannot A/B prompt
  changes or roll back a regression — "we changed the system prompt and
  quality dropped" is untraceable otherwise.
- **Retrieval (RAG) failure modes are invisible without logging the context.**
  Log the retrieved chunk IDs and their similarity scores. A bad answer is
  often a retrieval problem (wrong chunks) not a generation problem.
- **PII in prompts/logs.** User prompts often contain PII. Apply the same
  redaction/masking you use on regular logs *before* shipping to the LLM
  observability tool, or use a tool with built-in PII scrubbing (Langfuse,
  Helicone). Don't ship raw support-chat transcripts to a third party.
- **Rate limits and abuse.** LLM endpoints are expensive attack targets.
  Monitor requests-per-user, tokens-per-user-per-day, and prompt-length
  distributions. A single user sending 10k-token prompts every second will
  drain your budget.
- **Model swaps silently change behavior.** OpenAI deprecating `gpt-4` for
  `gpt-4-turbo` (or equivalent) changes tokenization, latency, and quality.
  Tag every span with the exact model ID and monitor quality by model.

## Example: OpenLLMetry span attributes (OTel GenAI semantic conventions)

```python
from openai import OpenAI
from opentelemetry import trace

client = OpenAI()
tracer = trace.get_tracer("llm-app")

def chat(user_msg: str, prompt_version: str):
    with tracer.start_as_current_span("llm.chat") as span:
        span.set_attribute("gen_ai.system", "openai")
        span.set_attribute("gen_ai.request.model", "gpt-4o")
        span.set_attribute("gen_ai.request.temperature", 0.2)
        span.set_attribute("gen_ai.prompt_template_id", "support-v3")
        span.set_attribute("gen_ai.prompt_template_version", prompt_version)
        # user input (PII-scrubbed before logging)
        span.set_attribute("gen_ai.user_input_hash", hash_scrub(user_msg))

        resp = client.chat.completions.create(
            model="gpt-4o",
            temperature=0.2,
            messages=[{"role": "user", "content": user_msg}],
        )

        span.set_attribute("gen_ai.usage.input_tokens", resp.usage.prompt_tokens)
        span.set_attribute("gen_ai.usage.output_tokens", resp.usage.completion_tokens)
        span.set_attribute("gen_ai.response.finish_reason", resp.choices[0].finish_reason)
        return resp.choices[0].message.content
```

## Key dashboards to build

| Panel                      | What it tells you                          |
|----------------------------|--------------------------------------------|
| Cost per request (by template) | Which prompt is burning budget           |
| TTFT distribution          | Perceived responsiveness                   |
| Tokens/sec                 | Provider throughput health                 |
| Error rate by model        | Which provider is failing                  |
| Output-quality score (judge/eval) | Hallucination trend over time         |
| Requests per user (top 10) | Abuse / cost attribution                   |
| Prompt-length p99          | Prompt-injection / context-stuffing signal |

## Example: Cost alert (Prometheus-style, if you export token metrics)

```promql
# Daily spend = sum(input_tokens * $in_price + output_tokens * $out_price)
sum_over_time(
  gen_ai_usage_input_tokens_total[24h] * 0.000005    # $5/1M input tokens
  + gen_ai_usage_output_tokens_total[24h] * 0.000015  # $15/1M output tokens
) > 500  # alert if daily spend exceeds $500
```

## Verifying it works

- You can attribute 100% of your provider invoice back to specific
  prompt-template × model combinations.
- You can detect a quality regression (via LLM-judge or eval set) within one
  day of a prompt or model change.
- Cost-anomaly alerts fire before the monthly bill surprises you.
- A prompt-injection attempt is detectable from the prompt-length and
  request-rate distributions, not just from output content.
