# Lesson: Retries Need Idempotency

Retryable background work can run more than once. Design operations so repeated delivery does not duplicate charges, emails, writes, or state transitions unexpectedly.

Sources: Cloudflare Queues/Workflows best practices; general reliability practice.