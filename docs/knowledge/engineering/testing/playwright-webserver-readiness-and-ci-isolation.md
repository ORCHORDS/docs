# Playwright webServer readiness and CI isolation

**Issue:** Browser suites can attach to the wrong local process or begin before the application is actually ready.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Configure `webServer.url` as a readiness endpoint and use `reuseExistingServer: !process.env.CI`: local development may reuse a server, while CI must fail on a conflicting listener and launch the intended revision. Use explicit timeouts, pipe stderr, and configure multiple named servers when frontend and API lifecycles differ. The readiness route should reflect required dependencies without mutating state. Use `baseURL` for consistent navigation, but never treat an arbitrary open port as application readiness.

## Verification

In CI, occupy the expected port and verify the run fails; then verify delayed startup is awaited and startup failure surfaces server stderr. Confirm the server is terminated after pass, fail, and cancellation paths.

## Gotchas

- Confirm behavior against the exact deployed version; feature state and defaults can change.
- Preserve logs and artifacts needed to reproduce failures without recording secrets or personal data.
- Roll out behind a reversible change and define the rollback trigger before production use.

## Official source

- [Primary documentation](https://playwright.dev/docs/test-webserver)
