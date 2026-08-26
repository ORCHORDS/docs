# Govern Argon2 Parameters, Versions, and Rehashing

**Issue:** Naming Argon2id without persisting its version, memory, time, parallelism, salt, and output parameters makes verification and future upgrades ambiguous.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls
- Store the complete encoded parameter set per password hash and use Argon2id for password hashing unless a reviewed profile requires otherwise.
- Benchmark memory and time cost on production-class authentication workers under concurrency and memory pressure.
- Set resource ceilings before parsing attacker-controlled encoded hashes.
- Rehash after successful authentication when the stored profile is below current policy.
- Generate unique salts with a cryptographic random source; keep any secret pepper separately managed.

## Verification
- Run RFC 9106 vectors and malformed-encoding tests.
- Load-test login and password-reset paths at peak concurrency.
- Exercise old-profile verification followed by atomic rehash.

## Gotchas
Higher memory per hash can become a denial-of-service multiplier. Argon2's version and parameters are part of the security result; a library default is not a durable policy.

## Official sources
- [RFC 9106](https://www.rfc-editor.org/rfc/rfc9106.html)
