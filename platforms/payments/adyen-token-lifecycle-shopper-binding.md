# Adyen token lifecycle and shopper binding

**Issue:** A merchant treats an Adyen `storedPaymentMethodId` as a reusable card number, looks it up without the original shopper binding, or assumes a create response is the final token state. Tokens cross tenant/customer boundaries or disabled methods remain selectable.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Identity boundary

Adyen stored payment methods are merchant/account-scoped references used together with a stable `shopperReference` and recurring-payment context. A token is not a PAN, proof of cardholder identity, payment authorization, or universal credential.

Bind locally:

- merchant account and environment;
- tenant/account;
- internal customer ID;
- exact non-PII `shopperReference` used with Adyen;
- `storedPaymentMethodId`;
- payment method type/brand and safe display metadata;
- lifecycle status and latest canonical event/version.

Never accept `shopperReference` or token ownership from client form fields. Resolve them from the authenticated server-side customer record.

## Creation and use

1. Generate a stable shopper reference that contains no name, email, or other directly identifying data prohibited by Adyen guidance.
2. During the shopper-present interaction, send the documented `shopperInteraction` and `recurringProcessingModel` values for the intended consent/use case.
3. Capture explicit product consent and display terms separately from the API parameters.
4. Treat token creation/updates as asynchronous-capable. Ingest Adyen recurring token lifecycle webhooks (created, updated, disabled) idempotently and reconcile to canonical state.
5. For a later payment, load the token through the authenticated customer/tenant relation and send the correct recurring model and shopper-interaction context.
6. Re-authorize every payment normally. A stored method reduces data re-entry; it does not bypass issuer authentication, risk, amount/currency, or SCA rules.
7. On removal, request/observe disablement and immediately hide the local method while final state reconciles. Retain an audit tombstone, not sensitive instrument data.
8. Handle account updater/network-token changes as metadata/lifecycle events without changing local ownership.

## Webhook controls

Verify Adyen webhook authenticity using the documented mechanism, deduplicate the event, and tolerate reordering. Do not let an older “created” delivery reactivate a token already disabled. When ordering is ambiguous, query/reconcile using the supported Adyen management APIs or the latest event metadata.

Separate token webhooks from payment outcome webhooks. A token can exist after a declined payment, and token disablement is not a refund.

## Verification

Test first storage, duplicate create delivery, existing token reuse, updated metadata, disabled token, removal timeout, two tenants with similar customer IDs, wrong shopper reference, merchant/test-live separation, off-session issuer challenge/decline, webhook replay/reordering, account update, and customer deletion. Assert every charge path enforces token-owner binding server-side.

## Gotchas

- Never log full payment method payloads or put token identifiers in analytics URLs.
- `recurringProcessingModel` expresses transaction context; choose it from the actual business agreement.
- A locally active token can be stale; handle Adyen rejection and reconcile.
- Deleting a customer record needs a documented retention and token-disable workflow.

## Sources

- [Adyen — Create tokens](https://docs.adyen.com/online-payments/tokenization/create-tokens)
- [Adyen — Manage tokens](https://docs.adyen.com/online-payments/tokenization/managing-tokens/)
