# RAG Ingestion Pipeline Idempotency

A non-idempotent ingestion pipeline is the root cause of most RAG pain at scale: double-embedded chunks inflate cost and the index, partially-failed runs leave the corpus in inconsistent states, and recovery requires deep manual work because every rerun produces a slightly different world. Idempotency is the property that re-running ingestion over the same source produces the same index — the same chunks, embeddings, and provenance — without tears or cost surprises. It is largely a design discipline, not an expensive refactor after the fact.

## Scope

This article covers idempotency in RAG ingestion pipelines: content-addressed deduplication, resumable runs, poisoned-input quarantine, and the cost-and-freshness controls idempotency buys. It applies to anyone running batch or streaming document processing for vector or lexical indexes.

Excluded: live document-update protocols (CDC-style streams, where the upstream database itself dedupes), embedding model choice, and re-ranker version management once the retrieval side is in production.

The principle that organizes everything: an ingestion run is a function of source content, configuration, and tools. Same inputs, same outputs. Anything that breaks this property — clock-influenced identifiers, non-deterministic splitting, mutable metadata — is a defect whose cost will eventually be paid.

## Workflow or implementation guidance

1. **Key every artifact on source content, not run metadata.** A chunk's identity is the hash of the canonicalized source span plus its configuration tuple (chunker version, structural type, embedding model, writer prompt version for contextual retrieval). Identical inputs produce the same key on every run; a rerun does nothing. Files, line numbers, timestamps, and run UUIDs are not in the key.
2. **Make the canonicalization explicit and versioned.** Whitespace handling, unicode normalization (NFC vs NFKC), case folding, and HTML/Markdown cleanup decisions are written down once and versioned together. Re-ingestion under a new canonicalization is a new identity space — old and new chunks do not collide or replace each other on a partial migration; treat the canonicalization change like an embedding-model upgrade.
3. **Implement resumable runs from the start.** Each run tracks a per-source checkpoint: which documents completed through which stages. A failing stage resumes at the last completed document, not at the beginning. The cost of an interrupted re-run is "what didn't finish," not "everything again." This is the property that makes idempotency worth having — without resumability, the property merely prevents duplicate writes from a complete run, not from a failure.
4. **Quarantine malformed or unsafe inputs explicitly.** A document with structural parse errors, encoding issues, or content that fails policy checks must not poison the index or stall the pipeline. Quarantine writes the source, the failure reason, and a stable identifier to a side store; ingestion proceeds past it; operators triage the quarantine separately. Silent skipping leaves failures invisible; aborting the run blocks good work.
5. **Separate the write path into prepare and commit.** Compute chunks and embeddings in a prepare phase that does not touch the live index; on completion, the commit phase atomically swaps versions (aliases, shadow indexes, namespace switches). A run that fails in prepare produces no index changes; a successful commit is the boundary at which new state becomes visible. Rollback is then a pointer change, not a deletion.
6. **Prove idempotency in CI, not just in design.** A fixture corpus with stable configuration runs ingestion twice; the second run embeds zero new chunks (in idempotent-by-config mode) or deterministically same chunks (in mode where re-embedding is desired) and the index hashes match. Any divergence is a regression caught before production.

## Controls

- **Prepare/commit separation enforced.** Pipeline writes go through prepare; only commit may touch live indexes; commit is gated on a successful prepare and a documented gate (evaluation results, owner approval).
- **Checkpoint durability and replayability.** Resume from a checkpoint recovers exactly the state prior to interruption, including in-progress stages; tested with simulated failures.
- **Quarantine dashboard.** Pending entries by reason and age, with explicit owner and handling rules; growth beyond tolerance is alerted.
- **Configuration tuple pinning in logs.** Every artifact carries its full configuration tuple; logs and indexes join to the tuple so changes correlate to effects.
- **Idempotency CI check.** A nightly run of the idempotency test on the fixture corpus; divergences block or page.

## Validation evidence

- Idempotency CI artifacts: prepared index hashes from two consecutive runs identical, with fixture, configuration, and tool versions recorded.
- Resumability evidence: a deliberately interrupted run resumes from the last checkpoint; the final index is identical to an uninterrupted run's.
- Quarantine audit: quarantine statistics over time by reason, source domain distribution, time-to-triage; trends indicating systemic problems visible.
- Cost evidence: re-running ingestion after a tool-only change costs ~zero, demonstrating the design delivers on its promise.

## Failure modes and correction

- **Clock-derived identifiers.** "Did this chunk already exist?" answered by mtime or a run UUID produces false duplicates or false non-duplicates. Correction: content hash plus configuration tuple; never clock-derived.
- **Non-deterministic splitting.** Splitter ordering changes between runs (concurrent map, OS-level randomization) produce duplicate chunks with different identities; index inflates. Correction: deterministic splitter invocation, sorted iteration, fixed random seeds where used; the idempotency CI catches non-determinism.
- **Quarantine abandonment.** Documents that error during ingestion are silently dropped or sit unprocessed; the live corpus drifts from the source. Correction: quarantine as a designed path with explicit owner, age alerting, and dashboards; triage is operational work, not a happy-path side effect.
- **Prepare/commit conflation.** Live index updates during prepare — a half-failed run leaves the index inconsistent. Correction: enforce the boundary mechanically (separate credentials, separate write endpoints); reconciliation runs catch leaks.
- **Canonicalization drift.** Whitespace or unicode normalization quietly changes between deploys; embeddings for the "same" source differ and the index silently grows. Correction: canonicalization pinned in the configuration tuple; changes bump the tuple and trigger a planned re-embedding migration.

## Limitations

Truly idempotent pipelines assume source content stability — when a document is re-ingested after editing, identity changes deliberately and the prior chunk is evicted (or the parent's chunk set updates per ingestion logic). Maintaining a single-canonical state across continuous edits requires streaming or CDC patterns this article does not cover. Storage of historical chunks for rollback or diff consumes resources proportional to retained versions; trade-offs between storage cost and rollback depth are policy decisions outside the ingestion boundary. Canonicalization cannot recover content lost in the source — badly OCR'd documents cannot be made well-structured by ingestion; upstream quality governs what's possible downstream.

## Canonical sources

- PostgreSQL documentation, Content-Addressable Storage Patterns (general reference): https://www.postgresql.org/docs/current/storage.html
- dbt documentation, Idempotent Materializations: https://docs.getdbt.com/docs/build/materializations