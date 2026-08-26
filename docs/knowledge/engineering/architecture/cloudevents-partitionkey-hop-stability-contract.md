# CloudEvents partitionkey hop-stability contract

**Issue:** Producers use the CloudEvents `partitionkey` extension as if it guaranteed global ordering, while brokers or intermediate hops may remap or remove the value.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Use `partitionkey` only when the optional partitioning extension is part of the declared event contract.
- Require a non-empty, bounded, non-secret string derived from the entity whose causal ordering is needed.
- Define whether each hop preserves, transforms, or removes the attribute and map it explicitly to the broker record key.
- Keep partition selection separate from CloudEvents `id`, business correlation, idempotency, and authorization.
- Plan repartitioning and hot-key mitigation without silently changing ordering scope.

## Verification

Send related and unrelated entities through every broker hop, retry, replay, and dead-letter path. Assert required co-partitioning, document any remapping, and load-test skewed keys.

## Gotchas

The extension defines a partitioning hint, not end-to-end delivery order. Its specification explicitly permits the value to change or disappear across hops, and transport bindings may require an opt-in key mapper.

## Official sources

- [CloudEvents partitioning extension](https://github.com/cloudevents/spec/blob/main/cloudevents/extensions/partitioning.md)
- [CloudEvents Kafka protocol binding](https://github.com/cloudevents/spec/blob/main/cloudevents/bindings/kafka-protocol-binding.md)
