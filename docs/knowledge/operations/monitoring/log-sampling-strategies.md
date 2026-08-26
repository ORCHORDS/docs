# log-sampling-strategies

**Issue:** Reducing log volume at high traffic without losing important signals
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Logging every request at 50k RPS generates terabytes daily. Storage and ingestion costs are unsustainable.

## Pattern / Solution
Head-based sampling: log N% of requests randomly (10%). Simple but loses rare events. Tail-based sampling: buffer all logs per trace, keep 100% of traces with errors/slow requests and sample the rest. Priority sampling: always log errors, warnings, and slow requests; sample info/debug at 1-5%. Implement at the logging agent layer (Vector, Fluentd) not application code.

## Gotchas
Sampled logs break rate calculations — multiply counts by 1/sample_rate. Never sample error logs — they are low volume and high value. Sampling decisions must be consistent per trace ID. Structured logs with sampling rate metadata enable reconstruction of true rates.

## Related
log-structured-logging, log-correlation-ids, log-retention-policies, loki-retention-config
