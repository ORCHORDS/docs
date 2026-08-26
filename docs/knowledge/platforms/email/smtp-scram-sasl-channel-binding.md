# SMTP SCRAM SASL and channel binding

**Issue:** SMTP submission uses reusable cleartext-equivalent passwords or implements SCRAM without validating server proof, downgrade policy, and channel binding.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** standards-defined; server/client support varies

SCRAM SASL mechanisms provide salted challenge-response authentication; SCRAM-SHA-256 and its PLUS variant are defined by RFC 7677. Use after protected capability negotiation and verify the complete exchange.

**Sources:** [RFC 7677: SCRAM-SHA-256](https://www.rfc-editor.org/rfc/rfc7677) · [RFC 4422: SASL](https://www.rfc-editor.org/rfc/rfc4422)

## Controls

- require TLS and re-EHLO before selecting AUTH;
- prefer SCRAM-SHA-256-PLUS when valid channel binding is available;
- verify nonce, iteration bounds, server signature, and channel binding;
- use a maintained SASL implementation;
- never log credentials, proofs, or auth frames;
- rate-limit failures and prevent silent downgrade.

## Verification

Test valid exchange, wrong password, nonce reuse, low/extreme iteration count, invalid server proof, TLS change, PLUS/non-PLUS downgrade, cancellation, and reconnect.

## Gotchas

SCRAM protects the authentication exchange, not message content. Mechanism advertisement can differ after TLS. Channel binding must use the protocol-defined binding data exactly.
