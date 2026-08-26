# Prometheus target-limit discovery budget

**Issue**

Unbounded service discovery can create excessive targets and memory use before scrape behavior is understood.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Set `target_limit` per job from inventory and churn budgets.
- Alert on limit failures and discovered-target growth.
- Use relabeling to drop irrelevant targets before enforcement.

## Verification

1. Generate counts below, at, and above the limit.
2. Test discovery churn and reload.
3. Measure memory and target API responsiveness.

## Gotchas

- Limit failure can stop scraping the job.
- Dropped-target retention adds memory separately.
- Raising limits can hide discovery bugs.

## Official source

- [Official documentation](https://prometheus.io/docs/prometheus/latest/configuration/configuration/#scrape_config)
