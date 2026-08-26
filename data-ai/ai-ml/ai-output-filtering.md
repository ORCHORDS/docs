# ai-output-filtering

**Issue:** LLM outputs need post-processing to remove sensitive, off-policy, or low-quality content before delivery
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
LLM responses contain hallucinated phone numbers, competitor mentions, legal disclaimers that should be stripped, or phrases that violate brand tone guidelines. You need a deterministic layer to clean outputs regardless of model behavior.

## Pattern / Solution
Build a filter pipeline that runs after the LLM call: (1) regex/NER for PII scrubbing, (2) keyword blocklist for competitor/legal terms, (3) quality score threshold (length, coherence), (4) policy classifier. Return a fallback response if the output fails multiple filters.

```python
def filter_output(text: str) -> str:
    text = strip_pii(text)
    text = remove_blocked_terms(text, BLOCKLIST)
    if quality_score(text) < 0.5:
        return FALLBACK_RESPONSE
    return text
```

## Gotchas
- Filtering too aggressively truncates legitimate content — log filter hits to tune thresholds
- Regex-based PII filters have false positives on structured data like product codes resembling SSNs
- Filtering order matters: strip PII before logging, not after

## Related
- ai-content-moderation
- pii-detection-redaction
- ai-safety-guardrails
