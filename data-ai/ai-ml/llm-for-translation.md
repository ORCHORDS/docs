# llm-for-translation

**Issue:** LLM translations lose domain-specific terminology, tone, and cultural nuance compared to specialized MT systems
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A medical platform uses an LLM to translate patient instructions. The LLM translates medical terms incorrectly or uses informal register where formal language is required by the target culture.

## Pattern / Solution
Provide a terminology glossary in the system prompt (source to target term pairs). Specify register (formal/informal) and dialect. For critical content, use a two-pass approach: translate, then back-translate and compare to the original. Use domain-specific few-shot examples with verified translations.

```
You are a medical translator (English to German, formal register).
Glossary: {"hypertension": "Hypertonie", "dosage": "Dosierung"}
Translate preserving all medical terminology exactly as specified in the glossary.
```

## Gotchas
- LLMs default to informal register in many languages — always specify register explicitly
- Glossary conflicts (model prefers its own translation) can be mitigated by instructing "use glossary terms exactly, no synonyms"
- Right-to-left languages (Arabic, Hebrew) may have subtle rendering issues in downstream display systems

## Related
- prompt-few-shot-examples
- prompt-system-message-design
- llm-for-extraction
