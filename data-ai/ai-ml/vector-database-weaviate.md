# vector-database-weaviate

**Issue:** Using Weaviate for hybrid search and multi-tenancy in RAG
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Need vector + BM25 hybrid search with schema enforcement in a single DB.

## Pattern / Solution
```python
import weaviate
from weaviate.classes.config import Configure, Property, DataType

client = weaviate.connect_to_cloud(cluster_url="...", auth_credentials=weaviate.auth.ApiKey("KEY"))
collection = client.collections.create(
    "Document",
    vectorizer_config=Configure.Vectorizer.text2vec_openai(model="text-embedding-3-large"),
    vector_index_config=Configure.VectorIndex.hnsw(),
    properties=[Property(name="text", data_type=DataType.TEXT), Property(name="source", data_type=DataType.TEXT)],
)

# Hybrid search
results = collection.query.hybrid(query="machine learning", alpha=0.5, limit=5)
```

## Gotchas
- Multi-tenancy isolates data per tenant — enable at collection creation, can't change later
- Batch imports are required for >1k documents (use `collection.data.insert_many`)
- BM25 tokenizer must match document language

## Related
- `rag-hybrid-search.md`
- `vector-database-pinecone.md`
