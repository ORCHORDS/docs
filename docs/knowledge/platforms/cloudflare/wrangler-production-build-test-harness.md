# Wrangler production-build test harness

**Issue:** Wrangler's 2026 `createTestHarness()` runs integration tests against a Worker built by Wrangler or the Cloudflare Vite plugin. It complements workerd-unit tests by exercising the production build graph, multi-Worker routing, outbound mocks, storage reset, and runtime logs.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Keep fast isolated tests in the Workers Vitest pool; add harness tests for bundling, routing, service bindings, and browser-visible integration.
- Build once per suite, reset mutable storage between cases, mock external network calls explicitly, and close the harness in teardown.
- Pin Wrangler and make the harness configuration derive from the deploy configuration.

## Verification

1. Assert two Workers route through the intended service binding.
2. Prove an outbound request is intercepted rather than reaching the network.
3. Verify storage reset and teardown after success, failure, and cancellation.
4. Run at least one Playwright smoke against the harness endpoint.

## Gotchas

A local harness is not proof of Cloudflare account configuration or production bindings. Do not inject production secrets into it, and do not replace post-deploy smoke tests.

## Official sources

- https://developers.cloudflare.com/changelog/
- https://developers.cloudflare.com/workers/wrangler/api/
