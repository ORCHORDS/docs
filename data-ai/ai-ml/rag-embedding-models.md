# rag-embedding-models

**Issue:** Selecting and using embedding models for RAG
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Wrong embedding model leads to poor semantic search relevance.

## Pattern / Solution
```python
# OpenAI embeddings (best quality/cost balance)
from openai import OpenAI
client = OpenAI()
response = client.embeddings.create(input=["text to embed"], model="text-embedding-3-large")
vector = response.data[0].embedding  # 3072 dims

# Local via sentence-transformers (no API cost)
from sentence_transformers import SentenceTransformer
model = SentenceTransformer("BAAI/bge-large-en-v1.5")
vectors = model.encode(["text to embed"], normalize_embeddings=True)

# Matryoshka embeddings — truncate to reduce cost
short_vector = vector[:256]  # from 3072 to 256 dims
```

## Gotchas
- Match query and document embedders — must be the same model
- Normalize embeddings before cosine similarity search
- Domain-specific fine-tuned embedders outperform general ones

## Related
- `embedding-generation-patterns.md`
- `embedding-batching.md`
