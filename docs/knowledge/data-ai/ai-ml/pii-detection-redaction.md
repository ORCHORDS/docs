# pii-detection-redaction

**Issue:** User inputs and LLM outputs may contain PII that must not be stored, logged, or transmitted
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Users paste email addresses, credit card numbers, or SSNs into chat interfaces. LLMs sometimes reproduce PII from their context window in outputs. Storing or logging this violates GDPR, CCPA, and HIPAA.

## Pattern / Solution
Use a PII detection library (Microsoft Presidio, spaCy with NER, AWS Comprehend) to scan inputs before sending to LLM and scan outputs before storing. Replace detected entities with typed placeholders (`[EMAIL_ADDRESS]`, `[CREDIT_CARD]`) or consistent pseudonyms for entity tracking.

```python
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine

analyzer = AnalyzerEngine()
anonymizer = AnonymizerEngine()

def redact_pii(text: str) -> str:
    results = analyzer.analyze(text=text, language="en")
    return anonymizer.anonymize(text=text, analyzer_results=results).text
```

## Gotchas
- Presidio has false negatives on informal PII (e.g., "my number is zero-one-two...") — supplement with custom recognizers
- Redacting before sending to LLM can break task context — for tasks that need the actual value, use a vault-and-replace pattern
- Log redaction events separately from content logs; never log the original PII

## Related
- ai-output-filtering
- ai-content-moderation
- ai-safety-guardrails
