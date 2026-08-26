# Network Information adaptive-loading signal, not policy

**Issue:** A site blocks video, upgrades, or core functionality whenever navigator.connection reports a slow effectiveType. The estimate is missing, rounded, stale, or changes after navigation, so users on capable networks receive a permanent low-quality experience while other browsers take an untested code path.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** limited availability; optional hint only

## Problem and applicability

The Network Information API can expose connection observations such as effectiveType, downlink, round-trip time, type, and change events where supported. Values are user-agent estimates with privacy reduction and are not a measurement of the exact origin request currently in flight.

Use them to choose a reversible initial strategy for optional bytes. Never use them for authorization, billing, eligibility, safety, or permanent feature denial.

## Controls and implementation

1. Feature-detect navigator.connection and every property consumed. Keep a tested default path when the interface or field is absent.
2. Treat effectiveType, downlink, and rtt as coarse, mutable hints. Do not combine them into a precise bandwidth claim or expose them as fact to the user.
3. Adapt only discretionary work: defer a preview, choose a smaller initial image, reduce speculative prefetch, or ask before a large download.
4. Preserve a visible override for higher quality or immediate loading, remember it at an appropriate product scope, and never downgrade user-requested content silently after interaction.
5. Re-evaluate on a bounded connection change handler. Coalesce bursts, compare the current generation, and avoid cancel/restart loops that waste more bytes than they save.
6. Prefer direct application evidence after startup: observed Resource Timing, transfer completion, buffer health, and server responses. Apply hysteresis before changing quality.
7. Do not send raw network estimates to analytics by default. If operationally necessary, bucket and sample them, document retention, and avoid joining them into a fingerprint.
8. Build server and CDN selection around explicit asset variants and cache-safe URLs. A client hint must not create unbounded cache variants or inconsistent content.

## Verification

Test API absent, every documented effective type, zero/unknown/rounded values, rapid changes, offline transition, Wi-Fi with poor upstream, cellular with good throughput, VPN, data saver implemented outside this API, user override, background tab, and privacy-restricted browser.

Simulate incorrect hints and assert the application remains complete and recoverable. Compare initial hint decisions with later observed transfers without claiming they should always match.

## Gotchas

- effectiveType describes an estimated effective class, not necessarily the physical radio type.
- downlink and rtt can be rounded or privacy-reduced.
- A change event does not mean every existing connection changed immediately.
- Browser support is uneven, so the no-API path is a first-class product path.

## Official sources

- [WICG — Network Information API](https://wicg.github.io/netinfo/)
- [W3C TAG — Self-Review Questionnaire: Security and Privacy](https://www.w3.org/TR/security-privacy-questionnaire/)
