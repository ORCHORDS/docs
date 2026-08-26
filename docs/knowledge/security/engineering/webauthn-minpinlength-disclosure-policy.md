# WebAuthn minPinLength disclosure policy

**Issue:** The minPinLength extension can disclose authenticator PIN-policy information to authorized relying parties and is not a universal password-strength signal.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls and implementation

Request only when needed, validate attestation/authenticator policy, minimize logging, handle unsupported results and avoid account fingerprinting.

## Tests

Unsupported authenticator, absent result, changed PIN policy, cross-RP request, log leakage.

## Gotchas

Reported minimum PIN length does not prove the current PIN strength or user verification event.

## Official sources

- https://w3c.github.io/webauthn/#sctn-minpinlength-extension
