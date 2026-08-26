# dns-caa-certificate-issuance-policy

**Issue:** A domain has no explicit policy restricting which certificate authorities may issue certificates for it.
**Date:** 2026-08-11
**Author:** ORCHORDS
**Status:** documented

## Root cause

Certificate issuance is an external trust boundary. DNS Certification Authority Authorization (CAA) records let a domain authorize certificate issuers and optionally receive incident reports, but they must cover normal and wildcard issuance and be kept aligned with the actual CA/automation estate.

**Source:** [RFC 8659 — DNS Certification Authority Authorization](https://datatracker.ietf.org/doc/rfc8659/).

## Fix

- inventory every CA and automated issuance path used by the domain;
- publish narrowly scoped `issue` and `issuewild` authorization records;
- use `iodef` reporting only with an owned, monitored destination;
- review CAA changes with DNS, certificate, and deployment owners;
- test issuance and renewal in a non-production name before tightening production policy;
- include CAA in incident response for unexpected certificate issuance.

## Verification

- An authorized CA can renew the intended certificate.
- An unauthorized CA issuance attempt is refused.
- Wildcard issuance follows its explicit policy.
- CAA records and actual certificate inventory agree.

## Related

- the mTLS sections in this file
- `infra/dns-ttl-strategy.md`
