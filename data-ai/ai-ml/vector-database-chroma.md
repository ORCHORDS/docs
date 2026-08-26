# vector-database-chroma

**Issue:** Using ChromaDB for local and lightweight vector storage
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Need a zero-infrastructure vector DB for development or small-scale production.

## Pattern / Solution
```python
import chromadb
from chromadb.utils import embedding_functions

ef = embedding_functions.OpenAIEmbeddingFunction(api_key="KEY", model_name="text-embedding-3-small")
client = chromadb.PersistentClient(path="./chroma_db")
collection = client.get_or_create_collection("docs", embedding_function=ef)

collection.add(documents=["text1", "text2"], ids=["1", "2"], metadatas=[{"source": "a"}, {"source": "b"}])
results = collection.query(query_texts=["search query"], n_results=3)
```

## Gotchas
- PersistentClient is single-process; use HttpClient for multi-process access
- No built-in BM25; use Chroma + separate BM25 index for hybrid search
- Not suitable for >1M vectors without sharding strategy

## Related
- `vector-database-pgvector.md`
- `rag-architecture-overview.md`
