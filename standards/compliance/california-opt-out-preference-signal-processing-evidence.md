# California Opt-Out Preference Signal Processing Evidence

**Issue:** A business can expose a manual opt-out while failing to detect or consistently honor browser-based opt-out preference signals across domains, devices, and downstream recipients.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Determine CCPA/CPRA applicability and the precise obligations for the business with qualified counsel.
- Detect recognized opt-out preference signals at the request boundary and apply them without requiring account creation.
- Bind the result to known consumer identity where permitted and propagate the opt-out to systems and third parties covered by the request.
- Retain privacy-preserving evidence of signal receipt, interpretation, downstream propagation, and exceptions.

## Verification

- Send Global Privacy Control from supported browsers on authenticated and anonymous journeys.
- Verify sale/sharing controls across web, mobile web, subdomains, and tag-management integrations.
- Confirm downstream recipients stop covered processing and that later consent changes follow the required flow.

## Gotchas

- Do Not Track and Global Privacy Control are not interchangeable signals.
- A banner acknowledgment is not proof that advertising or data-sharing systems honored the signal.

## Official sources

- https://cppa.ca.gov/regulations/
- https://oag.ca.gov/privacy/ccpa
