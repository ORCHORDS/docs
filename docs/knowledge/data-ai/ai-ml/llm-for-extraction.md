# llm-for-extraction

**Issue:** Extracting structured fields from unstructured documents with LLMs produces incomplete or hallucinated data
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A contract analysis pipeline extracts party names, dates, and obligations. The LLM sometimes invents plausible-sounding values for fields not present in the document, causing downstream data integrity issues.

## Pattern / Solution
Provide exact JSON schema in the prompt and require null for absent fields — never invent. Use function calling or tool use to enforce schema. Include a confidence field and flag low-confidence extractions for human review. For multi-page documents, extract per page then merge.

```
Extract from the contract. Use null for missing fields. Do not invent values.
Schema: {"party_a": str|null, "party_b": str|null, "start_date": ISO8601|null, "value_usd": number|null}
```

## Gotchas
- Without explicit null instruction, models fill gaps with plausible hallucinations
- Dates are extracted in varied formats — always normalize to ISO 8601 post-extraction
- Overlapping fields (e.g., two different effective dates) require disambiguation instructions

## Related
- llm-for-summarization
- llm-structured-output
- llm-output-validation
- rag-citation-grounding
