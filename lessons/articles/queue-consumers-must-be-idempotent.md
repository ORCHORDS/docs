# queue-consumers-must-be-idempotent

**Issue:** Message queue consumers that are not idempotent cause duplicate side effects when messages are redelivered
**Date:** 2026-08-11
**Status:** documented

## What happened
A consumer processed an "order shipped" event by sending the customer an email and updating the shipment record. The consumer crashed after sending the email but before acknowledging the message. The broker redelivered the message. The customer received two "your order shipped" emails and customer support logged a complaint.

## The lesson
Queue consumers must be designed so that processing the same message twice produces the same outcome as processing it once. Use a deduplication table (message ID → processed at), check before processing, and acknowledge only after all side effects are durable.

## Why it matters
At-least-once delivery is the default guarantee for most message queues (SQS, Kafka, RabbitMQ). Exactly-once is expensive or impossible. If your consumer is not idempotent, you will have duplicate side effects — duplicate emails, duplicate charges, duplicate records.

## How to apply
- [ ] Store message IDs in a `processed_messages` table. Before processing, check if the ID exists; if yes, skip.
- [ ] Make all external calls (email, payment) idempotent using idempotency keys or deduplication.
- [ ] Acknowledge the message only after all side effects are durably committed.
- [ ] Test redelivery explicitly: publish a message, process it, publish the same message ID again, verify no duplicate side effects.
- [ ] Set a TTL on the deduplication table entries equal to your queue's maximum redelivery window.

## Related
- `webhook-delivery-is-not-guaranteed.md`
- `idempotency-keys-for-all-payment-calls.md`
- `circuit-breaker-prevents-cascade-failure.md`
