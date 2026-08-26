# rag-citation-grounding

**Issue:** Grounding LLM answers with source citations from retrieved documents
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
RAG answers without citations are not auditable and increase hallucination risk.

## Pattern / Solution
```python
# Annotate chunks with IDs before injection
context = "\n".join([f"[{i+1}] {chunk.text}" for i, chunk in enumerate(chunks)])

prompt = f"""Answer the question using only the sources below.
Cite sources inline as [1], [2], etc.

Sources:
{context}

Question: {query}"""

# Post-process: verify citations exist
import re
cited = set(int(x) for x in re.findall(r"\[(\d+)\]", answer))
valid = cited.issubset(set(range(1, len(chunks)+1)))
```

## Gotchas
- Models sometimes cite non-existent source numbers — validate citations
- Include source URL/title in chunk metadata for user-facing links
- Citation extraction can fail if model reformats brackets

## Related
- `rag-hallucination-detection.md`
- `rag-evaluation-ragas.md`
