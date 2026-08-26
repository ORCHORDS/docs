# agent-tool-design

**Issue:** Designing tools that agents use reliably
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Poorly designed tools cause hallucinated arguments and silent failures in agents.

## Pattern / Solution
```python
from pydantic import BaseModel, Field

class SearchInput(BaseModel):
    query: str = Field(description="Search query string, specific and concise")
    max_results: int = Field(default=5, ge=1, le=20, description="Number of results to return")

async def search_docs(input: SearchInput) -> str:
    """Search the documentation database. Returns relevant document excerpts."""
    results = await vector_search(input.query, top_k=input.max_results)
    if not results:
        return "No results found. Try a different query."
    return "\n---\n".join(f"[{r['source']}]: {r['text']}" for r in results)
```

## Gotchas
- Return strings, not dicts — models handle text better than structured data
- Always return something, even on empty results — avoid None/exceptions
- Keep tool count low; >10 tools degrades model decision quality

## Related
- `llm-tool-use-patterns.md`
- `agent-error-recovery.md`
