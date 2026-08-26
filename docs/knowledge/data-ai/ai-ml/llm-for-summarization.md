# llm-for-summarization

**Issue:** LLM summarization produces inconsistent length, style, and accuracy across document types
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A document summarization pipeline produces summaries that are too long for some documents and miss key facts in others. Users complain that summaries omit numbers and dates that are critical for their work.

## Pattern / Solution
Specify format constraints in the prompt (bullet count, word limit, required elements). For long documents, use a map-reduce pattern: chunk then summarize each chunk then summarize the summaries. For extractive summarization (preserving exact language), ask for quotes with page references rather than paraphrases.

```
Summarize in exactly 5 bullet points. Each bullet must:
- Start with a key claim
- Include any relevant numbers or dates
- Be under 20 words

Document: {text}
```

## Gotchas
- "Summarize this" without constraints yields wildly variable length — always specify length
- Map-reduce can lose inter-chunk context (e.g., a conclusion that references an earlier section)
- Hallucinated numbers in summaries are common — consider extractive summaries for fact-critical domains

## Related
- rag-context-compression
- llm-for-extraction
- prompt-output-format-control
