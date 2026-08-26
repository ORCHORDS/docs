# SMTP REQUIRETLS Delivery Policy

**Issue:** Ordinary SMTP STARTTLS is opportunistic: delivery can continue without authenticated encryption, which is unsuitable for messages whose sender requires protected relay.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Use RFC 8689 REQUIRETLS only through an MTA that implements the complete sender and relay semantics. Before sending `MAIL FROM ... REQUIRETLS`, establish TLS, authenticate the peer through the required PKIX or DANE path, validate MX identity through DNSSEC or MTA-STS as applicable, and confirm the peer advertises REQUIRETLS after STARTTLS.

Tag the message so every supporting onward relay preserves the requirement. If a next hop cannot meet it, generate the specified non-delivery response rather than silently downgrading. Protect bounce handling because non-delivery messages can expose original headers; verify the return path can receive REQUIRETLS.

Keep `TLS-Required: No` semantically separate: it requests delivery despite recipient TLS policy failure and is not a way to request encryption. Restrict who may set either policy and log the effective policy without message content.

## Verification

Build an interoperability matrix for supported/unsupported REQUIRETLS peers, valid/expired/mismatched certificates, MTA-STS and DANE outcomes, STARTTLS stripping, forwarding, mailing lists, aliases, and bounce return. Confirm required messages fail closed with useful status codes and ordinary mail remains unaffected.

## Gotchas

A header alone cannot make non-supporting relays enforce TLS. REQUIRETLS can reduce deliverability, so apply it from a classified policy and monitor non-delivery rates. Do not describe transport TLS as end-to-end content encryption.

## Sources

- [RFC 8689: SMTP Require TLS Option](https://www.rfc-editor.org/rfc/rfc8689.html)
- [RFC 8461: SMTP MTA Strict Transport Security](https://www.rfc-editor.org/rfc/rfc8461.html)
- [RFC 7672: SMTP Security via DANE](https://www.rfc-editor.org/rfc/rfc7672.html)
