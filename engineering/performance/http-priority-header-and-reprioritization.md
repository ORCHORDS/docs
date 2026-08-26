# HTTP Priority Header and Reprioritization

**Issue:** Critical and incremental responses compete under HTTP/2 or HTTP/3 while teams assume request order, preload, or a priority hint guarantees server scheduling.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Use RFC 9218 priority signals only as measured scheduling inputs. The `Priority` field carries an end-to-end dictionary: urgency `u` ranges from 0 (highest) to 7 (lowest), and incremental `i` indicates whether progressive delivery is useful. HTTP/2 and HTTP/3 can additionally carry hop-specific `PRIORITY_UPDATE` frames.

Assign a small number of stable classes based on actual user-visible dependency. Preserve or deliberately rewrite signals at intermediaries, document that policy, and keep admission control/fairness independent of client input. Since a server is not required to honor the hint, resource discovery, caching, and payload size remain the primary controls.

## Verification

Capture H2/H3 traces for competing large and small, incremental and non-incremental responses. Compare LCP/INP and completion time with signals absent, honored, ignored, and rewritten by a CDN. Confirm cached responses remain valid when response priority depends on request properties and test reprioritization races.

## Gotchas

Priority is a preference, not acknowledgement or a delivery guarantee. Trusting arbitrary client urgency enables starvation. The HTTP field is end-to-end while update frames are hop-specific. Do not confuse RFC 9218 with HTML `fetchpriority`; they operate at related but distinct layers.

## Sources

- [IETF RFC 9218 — Extensible Prioritization Scheme for HTTP](https://datatracker.ietf.org/doc/html/rfc9218)
- [IANA HTTP Priority registry](https://www.iana.org/assignments/http-priority/)
