# Fetch Metadata Resource Isolation Policy

**Issue:** Cookie-authenticated endpoints can receive cross-site requests that look syntactically valid. Fetch Metadata headers provide server-side context for rejecting requests not initiated by the application.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- For state-changing and sensitive endpoints, reject requests with Sec-Fetch-Site: cross-site unless the route is an explicit cross-site integration.
- Allow same-origin and same-site according to the application trust model; do not assume every sibling subdomain is trusted.
- For top-level safe navigations, require Sec-Fetch-Mode: navigate and an allowed method.
- Maintain an explicit exception inventory for CORS APIs, webhooks, and embeds; layer CSRF tokens and Origin validation where applicable.

## Verification

- Exercise same-origin, same-site, cross-site, missing-header, and direct-navigation cases.
- Test old-client behavior intentionally; missing headers must follow a documented fallback.
- Verify CDN or proxy layers preserve Sec-Fetch-* values.

## Gotchas

- Fetch Metadata is defense in depth, not a replacement for authorization or CSRF protection.
- Never trust a client-supplied substitute header.

## Official sources

- https://www.w3.org/TR/fetch-metadata/
- https://web.dev/articles/fetch-metadata
