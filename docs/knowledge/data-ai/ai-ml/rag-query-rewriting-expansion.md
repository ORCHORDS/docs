# rag-query-rewriting-expansion

**Issue:** User queries are short, ambiguous, or phrased in a way that does not match document language, causing vector + keyword retrieval to return irrelevant chunks.
**Date:** 2026-08-13
**Status:** documented

## Symptom

Retrieval quality is poor even though the right document is in the index. Symptoms:
- Top-k results are semantically adjacent but not the actual answer.
- The user asks "how do I reset it?" and retrieval returns generic overview docs
  because "it" and "reset" never appear in the target document.
- A single-word or two-word query (e.g. "billing", "401k") returns a grab-bag
  of unrelated chunks, none of which answer the real intent.
- Adding the answer manually to the index does not improve recall, because the
  query embedding is too far from the document embedding.
- Hybrid BM25+vector helps for exact-keyword queries but does nothing for
  paraphrase or vocabulary mismatch problems.

The root cause is that the raw user query is used directly as the retrieval
probe, with no transformation. In production RAG systems this is the single
highest-leverage improvement after chunking is fixed.

## Pattern / Solution

Apply one or more query-side transformations before hitting the vector store.

### 1. Query rewriting for standalone context

LLM calls that follow a conversation inherit pronouns and implicit references.
Rewrite the follow-up into a self-contained query before retrieval.

```python
rewrite_prompt = f"""Rewrite the user's latest message into a self-contained
search query. Resolve pronouns and implicit references using conversation history.
Return ONLY the rewritten query, nothing else.

History:
{formatted_history}

Latest message: {user_message}
"""
standalone_query = llm.generate(rewrite_prompt).strip()
docs = vector_store.search(standalone_query, top_k=10)
```

### 2. Multi-query expansion

Generate multiple phrasings of the same intent and union the results.

```python
expand_prompt = f"""Generate 3 different search queries that express the same
information need as: "{user_query}". Vary vocabulary and phrasing.
Return one query per line."""
expanded = llm.generate(expand_prompt).strip().split("\n")
expanded = [q.strip() for q in expanded if q.strip()]

all_results = []
for q in expanded:
    all_results.extend(vector_store.search(q, top_k=5))

# Deduplicate by document id, then rerank
deduped = dedupe_by_id(all_results)
final = reranker.rerank(user_query, deduped, top_k=5)
```

### 3. HyDE (Hypothetical Document Embeddings)

Generate a hypothetical answer, then embed that answer instead of the query.
The idea: the generated answer is closer in embedding space to real answer
documents than the short question is.

```python
hyde_prompt = f"""Write a short paragraph (3-5 sentences) that would answer
this question. Do not worry about factual accuracy; focus on the vocabulary
and phrasing a real answer would use.

Question: {user_query}
"""
hypothetical_answer = llm.generate(hyde_prompt)
# Embed the answer, not the query
results = vector_store.search(hypothetical_answer, top_k=10)
```

### 4. Step-back prompting

Extract a broader, more abstract version of the question before retrieval.

```python
stepback_prompt = f"""Based on this question, generate a broader, more general
question whose answer would provide useful background context.

Question: {user_query}
Brother question:"""
stepback_q = llm.generate(stepback_prompt)
# Retrieve for both, then merge
results = merge(
    vector_store.search(user_query, top_k=5),
    vector_store.search(stepback_q, top_k=5),
)
```

### 5. Keyword + semantic split

For hybrid pipelines, ask the LLM to also extract likely keywords.

```python
kw_prompt = f"""Extract 3-5 keywords from this query for a BM25 search.
Return comma-separated.

Query: {user_query}"""
keywords = llm.generate(kw_prompt)
bm25_results = bm25.search(keywords, top_k=10)
```

## Gotchas

- **Latency cost.** Every rewrite is an extra LLM call (100-800ms added per
  retrieval). Cache aggressively — use a semantic cache so identical-intent
  queries skip the rewrite entirely.
- **Multi-query amplifies noise.** If one of the expanded queries is bad, it
  pollutes the merged result set. Always rerank after merging, and cap the
  number of expansions to 3-5.
- **HyDE can backfire on factual lookups.** If the question is a precise
  entity lookup ("What is the company's ticker symbol?"), a hypothetical
  answer may hallucinate the wrong entity and retrieve the wrong doc. Reserve
  HyDE for open-ended "how" and "why" questions.
- **Step-back loses specifics.** The broader question retrieves background
  but may bury the specific answer. Rerank with the original query, not the
  step-back query, as the scoring key.
- **Rewriting leaks conversation context into logs.** The rewritten query may
  contain PII from chat history. Scrub or tag it before logging.
- **Do not rewrite for every query blindly.** Short, unambiguous keyword
  queries ("billing API", "pricing page") do not benefit from expansion and
  just add latency. Gate rewriting on query length or a classifier.
- **Prompt stability.** The rewrite prompt must be frozen and versioned.
  Drift in the system prompt changes retrieval behavior silently and breaks
  eval reproducibility.
- **Eval before and after.** Always measure recall@k and answer faithfulness
  with ragas or similar before shipping a rewrite strategy. A rewrite that
  feels better can actually lower precision if the merge is unbalanced.

## Related
- `rag-document-chunking.md` — the other half of the retrieval quality problem
- `rag-hybrid-search.md` — keyword + semantic fusion, complementary to rewriting
- `rag-reranking.md` — mandatory after multi-query merge
- `rag-evaluation-ragas.md` — measure whether rewriting actually helps
- `semantic-caching-patterns.md` — avoid paying the rewrite cost twice
