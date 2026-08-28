# Lesson: At-Least-Once Delivery Changes Application Design

Queue delivery guarantees affect correctness. Consumers should expect duplicates, maintain safe deduplication or idempotent operations, and treat acknowledgement as part of the processing contract.

Source: Cloudflare Workers/Queues guidance.