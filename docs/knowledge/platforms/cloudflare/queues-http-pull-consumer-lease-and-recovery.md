# queues-http-pull-consumer-lease-and-recovery

**Issue:** An external Cloudflare Queues consumer acknowledges a message before its durable side effect completes, or lacks recovery for lease expiry, retries, and backlog.
**Date:** 2026-08-11
**Author:** ORCHORDS
**Status:** documented

## Root cause

HTTP pull consumers must coordinate message receipt, bounded processing, acknowledgement, idempotency, and retry. Acknowledging before the effect is durable loses work; an unbounded handler or duplicate delivery can overload downstream systems or repeat side effects.

**Source:** [Cloudflare Queues pull consumers](https://developers.cloudflare.com/queues/configuration/pull-consumers/) and [consumer concurrency](https://developers.cloudflare.com/queues/configuration/consumer-concurrency/).

## Fix

- choose pull versus push from the ownership and network model;
- use narrowly scoped credentials for queue operations;
- bound batch size, visibility/processing time, and downstream concurrency;
- persist an idempotency record before or with the external side effect;
- acknowledge only after the side effect and durable state are complete;
- configure retries, dead-letter handling, backlog alerts, and recovery runbooks.

## Verification

- A crash before acknowledgement results in safe retry, not lost work.
- Duplicate delivery produces one durable external effect.
- Poison messages reach the documented dead-letter path.
- Backlog and processing latency alerts fire before consumer capacity is exhausted.

## Related

- `patterns/idempotency-keys.md`
- `cloudflare/workers-cron-triggers.md`
