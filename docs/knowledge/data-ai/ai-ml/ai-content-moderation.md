# ai-content-moderation

**Issue:** User-generated inputs and LLM outputs contain harmful, illegal, or policy-violating content
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A product accepts user prompts and returns LLM-generated responses. Without moderation, users submit hate speech, CSAM-adjacent requests, or PII; LLMs hallucinate dangerous instructions or reproduce copyrighted text.

## Pattern / Solution
Apply moderation at two points: input (before sending to LLM) and output (before serving to user). Use provider moderation APIs (OpenAI Moderation, Perspective API) for speed. Add domain-specific classifiers for your content policy. Log all flagged content with context for human review.

```python
from openai import OpenAI

def check_content(text: str) -> bool:
    result = OpenAI().moderations.create(input=text)
    return not result.results[0].flagged
```

## Gotchas
- Moderation APIs have their own latency (50-200 ms) — run them concurrently with LLM warmup, not sequentially
- Category thresholds differ by jurisdiction and audience (e.g., violence acceptable in news context)
- Adversarial users encode harmful content in base64, l33tspeak, or non-English — multi-lingual moderation is required

## Related
- ai-safety-guardrails
- prompt-injection-defense
- ai-output-filtering
- pii-detection-redaction
