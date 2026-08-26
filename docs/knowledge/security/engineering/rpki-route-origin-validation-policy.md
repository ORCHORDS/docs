# RPKI Route-Origin Validation Policy

**Issue:** BGP routes may be Valid, Invalid, or NotFound under Route Origin Validation. Treating NotFound as Invalid or accepting Invalid routes without policy undermines routing security.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Fetch and validate RPKI data through redundant, monitored validator paths.
- Apply explicit policy to Valid, Invalid, and NotFound states; prefer Valid and reject or strongly de-preference Invalid.
- Monitor ROA expiry, maxLength, ASN changes, and publication lag before routing changes.
- Keep emergency rollback and out-of-band reachability for mistaken ROAs.

## Verification

- Announce valid, invalid-origin, invalid-length, and uncovered test prefixes.
- Withdraw or expire ROAs and observe convergence.
- Lose one validator and confirm bounded stale-data behavior.

## Gotchas

- RPKI validates origin authorization, not the full AS path.
- A bad ROA can cause self-inflicted reachability loss.

## Official sources

- https://www.rfc-editor.org/rfc/rfc6811.html
- https://rpki.readthedocs.io/
