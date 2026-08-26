# vector-index-ann-algorithms

**Issue:** Every vector database article tells you how to run HNSW in that database; almost none explain the algorithm tradeoffs underneath, which is what you actually need when choosing between HNSW, IVF (+PQ), and DiskANN-class indexes, or when recall quietly degrades after a data migration. Picking the wrong index family or leaving tuning knobs at defaults costs you either RAM (HNSW keeping all vectors in memory), recall (untuned nprobe/ef_search), or write throughput (constant HNSW rebuilds). This article is the algorithm-level view: the families, the selection logic, the tuning procedure, and the memory math.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The algorithm families

1. **HNSW (graph-based).** Builds a multi-layer proximity graph; queries walk from a top-layer entry point greedily toward the target. Fastest queries at high recall and great defaults, but memory-hungry: full-precision vectors plus graph links generally live in RAM. Tuning knobs: ef_construction (build quality, build time) and ef_search (recall/latency dial at query time).

2. **IVF / IVFFlat (cluster-based).** Partitions space into nlist clusters (usually via k-means); queries probe only nprobe nearest clusters. Cheaper to build, lower memory floor, tolerates larger-than-RAM datasets when combined with compression — but recall depends heavily on nprobe and on clusters matching your query distribution.

3. **Product quantization (PQ) as compression, not an index.** PQ compresses vectors (e.g., 1536-d float32 to ~64 bytes) at a recall cost, and is usually combined with IVF or a re-ranking step. Use it when the memory budget cannot hold full vectors; always re-rank shortlisted candidates with full vectors when recall matters.

4. **DiskANN / Vamana (SSD-based graph).** Keeps a compact graph in RAM and vectors on SSD, serving billion-scale sets at millisecond latency with roughly an order of magnitude less RAM than HNSW. Unlike HNSW/IVF, which often need rebuilds to sustain recall under churn, DiskANN-class indexes handle inserts and deletes more gracefully. Tuning: search list size and beam width, and it needs more experimentation than HNSW to hit targets.

## Choosing by scale and memory budget

1. **Under ~1M vectors, start with HNSW defaults.** For mid-sized corpora with RAM available, HNSW with stock parameters is close to optimal and the least engineering effort. The 2025 benchmark literature (IISWC storage-based ANN study, vendor comparisons) consistently shows HNSW winning default-config latency/recall at small-to-medium scale.

2. **1M-100M with RAM pressure: IVF + PQ + re-rank.** Cluster-based search with compressed vectors cuts memory dramatically; recover recall by fetching full vectors for the top-k x 5-10 candidates and re-scoring. This is the standard large-scale RAG pattern.

3. **Billion-scale or SSD-bound: DiskANN family.** When the vector set exceeds affordable RAM, SSD-resident graph indexes deliver high recall at ms latency (Microsoft DiskANN, and related implementations in LanceDB/Milvus/Qdrant ecosystems). Budget the tuning time — Vectroid's comparison found HNSW works well with defaults while DiskANN parameters need deliberate experimentation.

4. **High-churn workloads shift the choice.** HNSW graphs degrade with heavy insert/delete and may need periodic rebuilds to restore recall; DiskANN and IVF handle updates more gracefully. If your corpus rewrites continuously (crawls, feeds, dedupe-freshness pipelines), factor rebuild cadence into the index decision, not just query performance.

## Tuning to a recall target

1. **Fix a ground-truth set first.** Sample 200-1000 realistic queries, compute exact brute-force top-k for them, and measure recall@k of the ANN index against that truth. Without this, "tuning" is astrology.

2. **Tune one query-time knob.** HNSW: raise ef_search until recall@k meets target (e.g., >= 0.95); each doubling costs roughly proportional query-time. IVF: same procedure with nprobe. Set the target from downstream task tolerance — RAG with a reranker tolerates lower recall@k than exact nearest-neighbor lookup.

3. **Set build-time knobs from data size.** IVF nlist rule of thumb is sqrt(N) to 4*sqrt(N) clusters (with at least ~39k points per cluster in pgvector's guidance; use more lists for bigger sets). HNSW ef_construction of 100-200 is a sane range; higher improves graph quality at build-time cost.

4. **Re-tune after embedding-model migrations.** Recall settings do not transfer across embedding models or dimensions — a new model changes distance distributions and cluster fit. Make recall measurement part of the embedding-migration checklist (see embedding-model-migration notes).

## Memory and storage math

1. **HNSW RAM = vectors + graph.** Full-precision 1536-d vectors cost ~6KB each (float32); graph links add ~30-100% overhead depending on M. One million such vectors is roughly 6-12GB RAM before the database's own overhead. This is why HNSW-at-scale hurts.

2. **PQ compression ratio is tunable per segment.** 8-bit codebooks per sub-vector typically land at 20-40x compression with a few points of recall loss recoverable via re-rank. Compute your budget as (vectors x compressed-bytes) + (full vectors for the re-rank tier, optionally on disk).

3. **DiskANN trades RAM for SSD IOPS.** Plan for the RAM-resident compact graph plus SSD latency under your QPS; beam width directly controls read amplification. On cloud NVMe this is usually the cheapest billion-scale path.

## Operational lifecycle

1. **Build offline, swap atomically.** Index construction for large corpora takes minutes-to-hours; build into a shadow index and alias-swap rather than indexing inline while serving traffic.

2. **Monitor recall as an SLO, not a one-time check.** Data drift and graph degradation silently erode recall. Schedule the ground-truth recall probe as a recurring job and alert on recall@k drops — the vector-search equivalent of a canary.

3. **Version indexes with embedding models.** Store embedding-model version as index metadata and refuse queries whose embeddings come from a different model. Mixing embeddings from two models in one index is a silent corruption bug that looks like "search got worse."
