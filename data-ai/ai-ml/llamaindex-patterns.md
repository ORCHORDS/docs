# llamaindex-patterns

**Issue:** Using LlamaIndex for RAG and data indexing workflows
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
LlamaIndex abstracts document loading, chunking, embedding, and querying for RAG.

## Pattern / Solution
```python
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, Settings
from llama_index.llms.anthropic import Anthropic
from llama_index.embeddings.openai import OpenAIEmbedding

Settings.llm = Anthropic(model="claude-opus-4-5")
Settings.embed_model = OpenAIEmbedding(model="text-embedding-3-small")

documents = SimpleDirectoryReader("./docs").load_data()
index = VectorStoreIndex.from_documents(documents)

query_engine = index.as_query_engine(similarity_top_k=5)
response = query_engine.query("What is the deployment process?")
print(response)
```

## Gotchas
- Default chunk size is 1024 tokens; adjust per use case
- Use `StorageContext` with a vector store for production (not in-memory)
- `SubQuestionQueryEngine` for multi-document synthesis

## Related
- `rag-architecture-overview.md`
- `langchain-patterns.md`
