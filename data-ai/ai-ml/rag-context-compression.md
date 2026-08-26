# rag-context-compression

**Issue:** Compressing retrieved context to fit within LLM context limits
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Retrieved chunks can exceed context limits or add irrelevant noise.

## Pattern / Solution
```python
# LLMLingua compression
from llmlingua import PromptCompressor

compressor = PromptCompressor(model_name="microsoft/llmlingua-2-xlm-roberta-large-meetingbank")
compressed = compressor.compress_prompt(
    retrieved_text,
    instruction="Answer the question based on the context",
    question=user_query,
    target_token=1000,
)

# Extractive approach: keep only relevant sentences
from nltk.tokenize import sent_tokenize
sentences = sent_tokenize(chunk_text)
scored = [(s, similarity(s, query)) for s in sentences]
top_sentences = sorted(scored, key=lambda x: x[1], reverse=True)[:3]
```

## Gotchas
- Aggressive compression can remove critical facts
- Use compression only when chunks exceed 60% of context budget
- Evaluate compressed vs. full context on a held-out QA set

## Related
- `rag-reranking.md`
- `llm-context-window-management.md`
