# Payment Handler service-worker lifecycle

**Issue:** A web payment handler is implemented like a permanently running application. It keeps checkout state in memory, starts work outside event lifetime, or assumes every invocation has an open client window. Service-worker termination and duplicate delivery then lose state or return an ambiguous payment result.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** emerging web standard; maintain a compatibility matrix

## Problem and applicability

The Payment Handler API lets a registered service worker respond to supported payment methods through payment-related events. A merchant invokes it through Payment Request; the user agent controls handler discovery and selection.

Use it only where current browser and platform support matches the target audience. Always preserve a conventional provider checkout or native-wallet fallback.

## Controls and implementation

1. Register the handler and instruments from a secure origin using the documented service-worker/payment-manager APIs. Bind every supported payment method to its official method manifest or allowed-origin contract.
2. Treat CanMakePaymentEvent as a bounded capability decision. Return quickly from durable configuration; do not perform invasive account enumeration or use the event as a tracking probe.
3. In PaymentRequestEvent, validate method data, origin, total, currency, and a server-issued checkout identifier before presenting or authorizing anything.
4. Use event.respondWith for the final handler response and event.waitUntil only for work the event lifecycle must keep alive. Do not launch floating promises or rely on globals after the event completes.
5. If interaction is required, open or focus a handler-controlled window through the event's permitted API. Correlate it with an unguessable one-time request identifier, validate all messages, and handle the window closing.
6. Store authoritative pending state durably. The service worker can stop between messages and restart with no in-memory state.
7. Return a method-specific response only after user confirmation. The merchant backend must validate it with the payment provider and use idempotency before granting an order.
8. Handle abort/cancel, timeout, handler update, unregistration, and duplicate invocation explicitly. A closed window is a canceled or indeterminate UX state, not proof of failure at the processor.
9. Minimize disclosed data and partition storage by account/origin contract. Do not leak whether a user has a particular funding instrument through unrestricted capability probing.

## Verification

Test handler unavailable, install/update race, service-worker termination at every step, can-make-payment true/false/error, multiple instruments, window blocked/closed, duplicate events, malformed method data, wrong merchant origin, changed amount, offline restart, cancellation, provider timeout, and merchant fallback.

Confirm no order is fulfilled from the client response alone, pending state survives worker restart, and unsupported browsers never see a dead-end handler-only checkout.

## Gotchas

- A service worker has an event lifetime, not a persistent process lifetime.
- Handler discovery does not prove the user can or will complete the payment.
- Browser support is limited and policy-sensitive.
- Payment method manifests and origin authorization are part of the trust boundary.

## Official sources

- [W3C — Payment Handler API](https://www.w3.org/TR/payment-handler/)
- [W3C — Payment Method Manifest](https://www.w3.org/TR/payment-method-manifest/)
