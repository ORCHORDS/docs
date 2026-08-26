# smart-placement-best-practices

**Issue:** Smart Placement — Workers close to backends
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your Worker is in Tokyo. Your DB is in us-east-1. The
round trip is 150ms. The user waits. You wish your
Worker ran close to the DB.

## Root cause
**Workers run close to users, not backends.** Use
Smart Placement.

**Source:** CF Placement:
https://developers.cloudflare.com/workers/configuration/placement/

## The "Smart Placement" concept

Smart Placement places Workers close to backends:
- **Auto:** Cloudflare analyzes + places
- **Smart:** Multi-backend, unknown location
- **Region:** Single known cloud region
- **Host:** Single non-cloud host

The Worker runs in the optimal DC.

## The "Smart" pattern

For Smart (auto):
```toml
[placement]
mode = "smart"
```

Smart Placement is enabled.

## The "Region" pattern

For a known region:
```toml
[placement]
region = "aws:us-east-1"
```

The Worker runs close to that region.

## The "Host" pattern

For a non-cloud host:
```toml
[placement]
host = "10.0.0.1:5432"  # L4 probe
hostname = "api.example.com"  # L7 probe
```

CF probes the host and triangulates.

## The "region support" pattern

For supported regions:
| Provider | Format | Examples |
|---|---|---|
| AWS | `aws:{region}` | `aws:us-east-1`, `aws:eu-central-1` |
| GCP | `gcp:{region}` | `gcp:us-east4`, `gcp:europe-west1` |
| Azure | `azure:{region}` | `azure:eastus`, `azure:westeurope` |

The format is `{provider}:{region}`.

## The "Smart Placement use cases" pattern

For Smart Placement use cases:
- **Multiple backends:** Smart
- **Unknown location:** Smart
- **Single DB:** Region
- **Single VM:** Region
- **Single non-cloud:** Host

The right mode per use case.

## The "Smart Placement limits" pattern

For limits:
- **Multiple subrequests:** Triggers placement
- **WaitUntil:** Not considered
- **Globally distributed services:** Not considered
- **Anycasted services:** Not considered
- **Single-homed:** Best fit

The right pattern is single-homed backends.

## The "Smart Placement analysis" pattern

For analysis:
- **1% of requests:** Baseline (no placement)
- **99% of requests:** Smart Placement
- **15 min:** Initial analysis
- **Continuous:** Re-evaluation

The analysis is ongoing.

## The "Smart Placement cost" pattern

For cost:
- **Smart Placement:** Workers Paid plan ($5/mo)
- **No extra fee:** For Smart Placement
- **Worth it:** If DB round-trip is slow

The cost is the Workers Paid plan.

## The "Smart Placement observability" pattern

For observability:
- **Request duration:** Per region
- **Placement status:** In dashboard
- **Comparison:** Smart vs baseline
- **RPS:** Per region

The metrics are in the CF dashboard.

## The "placement anti-pattern" anti-patterns

### 1. No placement for slow DB
- **Issue:** 100ms+ round trip
- **Fix:** Smart Placement

### 2. Smart for anycast
- **Issue:** Won't help
- **Fix:** Don't use

### 3. Region for multi-region DB
- **Issue:** Wrong region
- **Fix:** Smart

### 4. No monitoring
- **Issue:** Don't know if it helps
- **Fix:** Compare

## Verification
- **Test:** Worker runs in expected region
- **Test:** Latency is reduced
- **Live:** Placement is monitored
- **Audit:** Quarterly review

## Gotchas
- **The "no placement for slow DB" anti-pattern.** Use
  Smart.
- **The "smart for anycast" anti-pattern.** Don't use.

## Related
- `cloudflare/workers-best-practices.md`
- `cloudflare/hyperdrive-best-practices.md`
- `cloudflare/d1-best-practices.md`
- CF Placement: https://developers.cloudflare.com/workers/configuration/placement/
