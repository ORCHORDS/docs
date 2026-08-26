# ai-cold-start-patterns

**Issue:** Serverless or on-demand LLM deployments have cold start latency that spikes p99 dramatically
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A serverless AI function takes 5-15 s on cold start due to model loading, library imports, and connection pool initialization. For interactive use cases, this is unacceptable. Traffic spikes cause simultaneous cold starts (thundering herd problem).

## Pattern / Solution
For serverless: use min instances > 0 during business hours; keep handlers warm with scheduled synthetic pings every 5 minutes. For container deployments: pre-load models at container start, not at first request. Use connection pooling initialized at startup. For ML models: use ONNX or TensorRT for faster load times than full PyTorch.

Separate cold-start-sensitive paths (interactive chat) from batch paths (background jobs) — give batch paths cold-start-tolerant infrastructure with different scaling policies.

## Gotchas
- "Warm" requests can still have high latency if the first request triggers JIT compilation — do a synthetic warm-up request at container startup
- Serverless concurrency limits cause cold starts under traffic spikes even with min instances configured
- Memory-optimize model loading: use memory-mapped files and lazy loading for large models to reduce startup time

## Related
- ai-latency-optimization
- llm-async-patterns
- llm-batch-processing
