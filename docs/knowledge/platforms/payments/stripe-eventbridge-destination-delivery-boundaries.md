# Stripe EventBridge Destination Delivery Boundaries

**Issue:** Sending Stripe events directly to Amazon EventBridge removes a public webhook endpoint, but it does not provide ordered, exactly-once business processing or eliminate trust and reconciliation design.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Create a Stripe event destination for the intended account, organization, or connected-account scope and subscribe only to required event types. Bind the partner event source to a dedicated event bus and restrict AWS resource policies so only approved rules and consumers can use it. Keep development, test, and production destinations separate.

Route events to a durable queue or idempotent workflow before business side effects. Persist the Stripe event identifier and relevant object/transition key; duplicates become successful no-ops. Do not assume arrival order. For thin events, fetch the related object with the correct account context; for snapshot events, decide whether event-time or current state is authoritative.

Configure a dead-letter destination, retry and age policies, encryption, log redaction, and alarms for failed invocations and backlog. Reconcile provider objects against the internal ledger because event delivery is a trigger, not the sole financial record.

## Verification

Use Stripe sandbox/CLI and AWS test rules to exercise correct scope, duplicates, out-of-order events, consumer timeout, throttling, poison payload, destination disablement, DLQ replay, and unknown event types. Prove replay cannot repeat fulfillment or refund and validate least-privilege policies with a denied unauthorized principal.

## Gotchas

EventBridge changes transport, not payment semantics. Organization and connected-account scopes differ. Broad wildcard subscriptions raise cost and blast radius. Never place API keys in event payloads, rules, logs, or DLQ inspection tools.

## Sources

- [Stripe Amazon EventBridge destinations](https://docs.stripe.com/event-destinations/eventbridge)
- [Stripe event destinations](https://docs.stripe.com/event-destinations)
- [AWS EventBridge SaaS partner events](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-saas.html)
