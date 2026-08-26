# SMTP DELIVERBY Deadline Semantics

**Issue:** Time-sensitive mail is queued with an application deadline, but downstream MTAs do not know when a late delivery becomes useless; teams also mistake DELIVERBY for guaranteed or priority delivery.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Use the RFC 2852 `DELIVERBY` extension only after the receiving server advertises it. Express the remaining deadline as the `BY` parameter on MAIL FROM and choose the mode explicitly: notify when the deadline passes or return the message. Recompute remaining delta time at every supporting relay. If a required return mode cannot be preserved by the next hop, fail or select another route rather than silently discarding the contract.

Keep the product deadline separately from SMTP queue retention. Define a fallback for unsupported peers: reject before submission, send without a transport deadline, or use an application channel. Make this a per-message policy decision. Capture capability, requested delta, mode, relay decision, and terminal DSN without storing content.

## Verification

Test unsupported peers, the advertised minimum return time, positive/zero/expired deltas where allowed, queue delay, relay to a supporting and non-supporting hop, clock skew, DSN generation, and retry near expiry. Verify the delta decreases across relays and that an expired message is never presented as on-time.

## Gotchas

DELIVERBY is not a scheduling or priority command and does not guarantee inbox placement. Its delta does not extend the MTA's ordinary retention period. Support is not universal. A product should not depend on it as the sole expiry control for password codes, payments, or emergency notices.

## Sources

- [IETF RFC 2852 — Deliver By SMTP Service Extension](https://datatracker.ietf.org/doc/html/rfc2852)
- [IETF RFC 3461 — Delivery Status Notifications](https://datatracker.ietf.org/doc/html/rfc3461)
