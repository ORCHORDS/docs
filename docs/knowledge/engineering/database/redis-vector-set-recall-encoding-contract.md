# Redis vector-set recall and encoding contract

**Issue:** A Redis vector-set query can look correct while returning unstable neighbors because dimension, binary encoding, quantization, search effort, or filters drift between writers and readers.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Pin a Redis version and client that support the required vector-set commands. Store the embedding model, dimension, normalization rule, quantization choice, and attribute schema beside the dataset contract. For FP32 blob input, encode values in little-endian order; otherwise use `VALUES` when cross-platform representation is more important than compact transfer.

Treat `VSIM` search effort and quantization as a measured recall/latency tradeoff. Validate filter expressions as application policy, cap candidate work, and keep tenant authorization outside similarity ranking. For manual sharding, query every required shard and merge scores under one deterministic rule; a single-shard result is not a global nearest-neighbor result.

## Verification

Use a versioned golden corpus to measure recall@k, latency, memory, filtered recall, update/removal behavior, and score ordering. Run the same FP32 fixture from each supported architecture and compare retrieved vectors. Test malformed attributes, dimension mismatch, empty sets, and shard loss.

## Gotchas

- Vector sets use cosine similarity and HNSW-specific tradeoffs; do not transplant tuning from a different index blindly.
- Updating an embedding can change graph neighbors and result order.
- Similarity is not an authorization decision.

## Official sources

- [Redis vector sets](https://redis.io/docs/latest/develop/data-types/vector-sets/)
- [Redis vector-set filtered search](https://redis.io/docs/latest/develop/data-types/vector-sets/filtered-search/)
