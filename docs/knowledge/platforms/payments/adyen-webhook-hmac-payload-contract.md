# Adyen webhook HMAC payload contract

**Issue:** One generic webhook verifier reserializes every Adyen payload before checking an HMAC. Standard webhook items and header-signed webhook types use different signed representations, so valid events fail or modified events reach business logic.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Controls and implementation

Dispatch verification by the configured webhook type and endpoint. For Standard webhooks, validate each notification item's `additionalData.hmacSignature` using Adyen's exact ordered field canonicalization or an official library. For webhook types signed in headers, capture the untouched request bytes and verify the `hmacsignature` with the documented protocol before deserialization.

Use a distinct secret per endpoint and separate test/live secrets. Compare decoded signatures in constant time, reject before enqueueing business work, and never log keys or full sensitive payloads. During rotation, accept the previous and new key only for a bounded propagation window and record which key version verified. Acknowledge verified events promptly, then process idempotently.

## Verification

Use provider fixtures plus changed field order/value, empty canonical fields, Unicode, whitespace changes in raw bodies, batched Standard items, bad Base64/hex, missing headers, wrong environment key, rotation overlap, duplicates, and oversized payloads. Assert one invalid item cannot be treated as verified by another item's signature.

## Gotchas

Basic authentication or IP filtering does not prove payload integrity. Parsing then reserializing a header-signed JSON body changes the signed bytes, while signing raw JSON is wrong for the Standard webhook field contract.

## Sources

- Adyen Docs, [Verify HMAC signatures](https://docs.adyen.com/development-resources/webhooks/secure-webhooks/verify-hmac-signatures)
- Adyen Docs, [Handle webhook events](https://docs.adyen.com/development-resources/webhooks/handle-webhook-events/)
