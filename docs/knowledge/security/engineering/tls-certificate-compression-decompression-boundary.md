# TLS certificate-compression decompression boundary

**Issue:** RFC 8879 reduces TLS certificate-chain bytes by replacing a Certificate message with CompressedCertificate after negotiation. The receiver is now parsing attacker-controlled compressed input before certificate validation, so algorithm confusion, decompression expansion, length mismatch, and middlebox incompatibility become handshake security and availability risks.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Enable certificate compression only for TLS 1.3 or later and only after the peer advertises supported algorithms.
- Accept only the exact algorithm selected from the peer’s `compress_certificate` list; reject unknown, unadvertised, or disabled algorithms.
- Enforce a local maximum uncompressed Certificate size before allocation and never exceed the protocol’s stated `uncompressed_length`.
- Stream or otherwise bound decompression memory and CPU; abort if output exceeds the limit, decompression fails, trailing data violates the implementation contract, or actual length differs.
- Process the decompressed Certificate message through the identical parser, chain building, signature, name, validity, revocation, policy, and authorization checks used without compression.
- Rate-limit handshake failures and expose algorithm, compressed size, declared size, actual size, alert, and timing without logging certificate secrets unnecessarily.
- Maintain a rapid disable switch per client population for middlebox failures.

## Implementation and tests

Negotiate each supported algorithm and compare the decompressed encoded Certificate structure byte-for-byte with an uncompressed handshake fixture. Test unsupported and unadvertised algorithms, zero or oversized lengths, output one byte below and above the declaration, corrupt streams, maximal valid chains, repeated compression bombs, client certificates, session resumption, and TLS 1.2 rejection.

Run interoperability and packet-loss tests through representative enterprise TLS inspection, mobile, proxy, and load-balancer paths. Confirm malformed messages terminate with the required certificate error and do not reach ordinary certificate parsing.

## Gotchas

Compression does not weaken or replace normal certificate verification. TLS 1.3 encrypts the Certificate message, but on-wire lengths can still reveal information and compression changes that signal. RFC 8879 permits lower local size limits if they match the uncompressed path.

The RFC Editor lists reported errata concerning encoded-structure length and transcript wording as of 2026-08-18; reported errata are not silently normative. Review their current status and library behavior during implementation.

## Official sources

- [RFC 8879: TLS Certificate Compression](https://www.rfc-editor.org/rfc/rfc8879.html)
- [RFC Editor: RFC 8879 status and errata](https://www.rfc-editor.org/info/rfc8879/)
