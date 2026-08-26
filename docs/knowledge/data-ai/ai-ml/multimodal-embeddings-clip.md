# multimodal-embeddings-clip

**Issue:** Every embedding article in this knowledge base covers text embeddings, but a large class of product problems — "find the screenshot that shows the login error," deduplicate product photos, search PDFs by their figures, recommend visually similar items — needs one shared embedding space for images and text. Contrastive image-text models (CLIP, and its successor SigLIP/SigLIP 2) provide that space, and they are now a standard component of multimodal RAG and search stacks. Engineers hit predictable problems: using CLIP where a vision LLM belongs (and vice versa), zero-shot recall disappointing on domain data, dimension/storage blowups at image-corpus scale, and quietly incompatible model versions between ingestion and query time. This article covers selection, pipeline design, domain adaptation, and evaluation.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## What contrastive image-text embeddings give you

1. **One space, two modalities.** CLIP-family models encode images and text into the same vector space with a shared similarity metric, enabling text-to-image search ("diagram of a double-entry ledger"), image-to-image search (near-duplicate detection), and zero-shot classification (argmax over label embeddings). No training required for any of these.

2. **Sigmoid loss is why SigLIP 2 is the default now.** SigLIP replaces CLIP's softmax-over-batch contrastive loss with a per-pair sigmoid loss that scales better and trains more efficiently; SigLIP 2 (2025) pairs this with stronger pretraining and is the recommended starting point for new image-text retrieval projects, with practical recipes published (e.g., Elastic's SigLIP-2 kNN search walkthrough).

3. **Embeddings are not descriptions.** The text tower encodes gist and semantics, not fine detail. "Chart showing revenue up" matches a bar chart; "the exact number 42.7 on the third bar" does not. When queries need fine-grained or attribute-level matching, combine embedding recall with a vision LLM reranker — 2025 work on promptable image embeddings (arXiv 2505.15877) targets exactly this attribute-retrieval weakness.

4. **Know when a vision LLM is the better tool.** Use embeddings for retrieval/similarity at scale (millions of items, millisecond queries); use a VLM for extraction, counting, OCR-heavy reading, and reasoning about a single image. Multimodal RAG typically uses both: SigLIP to recall candidates, a VLM to ground answers in them.

## Model selection

1. **Start with SigLIP 2 (or CLIP for compatibility).** SigLIP 2 offers strong zero-shot performance across base/medium/large checkpoints with native Matryoshka (MRL) support; original CLIP/ViT-L remains fine where an existing pipeline already speaks its geometry.

2. **Prefer MRL-capable checkpoints for scale.** SigLIP 2's native Matryoshka support means one stored embedding serves multiple dimensionalities — e.g., truncate 1152-d to 256-d for the first-pass ANN search, then re-rank with full dimensions. This composes directly with the ann-vector-index memory math and the matryoshka-embeddings-mrl article.

3. **Match pretraining data to your domain.** Web-scale image-text pairs cover natural photos well; screenshots, UI captures, medical imaging, and technical diagrams are underrepresented. Budget for evaluation (below) and likely fine-tuning (further below) on domain corpora.

4. **Freeze model plus preprocessor together.** Image preprocessing (resize, normalization, center-crop vs padding) is part of the model contract. Version the exact checkpoint and preprocessing config as one unit — a mismatched transform degrades recall silently.

## Building the retrieval pipeline

1. **Index images, embed queries as text (or images).** For multimodal RAG, embed page figures/screenshots at ingestion and embed the user query with the text tower at serving time; store per-item whether it came from the image or text tower so reranking can account for asymmetric fidelity.

2. **Chunking is per-image, not per-token.** The unit of retrieval is a whole image (or a detected region). For PDFs and slides, extract figures as separate items with captions and surrounding text metadata — the caption text embeds better than pixels for keyword-adjacent queries, and metadata filtering applies unchanged.

3. **Plan storage before scaling.** Image corpora are big: 10M images at 1152-d float32 is ~46GB of vectors before the index. Use MRL truncation for the primary index, keep full-dim vectors (optionally on disk) for re-rank, and normalize so cosine similarity is a dot product.

4. **Handle near-duplicates deliberately.** Image-to-image search finds perceptual duplicates that hashing misses after crops/rescales; dedupe at ingestion using embedding clusters rather than exact hashes, or your index fills with visually identical variants.

## Domain adaptation when zero-shot is not enough

1. **Two-stage fine-tuning (2SFT).** 2025 research (Schall et al.) shows first fine-tuning on broad image-text data, then on domain pairs, measurably improves CLIP-family retrieval over single-stage adaptation. Keep stage one general to avoid catastrophic forgetting of general queries.

2. **Multi-caption-image pairing (MCIP).** Training each image against several captions (different lengths, granularities) instead of one improves robustness to how real users phrase queries — cheap to generate with a VLM describing your own images.

3. **Mine hard negatives.** Random negative pairs teach little; batch with visually similar non-matches (same photographer, same template, adjacent video frames) so the model learns the distinctions your users actually ask for.

4. **Re-embed everything after any model change.** Unlike rerankers, embedding models cannot be swapped at query time — image and query towers must match. Follow the embedding-model-migration reindex discipline.

## Evaluation and pitfalls

1. **Build a labeled query-image set first.** A few hundred real queries with judged relevant images (from logs or domain experts) beats every published benchmark for decision-making; report recall@k and MRR on that set.

2. **Test both directions.** Text-to-image and image-to-image performance differ substantially; evaluate the direction(s) the product uses, not an average.

3. **Watch for text-in-image blindness.** Models partially read prominent rendered text but miss dense small text; if queries target text inside screenshots, pair embeddings with OCR text (hybrid embedding + keyword search) rather than trusting pixels.

4. **Beware watermark and template shortcuts.** Models latch onto incidental features (watermarks, letterboxing, brand colors) as spurious correlates. Include adversarial pairs in the eval set — same subject, different template — to detect shortcut learning before users do.
