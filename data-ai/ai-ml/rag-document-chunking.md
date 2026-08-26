# rag-document-chunking

**Issue:** Splitting documents into chunks for effective RAG retrieval
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Wrong chunk size causes poor retrieval — too large loses precision, too small loses context.

## Pattern / Solution
```python
from langchain.text_splitter import RecursiveCharacterTextSplitter

splitter = RecursiveCharacterTextSplitter(
    chunk_size=512,
    chunk_overlap=64,
    separators=["\n\n", "\n", ". ", " "],
)
chunks = splitter.split_text(document)

# Semantic chunking (better for heterogeneous docs)
from semantic_chunkers import StatisticalChunker
chunker = StatisticalChunker(encoder=embedding_model)
chunks = chunker(docs=[document])
```

## Gotchas
- Use overlap to avoid splitting context across chunk boundaries
- For code: chunk by function/class, not character count
- Store chunk metadata (source, page, section) for citations

## Related
- `rag-architecture-overview.md`
- `rag-context-compression.md`
