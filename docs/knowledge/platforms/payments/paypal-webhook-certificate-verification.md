# PayPal webhook certificate verification

**Issue:** PayPal webhook JSON is not trustworthy until its transmission signature is verified for the exact registered webhook and raw request body. Parsing and reserializing first, accepting arbitrary certificate URLs, confusing the client ID with the webhook ID, or processing retries twice can turn a signed-notification integration into spoofed or duplicate payment state.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Controls

Capture the raw body bytes before JSON middleware. Require the PayPal transmission ID, time, signature, certificate URL, and authentication algorithm headers, plus the configured webhook ID for that endpoint/environment. Prefer PayPal's documented self-verification method when implemented correctly; the verify-webhook-signature API is an alternative and must fail closed on timeout or non-success.

For self-verification, construct the documented message from transmission ID, transmission time, configured webhook ID, and decimal CRC32 of the original body. Validate the certificate chain and lifetime, restrict certificate retrieval to PayPal's documented HTTPS host/path policy, prevent redirects to untrusted networks, cache only within certificate validity, and allow only documented algorithms.

## Processing contract

Acknowledge only after durable receipt, or enqueue atomically before returning 2xx. Deduplicate on PayPal event ID and also record transmission ID because retries may be distinct deliveries. Apply events through a monotonic payment state machine and reconcile important outcomes against PayPal's API; arrival order is not business order.

Separate sandbox and production credentials, webhook IDs, certificates, and event stores. Simulator events use special semantics and are not real transactions. Never let a simulator success prove production signature or settlement behavior.

## Verification

Test byte changes, JSON key reordering, wrong webhook ID, missing/duplicate headers, stale/future timestamps, unknown algorithm, expired/untrusted certificate, certificate-host SSRF, API verifier outage, duplicate event/transmission, and out-of-order refund/capture events. Confirm unverified input causes no payment mutation and retries remain idempotent.

## Gotchas

The webhook ID is assigned to the listener subscription; it is not the PayPal client ID and is not supplied as a trusted body field. Certificate verification establishes message authenticity, not that the event is new or that a payment is finally settled. Preserve raw evidence under access controls for incident replay.

## Sources

- PayPal Developer, [Integrate webhooks — message verification](https://developer.paypal.com/api/rest/webhooks/rest/)
- PayPal Developer, [Verify webhook signature API](https://developer.paypal.com/docs/api/webhooks/v1/#verify-webhook-signature)
- PayPal Developer, [Webhook simulator](https://developer.paypal.com/api/rest/webhooks/simulator/)
