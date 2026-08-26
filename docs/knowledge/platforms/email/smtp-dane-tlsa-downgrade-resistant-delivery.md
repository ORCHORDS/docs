# SMTP DANE TLSA for downgrade-resistant delivery

**Issue:** Opportunistic SMTP STARTTLS can be stripped, and ordinary certificate checks cannot safely authenticate an MX target learned through unsigned DNS.
**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

- Enable DNSSEC from the organizational domain through every MX and TLSA owner name; a TLSA record without a validated DNSSEC chain is not authenticated policy.
- Publish TLSA at `_25._tcp.<mx-host>`, not at the recipient domain. Prefer well-supported DANE-EE or DANE-TA usages and document the exact selector and matching type.
- Roll keys safely: publish a TLSA record matching the new certificate or public key, wait for DNS TTLs, deploy the certificate, then retire the old TLSA only after another full TTL.
- Configure sending MTAs to distinguish secure, insecure, bogus, and indeterminate DNSSEC results. Never silently treat bogus or indeterminate as an unsigned destination.
- Alert on DNSSEC validation failures, unusable TLSA sets, STARTTLS absence, certificate mismatch, and queues blocked by authenticated-delivery policy.

## Verification

1. Query MX, A/AAAA, and TLSA through a validating resolver and require the authenticated-data result.
2. Test every MX preference and address family; a neglected backup MX can become the downgrade path.
3. Negotiate STARTTLS and independently match the presented chain/key against each usable TLSA association.
4. Rehearse a certificate rotation with overlapping records and prove queued mail succeeds throughout.
5. Inject bogus DNSSEC and mismatched-certificate cases in staging; assert defer/queue behavior rather than cleartext fallback when DANE applies.

## Gotchas

DANE is not merely “a TLSA record.” Its assurance depends on DNSSEC validation and correct MX indirection handling. Cached negative answers and split-horizon DNS can make a valid deployment appear absent. Do not copy HTTPS TLSA assumptions: SMTP reference identifiers, MX discovery, and DANE-EE name checks have protocol-specific rules.

## Sources

- [RFC 7672: SMTP Security via Opportunistic DANE TLS](https://www.rfc-editor.org/rfc/rfc7672.html)
- [RFC 6698: The TLSA DNS Resource Record](https://www.rfc-editor.org/rfc/rfc6698.html)
