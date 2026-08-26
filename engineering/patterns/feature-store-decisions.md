# feature-store-decisions

**Issue:** Feature store for ML — when you actually need one
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your ML team asks for a "feature store." You have 10 ML models.
Each model computes its own features (slowly, with bugs). The
team spends 50% of their time on feature engineering
infrastructure. You wonder if a feature store would help.

## Root cause
**Feature engineering is duplicated across models.** If 3
models all need "user's average purchase amount in the last 30
days," each computes it independently. A feature store is a
shared compute + store for these features.

**Source:** Feast (open-source feature store):
https://feast.dev/

> "A feature store is a data transformation and serving system
> that allows features to be registered, transformed, stored,
> and served consistently across models."

## What a feature store does

### 1. Feature definition
```python
# Define a feature once
@feature_store.entity("user")
class UserFeatures:
    avg_purchase_30d = Feature(Float32, description="30-day rolling average")
    churn_risk = Feature(Float32, description="Predicted churn risk")
    preferred_category = Feature(String, description="Most-purchased category")
```

### 2. Feature computation
The feature store computes the features on a schedule
(batch) or on-demand (streaming):
```python
# Batch: hourly
@feature_store.batch(timestamp_field="event_time")
def compute_avg_purchase_30d(events):
    return events.groupby("user_id").rolling(30).mean()
```

### 3. Feature storage
Features are stored in a low-latency DB (Redis, Bigtable,
Cassandra, DynamoDB):
- Online store: low-latency reads for inference
- Offline store: full history for training

### 4. Feature serving
```python
# At inference time (real-time)
features = feature_store.get_online_features(
    entity_rows=[{"user_id": "u_123"}],
    features=["user:avg_purchase_30d", "user:churn_risk"],
)
# Returns: { "user:avg_purchase_30d": 99.50, "user:churn_risk": 0.12 }
```

### 5. Feature consistency
The feature used at training time is the same as the feature
used at inference time. This avoids training/serving skew.

## When you need a feature store

✅ You need a feature store when:
- **You have multiple ML models** sharing features
- **You have high-volume, low-latency inference** (real-time
  recommendations, fraud detection)
- **You have feature freshness requirements** (features must
  be < 5 min old for inference)
- **You have data quality issues** (training data differs
  from inference data)

❌ You don't need a feature store when:
- **You have 1-2 models**
- **Inference is offline / batch** (no low-latency requirement)
- **Features are simple** (just a few columns from the DB)
- **You don't have a dedicated ML platform team**

## CF Workers + feature store?

CF Workers is not a great fit for a feature store:
- **No Redis-style low-latency DB** (KV is eventually
  consistent; D1 is slow for per-request reads)
- **No streaming compute** (Workers are request-driven)
- **No batch compute** (Workers are stateless)

For CF Workers, consider:
- **Compute features in a Worker** and store in D1 (slow but
  simple)
- **Use a managed feature store** (Feast Cloud, Tecton,
  Databricks Feature Store) for the heavy lifting
- **Use an external low-latency store** (Upstash Redis,
  Cloud Memorystore) for online features

## Build vs buy

| Aspect | Build | Buy (Tecton, Feast Cloud) |
|---|---|---|
| Cost | Engineering time | $ per feature + per request |
| Maintenance | You | Vendor |
| Customization | Full | Limited |
| Time to value | Months | Days |
| Lock-in | None | Vendor-specific |

For most teams, **buy** is the right answer. Building a feature
store is a 6-month project with a dedicated team.

## Verification
- **Test:** `test/feature-store.test.ts > features are consistent
  between training and inference` — passes
- **Live:** Feature freshness is monitored; alerts on stale
  features
- **Audit:** Quarterly review of feature quality

## Gotchas
- **Feature store is not a silver bullet.** Bad features
  produce bad models. The store doesn't fix the features.
- **Online vs offline skew** is the #1 ML production issue.
  The feature store enforces consistency, but you still need
  to verify.
- **Feature engineering is a team sport.** The data engineers,
  ML engineers, and product engineers must coordinate. A
  feature store doesn't replace the team.
- **Features have a TTL.** A "user's age" feature is stable.
  A "user's last 7 days of activity" feature needs frequent
  refresh.

## Related
- `cache-strategies.md` (similar mechanics)
- `queue-system-design.md` (for async feature computation)
- Feast: https://feast.dev/
- Tecton: https://www.tecton.ai/
