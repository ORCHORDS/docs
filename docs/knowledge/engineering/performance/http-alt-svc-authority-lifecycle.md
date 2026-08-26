# HTTP Alternative Services authority lifecycle

**Issue:** A client or edge advertises an alternative service for lower latency, but stale mappings, certificate mistakes, or cross-host routing create outages or privacy leaks.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

RFC 7838 Alt-Svc lets an origin advertise an alternative host/protocol while retaining the original origin's authority. Cache the mapping with its lifetime and validate the alternative connection for the original origin.

**Source:** [RFC 7838: HTTP Alternative Services](https://www.rfc-editor.org/rfc/rfc7838)

## Controls

- emit only alternatives that can authenticate and serve the origin;
- choose bounded `ma` lifetimes and support explicit clearing;
- preserve Host/:authority and origin-scoped cookies/cache;
- partition or suppress mappings where privacy policy requires;
- roll out by cohort and monitor fallback to the origin;
- coordinate Alt-Svc with HTTP/3 and load-balancer routing changes.

## Verification

Test valid/expired/cleared mappings, alternative outage, certificate mismatch, DNS change, proxy stripping, cached mapping after rollback, multiple alternatives, and fallback latency. Confirm the alternative never changes web origin semantics.

## Gotchas

Alt-Svc is not an HTTP redirect and must not change the URL shown to users. Long lifetimes make mistakes sticky. Advertising a distinct host can reveal origin relationships or client traffic.
