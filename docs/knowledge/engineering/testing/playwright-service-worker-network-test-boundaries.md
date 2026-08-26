# Playwright service-worker network test boundaries

**Issue**

Browser network interception can miss requests owned by service workers, producing tests that claim an API was mocked while a worker served or issued the traffic.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Set `serviceWorkers: 'block'` for tests whose correctness depends on page routing and interception.
- Maintain a separate worker-enabled lane for offline, cache, push, and update behavior.
- Assert the controlling service worker state before network expectations.
- Use HAR and routing fixtures with explicit scope and teardown.

## Verification

1. Prove page routing observes requests with workers blocked.
2. In the worker lane, test install, activate, cache hit, offline restart, and version update.
3. Fail on unexpected real-origin traffic at the proxy or test server.

## Gotchas

- Blocking workers invalidates PWA behavior tests.
- Requests initiated by workers may not appear as page route events.
- Persisted browser profiles can retain registrations across tests.

## Official source

- [Official documentation](https://playwright.dev/docs/network#missing-network-events-and-service-workers)
