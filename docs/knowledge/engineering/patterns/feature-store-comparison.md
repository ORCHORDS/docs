# feature-store-comparison

**Issue:** Feature store — Feast vs Tecton vs Databricks
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your ML team rebuilds features 5 times. Train-serve
skew. Real-time predictions are 100ms+ slow. The
data scientist wants a feature store. You don't know
which one. Feast? Tecton? Databricks?

## Root cause
**Features are scattered. Build a feature store.**

**Source:** Dasroot 2026 + Tecton 2026.

## The "feature store" concept

Feature store:
- **Centralized:** Repo for features
- **Sits between:** Raw data + ML models
- **Provides:** Registry + offline + online
- **Decouples:** ML from data infrastructure

The store is the layer.

## The "3 stages" pattern

For feature pipeline:
1. **Ingestion:** Raw data → store
2. **Transformations:** Compute features
3. **Ingestion:** To online + offline

The stages are sequential.

## The "online vs offline" pattern

For stores:
- **Online:** Low-latency, real-time inference (Redis)
- **Offline:** Training, batch (S3, BigQuery)
- **Consistency:** Same values for same entity

The split is per use.

## The "Feast" pattern

For Feast:
- **Type:** OSS, self-managed
- **Version:** 0.10 (2026)
- **Stores:** Redis, DynamoDB, Datastore
- **Batch/streaming:** Yes
- **Pipelines:** External (not managed)
- **Governance:** Limited, add-on
- **Latency:** ~1ms (Redis + Java gRPC)
- **Use:** Custom, multi-cloud

The Feast is OSS flexible.

## The "Tecton" pattern

For Tecton:
- **Type:** Commercial, managed
- **Version:** 1.5 (2026)
- **Stores:** Proprietary centralized
- **Pipelines:** Managed (built-in)
- **Governance:** Built-in, lineage, audit
- **Latency:** Enterprise-grade, 99.999%
- **Use:** Enterprise, compliance-heavy

The Tecton is full mgmt.

## The "Databricks Feature Store" pattern

For Databricks:
- **Type:** Native to Databricks
- **Compute:** Via Spark
- **Integration:** With MLflow, Delta
- **Use:** Databricks-native teams

The Databricks is native.

## The "Vertex AI Feature Store" pattern

For Vertex:
- **Type:** GCP native
- **Compute:** BigQuery external
- **Use:** GCP ML teams

The Vertex is GCP.

## The "SageMaker Feature Store" pattern

For SageMaker:
- **Type:** AWS native
- **Compute:** External
- **Use:** AWS ML teams

The SageMaker is AWS.

## The "5 architectural criteria" pattern

For evaluation:
1. **Feature freshness:** Batch vs streaming vs continuous
2. **Consistency:** Per-key eventual vs cross-entity
3. **Semantic operations:** Native vector search?
4. **Where compute happens:** External vs internal
5. **Operational surface:** How many systems

The 5 are the criteria.

## The "feature freshness" pattern

For freshness:
| Model | Latency |
|---|---|
| Batch sync | Hours |
| Streaming | Seconds |
| Continuous (in-system) | Immediate |

The model is per need.

## The "consistency" pattern

For consistency:
- **Per-key eventual:** Common, simple
- **Per-key strong:** Slightly better
- **Cross-entity transactional:** Rare, expensive

The guarantee is per design.

## The "Feast architecture" pattern

For Feast:
```
[Source] → [Spark / Kafka pipeline]
              ↓ (precomputed features)
[Feast Registry] → [Offline: S3/BQ/Redshift]
                  → [Online: Redis/DynamoDB]
                            ↓
                       [Model serving]
```

The Feast is decoupled.

## The "Tecton architecture" pattern

For Tecton:
```
[Source] → [Tecton SDK]
              ↓ (declarative)
[Tecton Platform]
   ├─ Batch pipeline (managed)
   ├─ Streaming pipeline (managed)
   ├─ Real-time compute (managed)
   ├─ Online store (managed)
   └─ Offline store (managed)
              ↓
         [Model serving]
```

The Tecton is integrated.

## The "comparison" pattern

| Feature | Feast | Tecton | Databricks |
|---|---|---|---|
| Compute features | No | Yes | Via Spark |
| Managed | No | Yes | Yes |
| OSS | Yes | No | No |
| Latency | 1ms | Enterprise | Variable |
| Governance | Limited | Built-in | Databricks |
| Versioning | Manual | Built-in | Delta |
| Compliance | Add-on | Native | Databricks |

The choice is per need.

## The "decision" pattern

For choice:
| Situation | Pick |
|---|---|
| OSS, custom, multi-cloud | Feast |
| Enterprise, compliance | Tecton |
| Databricks-native | Databricks FS |
| GCP-native | Vertex |
| AWS-native | SageMaker |
| Real-time + low-latency | Feast + Redis |
| Managed pipeline | Tecton |

The decision is per stack.

## The "Feast Redis perf" pattern

For Feast:
- **Redis Enterprise:** Tiered memory (DRAM + Flash)
- **TTL:** Per entity expiration
- **Java gRPC server:** Lowest latency
- **CPU:** 8 cores/node
- **Memory:** 100GB/node
- **Disk:** SSD + Flash

The Feast perf is per config.

## The "Tecton strengths" pattern

For Tecton:
- **Declarative features:** Define once
- **Auto pipelines:** Batch + stream
- **Backfill:** Auto
- **Monitoring:** Drift, freshness
- **Lineage:** Built-in
- **Audit:** Native
- **SLA:** Enterprise

The Tecton is full.

## The "operational surface" pattern

For ops:
- **Feast:** ~6 systems (orchestrator, batch, stream, offline, online, sync)
- **Tecton:** ~1 system (managed)
- **Databricks:** ~3 (Spark, Delta, MLflow)

The surface is per choice.

## The "train-serve skew" pattern

For skew:
- **Issue:** Train values ≠ serve values
- **Cause:** Different code paths
- **Fix:** Single source of truth (feature store)
- **Validation:** Same entity → same value

The skew is prevented.

## The "real-time serving" pattern

For real-time:
- **Online store:** Low-latency
- **Get features:** At inference
- **Latency budget:** < 10ms
- **Cache:** In serving layer

The real-time is fast.

## The "Feast vs Tecton" choice

| Factor | Feast | Tecton |
|---|---|---|
| Mgmt | Self | Tecton |
| Pipelines | External | Managed |
| Governance | Limited | Native |
| Real-time | Yes | Yes |
| Versioning | Manual | Built-in |
| Best for | Custom | Enterprise |
| Cost | Ops time | $ |

The choice is per need.

## The "evaluation" pattern

For evaluation:
1. **Define:** Hardest feature
2. **Implement:** End-to-end
3. **Measure:** Freshness gap
4. **Break:** Load + node kill
5. **Count:** Systems operated

The eval is empirical.

## The "do I need a feature store" pattern

For need:
- **Yes if:** Multiple models + reuse + consistency
- **No if:** 1 model, no reuse, simple

The need is per project.

## The "vector search" pattern

For vector features:
- **Use case:** RAG, similarity
- **In feature store:** Native or external
- **Tecton:** Native vector support
- **Feast:** External (e.g., Pinecone)

The vector is per stack.

## The "no feature store" anti-pattern

For no store:
- **Issue:** Each team rebuilds
- **Result:** Inconsistency, skew
- **Fix:** Feature store

The store is required.

## The "train-serve skew" anti-pattern

For skew:
- **Issue:** Different values
- **Fix:** Single source

The skew is detected.

## The "no monitoring" anti-pattern

For no monitoring:
- **Issue:** Drift undetected
- **Fix:** Drift + freshness alerts

The monitoring is required.

## The "Feast checklist" pattern

For Feast:
- [ ] Redis cluster sized
- [ ] Java gRPC server
- [ ] TTL configured
- [ ] Online + offline store
- [ ] Pipelines (Spark, Kafka)
- [ ] Backfill job
- [ ] Monitoring (drift)

The checklist is 7.

## The "Tecton checklist" pattern

For Tecton:
- [ ] Declarative features
- [ ] Auto pipelines
- [ ] Lineage tracked
- [ ] Drift detection
- [ ] Audit logs
- [ ] SLA documented

The checklist is 6.

## Verification
- **Test:** Train value = serve value
- **Test:** Freshness < SLA
- **Test:** Drift detected
- **Test:** Backfill works
- **Audit:** Quarterly

## Gotchas
- **The "no feature store" anti-pattern.** Build it.
- **The "train-serve skew" anti-pattern.** Single source.
- **The "no monitoring" anti-pattern.** Drift alerts.

## Related
- `patterns/data-mesh-vs-fabric.md`
- `patterns/ai-ml-detail.md`
- `patterns/observability-three-pillars.md`
- `patterns/data-warehouse-modern.md`
- Dasroot: https://dasroot.net/posts/2026/01/feature-stores-feast-vs-tecton-ml-engineering/
- Tecton: https://resources.tecton.ai/hubfs/Choosing-Feature-Solution-Feast-or-Tecton.pdf
- Tacnode: https://tacnode.io/post/how-to-evaluate-a-feature-store
