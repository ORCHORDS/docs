# llm-temperature-sampling-decoding

**Issue:** Choosing the wrong decoding parameters (temperature, top-p, top-k,
frequency/presence penalties) produces output that is either too random and
hallucinatory or too rigid and repetitive.
**Date:** 2026-08-13
**Status:** documented

## Symptom

The model behaves inconsistently or wrong-for-the-task across runs, with no
prompt change to blame. Common signals:
- **Deterministic tasks (JSON, extraction, classification) are flaky.** The
  same input sometimes produces valid JSON and sometimes adds prose wrappers,
  extra keys, or invents values not present in the source.
- **Creative tasks are flat.** Summaries, marketing copy, and brainstorming
  all sound identical across runs, reusing the same phrases and structures.
- **Repetition loops.** The model gets stuck repeating a phrase ("the the the
  the") or paraphrasing the same point in a loop until max tokens is hit.
- **Format drift under load.** When traffic spikes, output format breaks more
  often — because some providers rotate sampling defaults or the fallback
  model uses different defaults than the primary.
- **Tests pass locally, fail in CI.** Golden-file or snapshot tests flake
  because temperature is not pinned or the provider changed its default.

The root cause is that sampling parameters are treated as an afterthought or
left at provider defaults, rather than chosen deliberately per task.

## Pattern / Solution

### Per-task parameter matrix

| Task type | Temperature | top_p | Notes |
|---|---|---|---|
| Code generation | 0.0 - 0.2 | 1.0 | Deterministic; code must compile |
| JSON / structured output | 0.0 - 0.1 | 1.0 | Minimize format drift |
| Classification / extraction | 0.0 | 1.0 | One right answer |
| Summarization | 0.3 - 0.5 | 0.9 | Faithful but not rigid |
| General chat / QA | 0.3 - 0.7 | 0.9 | Balance accuracy and natural tone |
| Brainstorming / ideation | 0.8 - 1.0 | 0.95 | Maximize diversity |
| Creative writing | 0.9 - 1.2 | 0.95 | Some providers cap at 1.0 |

### Setting them explicitly

```python
response = client.chat.completions.create(
    model="gpt-4o",
    messages=messages,
    temperature=0.0,       # deterministic extraction
    top_p=1.0,             # no nucleus truncation
    max_tokens=500,
    frequency_penalty=0.0, # off for extraction
    presence_penalty=0.0,
    seed=42,               # pin for reproducible evals (if supported)
)
```

### Why temperature alone is not enough

Temperature scales the logits before softmax. At high temperatures, the long
tail of low-probability tokens can still dominate and produce gibberish. The
fix is to combine temperature with top-p (nucleus) or top-k truncation.

```python
# Low temperature + no truncation: mostly deterministic, but a bad token
# can still sneak in if logits are flat.
temp=0.1, top_p=1.0

# High temperature + nucleus truncation: creative but stays in plausible space
temp=0.9, top_p=0.92
```

### Fixing repetition loops

If the model loops on a phrase, add frequency and presence penalties.

```python
frequency_penalty=0.5,   # penalize tokens that already appeared
presence_penalty=0.3,    # penalize tokens on whether they appeared at all
```

Frequency penalty scales with how many times a token appeared; presence
penalty is binary. Start with 0.3-0.5 for each and increase until the loop
breaks. Too high and the output becomes erratic.

### Reproducible evals and tests

```python
# Pin temperature=0 and a seed for golden-file tests
@pytest.mark.parametrize("case", eval_cases)
def test_extraction_format(case):
    result = llm.generate(case.input, temperature=0.0, seed=12345)
    assert extract_json(result)["category"] == case.expected_category
```

### Provider default pitfalls

Different providers ship different defaults. Anthropic Claude defaults to
temperature=1.0; OpenAI to 1.0; some local runtimes to 0.8. When you switch
providers or use a fallback, re-pin every parameter explicitly.

```python
# Do NOT rely on provider defaults — pin everything
params = {
    "temperature": 0.0,
    "top_p": 1.0,
    "max_tokens": 1000,
}
response_primary = openai.chat(messages, **params)
response_fallback = anthropic.messages(messages, **params)
```

## Gotchas

- **temperature=0 is not fully deterministic on all providers.** OpenAI
  approximates it; some backends still sample. Use a `seed` if available, and
  accept ~1% variance even then.
- **Seeds are per-request, not global.** A seed of 42 gives different output
  with different prompts, models, or token counts. It is a reproducibility
  aid, not a hash.
- **Do not set temperature above 1.0 blindly.** Values above 1 amplify the
  long tail and can produce unicode garbage or tokenization artifacts. Some
  providers silently clamp; others do not.
- **top_p and temperature interact non-linearly.** Lowering top_p with a high
  temperature does not equal a low temperature. Test both axes independently.
- **Penalties can break structured output.** frequency_penalty > 0 on JSON
  generation can suppress repeated structural tokens (braces, quotes) and
  produce invalid JSON. Keep penalties at 0 for extraction and code.
- **Logging without parameters is useless.** Always log temperature, top_p,
  penalties, and seed alongside the response. A failure that cannot be
  reproduced cannot be debugged.
- **Fallback models need their own tuned parameters.** A small fallback model
  often needs lower temperature than the primary because it is less robust to
  sampling noise. Do not assume the same params work across model sizes.
- **Context length changes effective temperature.** As the prompt fills up,
  attention dilutes and outputs get noisier. Consider lowering temperature
  slightly for long-context calls.

## Related
- `llm-structured-output.md` — rely on grammar constraints, not low temperature alone
- `llm-json-mode.md` — format enforcement is more reliable than sampling tricks
- `prompt-testing-evals.md` — pin parameters before measuring prompt changes
- `llm-output-validation.md` — validate post-hoc even with temperature=0
- `llm-fallback-provider-rotation.md` — re-pin params on every provider
