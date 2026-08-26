# turnstile-test-keys-automation

**Issue:** Cloudflare Turnstile widgets block automated browser tests because solving a real challenge in CI is impossible, so teams end up disabling the widget in test builds — which means the captcha path (render, token, server validation, failure/retry) is never tested at all. Cloudflare ships official dummy sitekeys and secret keys for exactly this purpose (the famous `1x00000000000000000000AA` always passes, `2x00000000000000000000AB` always blocks, `3x00000000000000000000FF` forces the interactive challenge), letting full flows run in automation with a deterministic widget. The keys are swapped in via environment variables in test builds and must never leak into production.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The official dummy sitekeys and secrets

1. **`1x00000000000000000000AA` — always passes (visible).** The visible-mode widget renders and immediately issues a passing token with no interaction; this is the workhorse for E2E happy paths.
2. **`2x00000000000000000000AB` — always blocks (visible).** The visible widget always fails; use it to exercise the failure UI and the retry path.
3. **`1x000000000000000000000BB` / `2x000000000000000000000BB` — invisible pass/block pair.** Note the extra `0` in these (they are 23 chars before the suffix, vs 22 for the visible keys — easy to fat-finger); they let you test the `interactionless`/invisible widget mode both succeeding and failing.
4. **`3x00000000000000000000FF` — forces an interactive challenge.** The widget always shows the interactive challenge, so automation can test the "user must actually interact" branch and manual QA can see the challenge UX without seeding bots.
5. **Dummy secret keys.** Secret `1x0000000000000000000000000000000AA` always passes siteverify; `2x0000000000000000000000000000000AA` always fails it — the failing secret is how you test your server's rejection of an invalid token.
6. **Dummy keys are hostname-agnostic.** They work on any hostname including `localhost`, so local dev and CI (including Playwright's localhost origins) need no domain registration or key provisioning.

## Swapping keys via environment in test builds

1. **One injection point.** The widget reads `NEXT_PUBLIC_TURNSTILE_SITEKEY` (or equivalent) at render and the server reads `TURNSTILE_SECRET_KEY` at validation; CI sets the dummy pair in the environment so the same build code path runs with different keys.
2. **Pair sitekey and secret correctly.** A dummy sitekey must be validated against a dummy secret (the always-passing sitekey with the always-passing secret is the standard combo); mixing a dummy sitekey with the real secret produces a validation failure loop that looks like a backend bug.
3. **Fail the prod build on dummy keys.** Add a build-time assertion that production builds reject any key starting with `1x00000000000000000000`, `2x00000000000000000000`, or `3x00000000000000000000` — a test key reaching production disables bot protection entirely and Turnstile will not warn you.
4. **Keep real keys for staging.** Staging should run real keys with a low-friction mode (Turnstile's managed/non-interactive modes pass most humans automatically) so the real integration is exercised before release.

## What each key lets you test

1. **Happy path with `1x...AA`.** Full form submission → token attached → server siteverify succeeds → downstream action executes, with zero challenge solving.
2. **Failure path with `2x...AB` or the `2x...` secret.** Widget shows failure and/or siteverify rejects the token; assert the app surfaces a retry affordance instead of a dead end and never completes the protected action.
3. **Invisible mode with the `...BB` pair.** Renders no visible checkbox; assert no layout shift where the widget mounts and that the token callback still fires.
4. **Interactive challenge with `3x...FF`.** Assert the app tolerates the token arriving late (only after interaction) — catching code that assumed the token was available immediately at page load.

## CI, widget assertions, and visual testing

1. **E2E with dummy keys, no challenge solving.** This is Cloudflare's own documented approach for excluding Turnstile from E2E tests: configure the dummy keys, and Playwright/Cypress runs complete flows natively without third-party solvers or bypass toggles in application code.
2. **Assert presence, not pixels.** Assert the Turnstile container/iframe mounts (e.g. `[data-sitekey]` / the widget container selector) and that the token field populates, rather than diffing the widget's pixels — challenge visuals vary between runs and locales.
3. **Mask the widget region in visual regression.** In Percy/Playwright screenshot comparisons, mask the widget's bounding area so its non-deterministic rendering does not flake the suite; snapshot the surrounding layout instead.
4. **Monitor the real thing post-release.** Production uses real keys; watch the Turnstile analytics (solve rate, failed validations) as the live signal, since CI by design never exercises a genuine challenge.

## Sources

1. **Cloudflare — Test your Turnstile implementation.** Official dummy sitekey/secret table and testing guidance: https://developers.cloudflare.com/turnstile/troubleshooting/testing/
2. **Cloudflare — Excluding Turnstile from E2E tests.** Official tutorial on wiring dummy keys into automated suites: https://developers.cloudflare.com/turnstile/tutorials/excluding-turnstile-from-e2e-tests/
