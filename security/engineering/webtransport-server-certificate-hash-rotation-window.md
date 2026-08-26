# WebTransport Server-Certificate Hash Rotation Window

**Issue:** WebTransport deployments using serverCertificateHashes can fail closed during certificate rotation if clients and servers do not overlap accepted hashes and certificate constraints.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Publish hashes for both current and next eligible certificates during a bounded overlap window.
- Generate certificates within WebTransport’s permitted validity and algorithm constraints.
- Bind hashes to the intended origin and deployment environment; never reuse a development hash in production.
- Retire old hashes only after client configuration propagation and server rollout are verified.

## Verification

- Connect during old-only, overlap, new-only, expired, and mismatched-certificate phases.
- Verify a valid TLS certificate with an unlisted hash is rejected when hash pinning is required.
- Exercise cached clients that retain the previous configuration.

## Gotchas

- Hash pinning transfers rotation responsibility to the application.
- serverCertificateHashes does not excuse normal origin and session authorization checks.

## Official sources

- https://www.w3.org/TR/webtransport/
