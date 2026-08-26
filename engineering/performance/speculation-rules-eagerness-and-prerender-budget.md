# Speculation Rules Eagerness and Prerender Budget

**Issue:** Aggressive prerendering can consume bandwidth, CPU, memory, analytics events, and server capacity for pages the user never visits.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Start with prefetch and conservative eagerness for a small allowlist of high-confidence, safe GET navigations. Promote to prerender only when field evidence shows high navigation probability and meaningful latency benefit. Exclude logout, mutations, personalized one-time links, large downloads, and URLs whose rendering triggers irreversible work.

Treat speculation as a hint; correctness must not depend on execution. Defer analytics, impression counting, media playback, permission prompts, and side effects until activation. Ensure authenticated content has correct cache isolation and that server capacity accounts for speculative traffic. Cross-origin same-site prerender requires target opt-in; cross-site prerender is not available.

## Verification

Measure activation rate, unused speculation bytes, server requests, memory, LCP, and error rate by rule/eagerness. Test slow networks, data saver, memory pressure, authentication changes, CSRF defenses, redirects, cache headers, and browser refusal. Confirm prerendered documents do not emit impressions or mutate state before activation and that ordinary navigation remains correct.

## Gotchas

A prerender costs roughly a hidden page render and can be discarded. Browser heuristics may ignore rules. Prefetch and prerender have different risk/cost profiles; a fast demo does not justify broad URL matching.

## Sources

- [MDN Speculation Rules API](https://developer.mozilla.org/en-US/docs/Web/API/Speculation_Rules_API)
- [WICG Speculation Rules specification](https://wicg.github.io/nav-speculation/speculation-rules.html)
- [HTML prerendering](https://html.spec.whatwg.org/multipage/speculative-loading.html)
