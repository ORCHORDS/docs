# rag-ingestion-pipeline

**Issue:** RAG retrieval quality is bad because the ingestion pipeline that
feeds the vector index is an afterthought — raw documents are parsed poorly,
chunks lack metadata, updates are not incremental, and the index drifts out
of sync with source documents.
**Date:** 2026-08-13
**Status:** documented

## Symptom

Retrieval returns irrelevant or empty results even though you "ingested
everything." Common signals:
- **The right document is in the store, but retrieval misses it** because it
  was parsed as one giant blob, split mid-sentence, or stripped of section
  headings that gave it context.
- **Stale answers.** A source document was updated but the vector store still
  serves the old version — there is no update/delete path, only append.
- **Duplicate chunks.** Re-running ingestion appends identical vectors,
  inflating the index and skewing similarity scores.
- **Garbage in the index.** Boilerplate (nav menus, footers, cookie banners,
  legal disclaimers) got embedded alongside real content, polluting retrieval.
- **No provenance.** A retrieved chunk cannot be traced back to its source
  file, page number, or version, so citation and trust checks fail.
- **Ingestion is a manual script** run by hand, so the index is always behind
  the source-of-truth documents.
- **Secrets or PII leaked into the index** because no redaction ran before
  embedding.

The root cause: the ingestion pipeline is treated as "chunk and embed,"
when it is really a multi-stage data engineering pipeline whose quality
determines the ceiling of the entire RAG system.

## Pattern / Solution

A production ingestion pipeline has these stages. Each must be explicit,
logged, and idempotent.

```
Source → Fetch → Parse → Clean → Redact → Chunk → Enrich → Embed → Upsert → Verify
```

### Stage 1: Fetch (connectors)

Pull from the source-of-truth with change detection.

```python
def fetch_documents(source):
    """Return (new_or_updated, deleted) doc ids."""
    current = source.list_ids()
    seen = state_store.get_seen_ids(source.name)
    updated = [d for d in current if source.modified_after(d, seen.get(d))]
    deleted = [d for d in seen if d not in current]
    return updated, deleted
```

Support incrementality: only reprocess what changed.

### Stage 2: Parse (format-aware)

```python
def parse(doc):
    match doc.type:
        case "pdf":
            return parse_pdf_with_layout(doc.path)  # preserve headings, tables
        case "html":
            return trafilatura.extract(doc.raw)      # strip boilerplate
        case "docx":
            return python_docx_to_markdown(doc.path) # keep structure
        case "markdown":
            return doc.raw
        case _:
            return fallback_text_extract(doc.raw)
```

Preserve document structure (headings, lists, tables) as metadata — it drives
smart chunking later.

### Stage 3: Clean

Remove boilerplate and noise before chunking.

```python
def clean(text):
    text = remove_boilerplate(text)       # nav, footer, cookie banners
    text = deduplicate_lines(text)        # repeated headers/footers
    text = normalize_whitespace(text)
    text = fix_encoding_artifacts(text)   # mojibake, smart quotes
    return text
```

### Stage 4: Redact (PII / secrets)

```python
def redact(text):
    text = pii_detector.redact(text, replacements={"EMAIL": "[email]"})
    if secret_scanner.scan(text):
        raise SecurityError("secret detected, blocking ingestion")
    return text
```

Never embed secrets or PII. Fail loud rather than leak.

### Stage 5: Chunk

```python
chunks = semantic_chunker.split(
    text,
    max_tokens=512,
    overlap=64,
    respect_boundaries=True,   # split on headings/paragraphs, not mid-sentence
)
```

See `rag-document-chunking.md` for chunking strategies.

### Stage 6: Enrich (metadata)

Attach provenance and context to every chunk — this is what makes retrieval
trustworthy and filterable.

```python
for chunk in chunks:
    chunk.metadata = {
        "source_id": doc.id,
        "source_type": doc.type,
        "source_url": doc.url,
        "title": doc.title,
        "section": chunk.section_heading,
        "page": chunk.page_number,
        "chunk_index": chunk.index,
        "ingested_at": now_iso(),
        "content_hash": sha256(chunk.text),
        "embedding_model": config.embedding_model,
        "embedding_version": config.embedding_version,
    }
```

### Stage 7: Embed

```python
vectors = embedding_model.embed_batch([c.text for c in chunks])
```

See `embedding-batching.md` for efficient batching.

### Stage 8: Upsert (idempotent)

```python
for chunk, vector in zip(chunks, vectors):
    chunk_id = f"{doc.id}:{chunk.index}"
    store.upsert(id=chunk_id, vector=vector, metadata=chunk.metadata)
```

Use deterministic IDs derived from source + chunk index so re-ingestion
overwrites rather than appends. Delete chunks for deleted docs.

### Stage 9: Verify

```python
def verify(doc):
    chunks = store.list_by_source(doc.id)
    assert len(chunks) > 0, f"no chunks ingested for {doc.id}"
    assert all(c.metadata["content_hash"] for c in chunks)
    # Spot-check: embed a known query and confirm the doc is retrievable
    probe = embed("representative query for this doc")
    hits = store.search(probe, filter={"source_id": doc.id}, top_k=1)
    assert hits, f"{doc.id} ingested but not retrievable"
```

### Orchestration

Run the pipeline on a schedule or via webhooks, with idempotency and
observability.

```python
def ingest_pipeline(sources):
    for source in sources:
        updated, deleted = fetch_documents(source)
        for doc_id in updated:
            doc = source.fetch(doc_id)
            run_stages(doc)          # parse → clean → redact → chunk → embed → upsert
            verify(doc)
        for doc_id in deleted:
            store.delete_by_source(source.name, doc_id)
        state_store.commit(source.name)
    log_metrics(chunks_added, chunks_updated, chunks_deleted, errors)
```

## Gotchas

- **Append-only ingestion creates duplicates and skews similarity.** Use
  deterministic IDs and upsert semantics. Never blindly append on re-run.
- **Deleted source documents leave orphan vectors.** Your pipeline must handle
  deletes, not just adds. Without a deletion stage, the index grows forever
  and serves ghost answers.
- **Boilerplate is the #1 pollution source.** HTML pages especially — nav,
  sidebars, cookie banners, and "related articles" sections get embedded and
  retrieved. Clean before chunking, always.
- **Content hashing is mandatory for idempotency.** Without a hash, you cannot
  tell whether a document actually changed, so you re-embed everything every
  run, wasting cost and creating churn.
- **Parsing tables and code blocks is hard.** Naive text extraction flattens
  tables into garbage. Use layout-aware parsers (e.g., unstructured.io,
  docling) for PDFs with tables and figures.
- **Chunk-level metadata is retrieval currency.** Without `source_id`,
  `section`, and `page`, you cannot do metadata filtering, citation, or trust
  checks downstream. Enrich every chunk.
- **PII and secrets in the index are a security incident.** Redaction must
  run before embedding, and secret detection should hard-fail ingestion
  rather than silently pass.
- **Incremental ingestion without state is impossible.** You need a state
  store (last-seen modified time per doc) to avoid re-processing the full
  corpus every run.
- **Ingestion and query embedding models must match.** If the pipeline uses
  model A and the query path uses model B, retrieval silently breaks. Pin
  the model in config and assert it in metadata (see
  `embedding-model-migration.md`).
- **Verify, do not assume.** A successful upsert does not mean the chunk is
  retrievable. A probe query after ingestion catches indexing bugs that
  silently drop vectors.

## Related
- `rag-document-chunking.md` — the chunking stage in depth
- `rag-embedding-models.md` — model choice for the embed stage
- `embedding-batching.md` — efficient bulk embedding
- `rag-citation-grounding.md` — depends on the metadata enrichment stage
- `metadata-filtering-vectors.md` — enabled by chunk-level metadata
- `pii-detection-redaction.md` — the redaction stage
- `embedding-model-migration.md` — changing the model in a live pipeline
- `rag-hallucination-detection.md` — bad ingestion is a hallucination source
