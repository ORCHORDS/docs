# Account for ACME STAR Renewal and Termination Windows

**Issue:** Short-Term Automatically Renewed certificates reduce reliance on revocation, but cancellation is not instant once the next certificate has already been published.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Discover CA STAR limits and record start, end, lifetime, adjustment, fetch mode, and order identity.
- Poll the certificate URL before the current certificate's replacement deadline.
- Protect the ACME account and cancellation path separately from certificate consumers.
- Model termination exposure through expiry of every already published certificate.
- Bound caching of the dynamic certificate resource and monitor publication availability.

## Verification

- Exercise bootstrap, renewal, clock skew, missed polling, cancellation before and after next publication, and order expiry.
- Confirm no certificate exceeds the order end date.
- Measure delegation termination to last-certificate expiry.

## Gotchas

STAR commonly reuses the CSR public key across renewals. Short validity is an operational control, not immediate revocation.

## Official sources

- [RFC 8739](https://www.rfc-editor.org/rfc/rfc8739.html)
