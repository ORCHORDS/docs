# A2A Task Subscription Lifecycle

## Purpose

A2A v1.0 formalizes task subscription behavior for clients that need to attach to an existing task and receive continuing updates.

## Subscription model

The v1.0 operation is `SubscribeToTask`. A client uses it to receive streaming updates for a task that already exists. The protocol allows more than one concurrent subscription to the same task.

A subscription is an observation channel, not ownership of the task. Opening or closing a stream does not by itself change task state.

## Lifecycle guidance

1. Authorize the caller for the referenced task before opening a subscription.
2. Keep task identity and subscription identity conceptually separate; several subscribers may observe one task.
3. Preserve generated event order for every active subscription.
4. Close the live subscription when the task reaches a terminal state according to the binding's streaming behavior.
5. Treat client disconnects as subscription termination, not automatic task cancellation.
6. Make reconnect behavior explicit. Do not promise historical backfill unless the implementation actually supports and documents it.
7. Bound resources for slow or abandoned subscribers with timeouts, backpressure, or other transport-appropriate controls.
8. Re-check authorization on a new subscription request instead of assuming a previous stream grants continuing access.

## Migration note

A2A v1.0 renamed and clarified the earlier resubscription operation as `SubscribeToTask`. Implementations supporting older protocol revisions should negotiate the protocol version and map operations deliberately rather than silently assuming v1.0 names and lifecycle semantics.

## Sources

- A2A Protocol v1.0 specification: https://a2a-protocol.org/latest/specification/
- A2A v1.0 changes: https://a2a-protocol.org/latest/whats-new-v1/

## Scope note

Subscription lifecycle is distinct from push notifications. Push notifications are asynchronous HTTP callbacks; task subscriptions are client-initiated streaming observations.