# rag-architecture-overview

**Issue:** Understanding the components and data flow of a RAG system
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
RAG (Retrieval-Augmented Generation) combines search with generation to ground LLM answers in real data.

## Pattern / Solution
```
RAG Pipeline:
1. Ingest: Document → Chunk → Embed → Store in vector DB
2. Query: User query → Embed → Vector search → Retrieve top-k chunks
3. Generate: chunks + query → LLM prompt → Answer with citations

Components:
- Chunker: splits docs into meaningful segments
- Embedder: converts text to dense vectors
- Vector store: index for similarity search
- Reranker: re-scores retrieved chunks
- Generator: LLM that synthesizes the answer
```

## Gotchas
- Retrieval quality is the bottleneck — invest here first
- Chunk size affects both recall (large) and precision (small)
- Always evaluate end-to-end, not just retrieval in isolation

## Related
- `rag-document-chunking.md`
- `rag-embedding-models.md`
- `rag-vector-search.md`
