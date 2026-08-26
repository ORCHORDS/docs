# langchain-patterns

**Issue:** Using LangChain for composable LLM application pipelines
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
LangChain provides composable LCEL chains for building retrieval and agent pipelines.

## Pattern / Solution
```python
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_community.vectorstores import Chroma

embeddings = OpenAIEmbeddings()
vectorstore = Chroma.from_documents(docs, embeddings)
retriever = vectorstore.as_retriever(search_kwargs={"k": 5})

prompt = ChatPromptTemplate.from_template("Answer using context:\n{context}\n\nQuestion: {question}")
llm = ChatOpenAI(model="gpt-4o")

chain = ({"context": retriever | format_docs, "question": RunnablePassthrough()}
         | prompt | llm | StrOutputParser())

answer = chain.invoke("What is RAG?")
```

## Gotchas
- LCEL `|` operator creates lazy pipelines — use `.invoke()` or `.stream()` to run
- Avoid LangChain abstractions for simple use cases — adds debugging complexity
- Pin LangChain versions; breaking changes are frequent

## Related
- `llamaindex-patterns.md`
- `rag-architecture-overview.md`
