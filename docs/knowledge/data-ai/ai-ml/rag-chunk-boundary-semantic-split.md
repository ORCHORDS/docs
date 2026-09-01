# RAG Chunk Boundary Semantic Split

Retrieval quality is capped by chunk quality before any embedding model or reranker touches anything. Split a document on arbitrary character counts and you manufacture your own failures: definitions severed from their terms, tables split from headers, procedure steps scattered across chunks that each look unrelated. Chunk-boundary discipline — splitting where the document's own structure says meaning changes — is unglamorous preprocessing that quietly determines what retrieval can ever find.

## Scope

This article covers chunking strategy for RAG ingestion: fixed-size versus structure-aware splitting, boundary selection rules, overlap policy, and metadata that must survive the split. It applies to document-processing pipelines feeding retrieval systems.

Excluded: embedding model choice, retrieval fusion, and reranking (adjacent stages with their own articles), and multimodal chunking (tables-as-images, audio), which needs format-specific treatment.

A framing that prevents most bad choices: a chunk is the retrieval system's atom of context. Too small, and retrieval finds fragments without the surrounding sentences needed to use them; too large, and embeddings dilute — a chunk covering three topics matches everything and nothing. Boundary placement is how you keep chunks topically coherent without paying the dilution cost.

## Workflow or implementation guidance

1. **Start from document structure, not character counts.** Markdown headers, HTML landmarks, PDF layout artifacts, code function boundaries, and legal document numbering all mark where topics change. Split at the deepest structural level that yields chunks within the target size range; only fall back to sentence-based splitting inside oversized sections. Character-count splitting is the method of last resort, not the default.
2. **Define the size window from retrieval behavior, not folklore.** Choose minimum and maximum chunk sizes empirically: the minimum is the smallest unit that answers questions standalone; the maximum is where embedding dilution measurably hurts recall on your evaluation set. Typical windows land between a few hundred and roughly a thousand tokens, but the number is derived from retrieval metrics, then revisited when models change.
3. **Split at the widest semantic boundary available.** Prefer, in order: document-section boundaries, paragraph boundaries, sentence boundaries, clause boundaries as a last resort. Never split mid-sentence for text destined for semantic retrieval; never split between a heading and its first paragraph; never split a table row from its column headers.
4. **Use overlap surgically.** Overlap exists to survive a boundary landing mid-topic — a sentence or two of repeated context on each side. Blanket large overlaps (25–50 percent of chunk size) bloat the index, create near-duplicate retrievals that crowd out diversity, and often compensate for sloppy boundary choice. Apply small overlap where structure forced a split inside a topic; use none at clean structural boundaries.
5. **Preserve provenance metadata at split time.** Every chunk carries: document id, section path (heading hierarchy), structural type (prose, table, list, code), page or line anchors, and content hash. Provenance enables citation rendering, freshness eviction, and debugging ("which section did this chunk come from?"). Metadata lost at split time cannot be reconstructed later.
6. **Handle special structures with dedicated splitters.** Tables: keep each table (or a row-group with repeated headers) as one chunk; do not feed row fragments. Code: split at function/class boundaries with language-aware tooling. Lists: keep the list lead-in with its items. Dialogue or Q&A docs: split at speaker/turn boundaries. One generic splitter across all formats is where boundary quality dies.
7. **Evaluate boundaries with a boundary-probe set.** Build a set of questions whose answers sit exactly at natural boundary hazards — the last paragraph of a section, a definition after a long example, a table cell. Track recall on these separately; overall recall hides boundary damage that this probe set makes visible.

## Controls

- **Splitter configuration as versioned code.** Chunking rules live in version control with tests; pipelines record the splitter version per chunk so retrieval regressions join to splitter changes.
- **Structural-integrity assertions.** Ingestion checks: no chunk ends mid-sentence for prose (period/punctuation heuristic where applicable); no heading-only chunks; tables never separated from headers. Violations are logged with source anchors, not silently ingested.
- **Chunk-size distribution monitoring.** Alert when the distribution shifts — a new source format producing 4,000-token chunks or 20-token fragments changes retrieval behavior before anyone notices.
- **Provenance completeness check.** Every chunk in the index carries required metadata fields; a completeness scan runs on each ingestion batch.
- **Boundary-probe regression suite.** The hazard-adjacent question set runs on every splitter or embedding change; recall drops on probes block the change.

## Validation evidence

- Boundary-probe recall before/after splitter changes, per hazard type (section-end, table, list, definition).
- Chunk statistics per source format: size distribution, structural-type mix, overlap percentage actually applied — compared against the configured window.
- End-to-end retrieval evaluation (recall@k and answer quality) on the golden question set, attributed to splitter version.
- Structural-integrity violation logs trending toward zero per source format as splitters improve, with residual violations explained by format limitations.

## Failure modes and correction

- **Severed definitions.** A term is defined at a section's end; the chunk carrying the term lacks the definition and the chunk carrying the definition lacks the term's context. Retrieval surfaces both, and neither answers. Correction: structure-aware splitting keeps sections intact to the extent size allows; boundary probes on definition hazards verify.
- **Table shredding.** Fixed-size splitting turns a table into orphan rows without headers; embedding of a row fragment is noise. Correction: dedicated table splitter; integrity assertions reject headerless rows at ingestion.
- **Overlap-induced near-duplicate retrieval.** Large overlaps mean one passage retrieved as three near-identical chunks, crowding out diverse context. Correction: reduce overlap to surgical application; add near-duplicate suppression at retrieval if overlap remains necessary.
- **Heading-only fragments.** Splitting rules that isolate headings produce chunks that are navigation, not content. Correction: merge heading-only fragments forward into the following chunk; assertion forbids heading-only output.
- **Silent format drift.** A new source format arrives (different PDF generator, new markup dialect); structural detection misses its boundaries and chunks degrade to character splitting without anyone being told. Correction: per-format splitter telemetry (detected-boundary rate per document) alarms when a format stops yielding structure.

## Limitations

Optimal chunking is corpus- and question-dependent: technical references, narrative documents, and transcripts reward different granularities, so single-window configurations are always a compromise across formats. PDF structural detection is imperfect for scanned or heavily formatted documents; OCR quality bounds what any splitter achieves. Evaluation of boundary quality depends on the probe set's realism — a weak probe set certifies nothing. Chunking interacts with embedding model context capacity and reranker input limits; the window chosen here must be re-derived when those change.

## Canonical sources

- LlamaIndex documentation, Node Parser / Chunking: https://docs.llamaindex.ai/en/stable/module_guides/loading/node_parsers/
- LangChain documentation, Text Splitters: https://python.langchain.com/docs/concepts/text_splitters/
