# WebAuthn largeBlob confidentiality boundary

**Issue:** The WebAuthn largeBlob extension stores opaque RP data with authenticator credentials but is not general secret storage.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls and implementation

Encrypt/authenticate application payloads, version format, limit size, handle unsupported/sync/conflict and account recovery.

## Tests

Wrong credential, corrupted blob, multi-device update, rollback, unsupported client.

## Gotchas

Availability and sync vary; possession of a credential does not make arbitrary blob content trustworthy.

## Official sources

- https://w3c.github.io/webauthn/#sctn-large-blob-extension
