# FedCM Login Status API state minimization

**Issue:** The Federated Credential Management Login Status API lets an identity provider communicate login state to the browser. It is a privacy-sensitive hint, not proof of the application's local session or authorization.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Feature-detect; expose only coarse logged-in/logged-out state; update after authoritative IdP transitions; keep RP authorization independent and provide non-FedCM recovery.

## Verification

Test stale state, multi-account logout, revoked sessions, unsupported browsers, blocked third-party context, and disagreement between IdP and RP state.

## Gotchas

FedCM specifications remain evolving. Login status must not leak account identity or replace token validation, logout propagation, or session expiry.

## Official sources

- https://w3c-fedid.github.io/FedCM/
