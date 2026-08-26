# Playwright Retries Must Preserve Browser Errors

Date: 2026-08-26
Author: example.com
Status: production

---

## Symptom / Use-case

A production Playwright verifier uses bounded retries for transient navigation failures. A first navigation attempt can fail with a missing main-document response or a narrowly classified browser/network transient, then a fresh-page retry can succeed.

The dangerous failure mode is letting console errors or uncaught `pageerror` events from the first attempt become mere retry diagnostics. That turns a hard browser correctness assertion into informational text and weakens the verifier.

## Durable Rule

Retry eligibility and browser-runtime correctness are separate dimensions.

A route may receive a bounded retry only when **all** of the following are true:

1. The failure is explicitly classified as a retry-eligible navigation transient, or the navigation literally returned no main-document response.
2. The attempt emitted **zero** unexpected console errors.
3. The attempt emitted **zero** uncaught page errors.
4. No HTTP response at or above the configured failure threshold was observed.
5. The retry count has not been exhausted.

If a console error or uncaught page error occurs on any attempt, that route fails permanently. A later successful navigation must not erase or downgrade the earlier browser error.

## Recommended Decision Order

Evaluate retry/failure state in this order:

1. Browser errors (`console`, `pageerror`) -> fail permanently.
2. HTTP response status >= failure threshold -> fail permanently.
3. Successful HTTP response below threshold -> success after the post-navigation browser-error settle window is clean.
4. Explicitly classified transient or literal no-response -> retry only if retry budget remains.
5. Unclassified navigation exception -> fail permanently.
6. Repeated eligible transient after the bounded retry -> fail deterministically.

This ordering prevents a generic "no response" condition from accidentally making unrelated exceptions retryable.

## Fresh-Page Retry

When retrying, use a fresh page (or fresh context when stronger isolation is needed) so the retry does not inherit a corrupted navigation/execution context. Reattach all console and `pageerror` listeners before navigation.

Do not clear first-attempt browser errors and then treat the route as successful. The retry is allowed only if the first attempt was browser-error clean.

## Execution-Context Destruction

Page navigation destroys the old JavaScript execution context. Handles tied to the previous document become invalid when their frame navigates or the context is destroyed. Treat execution-context destruction as a navigation/lifecycle event that needs explicit evidence before classifying it as retryable. Do not broadly match generic error text.

## Certificate-Verifier Changes

Chromium can invalidate certificate-verification decisions when the certificate verifier changes configuration. Errors related to certificate-verifier changes should be diagnosed separately from application HTTP failures. They are not evidence that a locale route itself is missing or broken.

Do not add certificate errors to a retry allowlist merely because a later attempt succeeds. First prove from runner/browser evidence that the failure is environmental/transient and that no browser-runtime assertion was emitted.

## Required Tests for Retry Policy

At minimum, unit-test the decision helper for:

- eligible navigation transient + zero browser errors -> one retry allowed;
- literal no-response + zero browser errors -> one retry allowed;
- first-attempt console error -> permanent failure;
- first-attempt pageerror -> permanent failure;
- second-attempt console/pageerror -> permanent failure;
- HTTP >= failure threshold -> never retry;
- successful HTTP response with zero browser errors -> success;
- repeated eligible transient -> deterministic failure;
- unclassified navigation exception -> never retry.

## Anti-patterns

- Returning success after a fresh-page retry while embedding first-attempt console/pageerror text in a `recovered-after=` diagnostic.
- Retrying all `page.goto()` exceptions by default.
- Treating every missing response as equivalent to every thrown navigation error.
- Excluding flaky routes from the sitemap/public-route verifier.
- Lowering route coverage or suppressing browser errors to make a production proof green.
- Raising only the overall timeout when the real issue is verifier design or concurrency.

## Verification

A production proof should report, at minimum:

- exact deployed revision;
- exact canonical sitemap cardinality and unique URL set;
- all advertised routes attempted;
- every main-document response below the failure threshold;
- aggregate unexpected console errors = 0;
- aggregate uncaught page errors = 0;
- bounded retries used only for explicitly eligible navigation transients;
- deterministic failure when retry budget is exhausted.

## Sources

- Playwright BrowserContext / page lifecycle documentation: https://playwright.dev/docs/api/class-browsercontext
- Playwright JSHandle lifecycle documentation: https://playwright.dev/docs/api/class-jshandle
- Chromium CertVerifier source: https://chromium.googlesource.com/chromium/src/+/main/net/cert/cert_verifier.h
