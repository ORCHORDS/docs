# Node.js system CA rollout

**Issue**

Using the operating-system CA store changes TLS trust from Node's bundled roots to mutable host policy.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Enable system CAs only on governed images.
- Inventory added enterprise roots and preserve hostname verification.
- Canary package, API, proxy, and revocation behavior.

## Verification

1. Connect to public, enterprise, expired, wrong-host, and untrusted certificates.
2. Rotate a managed root.
3. Compare hosts in the same runner pool.

## Gotchas

- Host trust drift changes Node behavior.
- A trusted root can issue for many names.
- System stores differ by OS.

## Official source

- [Official documentation](https://nodejs.org/api/cli.html#--use-system-ca)
