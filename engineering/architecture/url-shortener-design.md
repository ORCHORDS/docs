# url-shortener-design

**Issue:** Long URLs are unwieldy for sharing and analytics is impossible without a redirect layer
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A marketing team needs trackable short links that redirect to campaign landing pages and survive high-volume social media traffic spikes.

## Pattern / Solution
Generate a unique short code (base-62 encoding of a counter or hash). Store the mapping in a database with the original URL. Redirect via HTTP 301 (cacheable) or 302 (trackable). Cache hot short codes at the edge. Log redirect events for analytics.

## Gotchas
301 redirects are cached by browsers, making click tracking impossible. Use 302 for tracking or a hybrid approach. Custom domains require wildcard TLS and per-tenant routing. Short codes must be collision-free if generated randomly.

## Related
cache-aside-pattern, rate-limiting-architecture, cdn-architecture
