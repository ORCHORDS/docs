# feature-store-vs-cache

**Issue:** Feature store vs cache — when to use which for ML
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your ML team uses a feature store (Tecton, Feast). Your
backend team uses KV as a cache. They have similar
mechanics but different semantics. The teams argue about
which to use. A user sees stale features in the model.

## Root cause
**A feature store and a cache solve different problems.**
Conflating them causes confusion. Choosing wrong is a perf
or correctness bug.

**Source:** Various ML platform guides.

## The comparison

### Cache
- **What:** Storing recent results for fast retrieval
- **Purpose:** Avoid recomputing expensive work
- **Lifetime:** TTL-based, can be evicted anytime
- **Consistency:** Eventually consistent
- **Staleness:** Acceptable (the user may see slightly stale
  data)
- **Examples:** KV, Redis, Memcached

### Feature store
- **What:** Storing pre-computed ML features for inference
- **Purpose:** Provide consistent, fresh features to models
- **Lifetime:** Time-based, must be reliable
- **Consistency:** Strongly consistent (for inference)
- **Staleness:** Not acceptable (the model needs fresh features)
- **Examples:** Feast, Tecton, Databricks Feature Store

## The decision matrix

| Use case | Use |
|---|---|
| Caching HTTP responses | Cache (KV) |
| Storing user preferences | Cache (KV) or D1 |
| Storing ML features for inference | Feature store |
| Storing search index | Search service (Algolia, etc.) |
| Storing session state | D1 or DO |
| Storing rate limit tokens | Cache (KV) or DO |
| Storing aggregated metrics | Cache (KV) or analytics service |
| Storing model embeddings | Feature store (or Vectorize) |

## The "feature freshness" requirement

ML models have different freshness requirements:
- **User profile features** (age, location): stable, can be
  cached for hours
- **Behavioral features** (recent activity, last 7 days):
  change daily, can be cached for minutes
- **Real-time features** (current session, current page):
  change constantly, must be fresh

A feature store has different TTLs per feature:
```python
@feature_store.feature(
    owner="data-team",
    ttl_seconds=86400,  # 1 day
)
def user_age(...): ...

@feature_store.feature(
    owner="data-team",
    ttl_seconds=60,  # 1 minute
)
def user_recent_activity(...): ...

@feature_store.feature(
    owner="data-team",
    ttl_seconds=0,  # real-time
)
def user_current_page(...): ...
```

## The "online vs offline" feature store

A feature store has 2 modes:
- **Online:** low-latency reads for inference (Redis-style)
- **Offline:** bulk reads for training (data warehouse-style)

The online store is what you use at inference. The offline
store is for training the model.

```
Training data: feature_store.get_historical_features(...)
                                          ↓
                                       (S3 / data warehouse)

Inference: feature_store.get_online_features(...)
                                          ↓
                                       (Redis / DynamoDB)
```

## The "feature consistency" requirement

For ML models, the features used at training must match the
features used at inference. If they differ:
- **Training:** "user's avg purchase 30d" computed across all
  orders
- **Inference:** "user's avg purchase 30d" computed across
  recent orders

The model expects the first; gets the second. The prediction
is wrong.

A feature store enforces this consistency by storing the
computation logic + the same data source.

## The "CF Workers + feature store" story

CF Workers is not a great fit for a feature store:
- **No Redis-style low-latency DB** (KV is eventually
  consistent; D1 is too slow)
- **No streaming compute** (Workers are request-driven)
- **No batch compute** (Workers are stateless)

For CF Workers, the practical approach:
- **For small models:** compute features inline + cache in
  D1 or DO
- **For large models:** use a managed feature store (Tecton,
  Feast Cloud) accessed over HTTP
- **For embeddings:** use Vectorize (CF native)

## The "feature store" anti-patterns

### 1. Treating the feature store as a generic cache
The feature store has its own lifecycle. Don't use it for
general caching.

### 2. Computing features at inference
If you compute the feature at inference, you have a
"training/serving skew" risk. Compute at training time,
store, fetch at inference.

### 3. Using different feature definitions in training and inference
The most common ML production bug. Use a single feature
definition, used by both.

### 4. Letting features go stale
A feature that's "stale" produces wrong predictions. Monitor
feature freshness; alert on stale.

## The "feature store" alternatives

If a feature store is overkill:
- **Compute features in the application** and store in D1
- **Use D1 + DO** as a poor-man's feature store
- **Use a managed ML platform** (Vertex AI, SageMaker) that
  includes a feature store

## Verification
- **Test:** `test/feature-store.test.ts > features are
  consistent between training and inference` — passes
- **Live:** Feature freshness is monitored; alerts on stale
- **Audit:** Quarterly review of feature quality + drift

## Gotchas
- **A feature store is not a database.** It's a feature
  management system. Don't try to use it as a general DB.
- **A feature store is not free.** Managed feature stores
  cost $1k-$10k/month. Self-hosted is engineering time.
- **Features have a TTL.** A "user's age" feature is stable
  for years. A "user's last 7 days" feature is fresh for
  minutes. Pick the right TTL.
- **Feature drift** is a silent killer. The data changes
  (e.g. users get older, behavior changes). The model
  doesn't adapt. Monitor the inputs and outputs.

## Related
- `cache-strategies.md` (the cache story)
- `feature-store-decisions.md` (the feature store story)
- `cache-strategies.md` (the cache story)
- Feast: https://feast.dev/
- Tecton: https://www.tecton.ai/
