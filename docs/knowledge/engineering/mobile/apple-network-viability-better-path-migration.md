# Apple Network viability and better-path migration

**Issue:** An app tears down a working connection whenever a better network appears, or treats a viable path signal as proof that its service request will succeed.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

Apple Network framework connections can report viability and availability of a better path. Use these signals to schedule a controlled reconnect/migration, while keeping application acknowledgements and idempotency authoritative.

**Source:** [Apple Network framework](https://developer.apple.com/documentation/network)

## Controls

- serialize connection-state transitions;
- migrate only at a safe protocol boundary;
- use exponential backoff with jitter after failure;
- preserve operation IDs across path changes;
- avoid duplicate active sessions and close superseded paths;
- respect expensive/constrained network policy.

## Verification

Test Wi-Fi/cellular handoff, captive portal, VPN, loss/recovery, better-path flapping, in-flight upload, backgrounding, duplicate callbacks, and server restart. Unknown outcomes must reconcile before replay.

## Gotchas

Viable does not mean the application service is reachable. Better does not mean free, trusted, or stable. Path callbacks can race with connection completion.
