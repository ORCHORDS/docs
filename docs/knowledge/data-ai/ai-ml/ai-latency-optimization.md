# ai-latency-optimization

**Issue:** LLM response latency (TTFT and total time) is too high for interactive user experiences
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A chat interface has p50 latency of 3 s and p99 of 12 s. Users abandon queries after 2 s. Streaming is implemented but the first token takes 2 s, so users see a spinner for most of the perceived wait regardless.

## Pattern / Solution
Optimize Time to First Token (TTFT): use smaller/faster models for the first response, warm up connections, reduce prompt length, use prompt caching for static prefixes. Optimize total time: stream tokens as they arrive, parallelize independent LLM calls, use speculative decoding for self-hosted models. Route simple queries to faster/cheaper models.

Target budgets: TTFT < 500ms, total time < 5s. Measure both separately in your traces.

## Gotchas
- Streaming improves perceived latency dramatically — prioritize it over reducing total generation time
- Prompt caching requires exact prefix match; even whitespace changes break cache hits
- CDN-based model routing to the nearest provider region reduces network latency for global user bases

## Related
- llm-streaming-responses
- llm-async-patterns
- semantic-caching-patterns
- ai-cold-start-patterns
