# RFC 9420 MLS Epoch and Commit State Machine

**Issue:** Messaging Layer Security groups advance through ordered epochs. Applying proposals or commits out of order can fork group state and make members unable to decrypt or authenticate messages.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Persist group ID, epoch, transcript hashes, tree state, and pending proposals atomically.
- Accept one valid commit transition from the current epoch and reject stale or future application messages according to policy.
- Authenticate external joins and validate proposal/commit authorization before state mutation.
- Keep delivery-service ordering separate from MLS cryptographic validation; the service is not trusted to define group state.

## Verification

- Reorder, duplicate, delay, and replay proposals, commits, and application messages.
- Fork two commits from one epoch and verify deterministic conflict handling.
- Remove a member and confirm it cannot derive later epoch secrets.

## Gotchas

- MLS provides group cryptography, not user identity proof or delivery guarantees.
- Lost epoch state can require rejoin rather than reconstructing secrets from the server.

## Official sources

- https://www.rfc-editor.org/rfc/rfc9420.html
