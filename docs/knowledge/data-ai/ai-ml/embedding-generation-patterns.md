# embedding-generation-patterns

**Issue:** Generating embeddings efficiently for documents and queries
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Naive embedding generation is slow and expensive for large document sets.

## Pattern / Solution
```python
from openai import AsyncOpenAI
import asyncio

client = AsyncOpenAI()

async def embed_batch(texts: list[str], model="text-embedding-3-small") -> list[list[float]]:
    response = await client.embeddings.create(input=texts, model=model)
    return [d.embedding for d in sorted(response.data, key=lambda x: x.index)]

# Process in batches
async def embed_all(docs: list[str], batch_size=100) -> list[list[float]]:
    tasks = [embed_batch(docs[i:i+batch_size]) for i in range(0, len(docs), batch_size)]
    results = await asyncio.gather(*tasks)
    return [emb for batch in results for emb in batch]
```

## Gotchas
- OpenAI embedding API max 2048 inputs per request
- Normalize embeddings with `normalize_embeddings=True` for cosine similarity
- Cache embeddings — recomputing is expensive

## Related
- `embedding-batching.md`
- `rag-embedding-models.md`
