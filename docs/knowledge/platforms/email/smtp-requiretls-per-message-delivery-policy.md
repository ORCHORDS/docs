# SMTP REQUIRETLS Per-Message Delivery Policy

**Issue:** Opportunistic STARTTLS prioritizes delivery and can silently fall back when TLS negotiation or authentication fails. Sensitive transactional mail may require a per-message guarantee, while indiscriminate enforcement can also cause lost delivery and lost bounces.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

- Use RFC 8689 REQUIRETLS only through MTAs that implement its end-to-end relay semantics; a TLS connection on the first hop alone is insufficient.
- Before adding the `REQUIRETLS` MAIL FROM parameter, require TLS on the active session, authenticate the receiving server certificate, validate the MX through DNSSEC or MTA-STS, and confirm REQUIRETLS is advertised again after STARTTLS.
- Persist the message's TLS-required state across queues, aliases, retries, redistribution, and onward relay.
- Fail closed with an explicit enhanced status when the next hop cannot honor REQUIRETLS. Surface the non-delivery reason to the sending application without silently downgrading.
- Protect resulting non-delivery messages with the same requirement and redact message content as required by RFC 8689.
- Gate use by message classification and recipient-domain capability. Keep ordinary mail on the normal policy unless the business requirement justifies possible non-delivery.
- Treat `TLS-Required: No` as a distinct delivery-availability request; do not confuse it with the REQUIRETLS service extension.

## Verification

1. Exercise a capable hop, a hop without REQUIRETLS, certificate failure, invalid MTA-STS/DNSSEC identity, STARTTLS stripping, relay forwarding, and bounce generation.
2. Confirm the queue never retries a required message without its flag.
3. Confirm errors 5.7.30 and 5.7.10 are observable and mapped to useful operator diagnostics.
4. Verify the receiving domain can also accept REQUIRETLS-protected bounces before enabling it for critical traffic.

## Gotchas

- Adding a header does not substitute for the SMTP extension when requiring TLS.
- All relays in the path need appropriate support; partial rollout is not an end-to-end guarantee.
- A policy intended to improve confidentiality can reduce availability.

## Sources

- [RFC 8689 — SMTP Require TLS Option](https://www.rfc-editor.org/rfc/rfc8689.html)
