# browser-automation-wait-strategies

**Issue:** Browser end-to-end tests fail intermittently because scripts interact with the page before it is ready, and teams respond by sprinkling arbitrary sleep statements that make suites slow without removing the flakiness. Modern automation frameworks such as Playwright solve this with built-in actionability checks and auto-retrying web-first assertions, but the guarantees only hold when tests are written to cooperate with them. Understanding which waits are automatic, which conditions are not covered (for example network idle or data loaded into the DOM), and when an explicit wait is legitimate is the difference between a suite that is trustworthy and one that gets retried until it is meaningless.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Core waiting model

1. **Actionability checks are automatic.** Before performing a click, fill, or check, the framework waits for the element to be visible, stable (not animating or moving), enabled, editable where relevant, and able to receive events (not obscured by an overlay). Tests should rely on this instead of preceding every action with a visibility probe; writing a manual wait-then-act sequence reintroduces the race the framework already handles.
2. **Web-first assertions retry.** An assertion such as expect(locator).toBeVisible() polls the DOM until the condition holds or the timeout expires, which tolerates asynchronous rendering. Extracting the value first (element.textContent()) and asserting on the raw string bypasses the retry loop and turns any late update into a hard failure. Always assert through the locator, not through a snapshot of it.
3. **Locators re-resolve on every action.** A locator is a query, not a handle to a stale node. Chaining locator.click() re-queries the DOM at action time, so a re-render between finding and acting is safe. Storing element handles across awaits defeats this and is a leading cause of detached-node errors.
4. **Navigation and load states are distinct waits.** Waiting for a load event or a URL change is a different mechanism from element actionability; a page can be "loaded" while its data is still in flight. Know which one the test actually needs before adding explicit waits.

## What auto-waiting does not cover

1. **Application-level data readiness.** The framework can see the DOM, not the intent behind it. A skeleton row that exists but is populated a second later passes a bare existence check, so tests must assert on content, not presence, once async data lands.
2. **Network quiet heuristics.** Waiting for network idle is fragile with analytics, websockets, long-polling, and third-party beacons that never go quiet. Prefer asserting on the observable effect of the request (the rendered result) over inferring readiness from network silence.
3. **Cross-page and cross-tab handoffs.** Redirect chains, popup windows, and OAuth-style hops involve contexts the original page object does not automatically wait on; tests must explicitly wait for the target page or URL within the new context.
4. **Non-DOM side effects.** A database write, job enqueue, or downstream API call triggered by a UI action is invisible to the browser; verify it through the system under test's API or database rather than waiting hopefully for UI symptoms.

## Explicit waits done right

1. **Wait for a condition, never a duration.** When an explicit wait is genuinely needed, express it as the awaited state: a specific URL, a response with a given status, a text appearing in a known element. A fixed waitForTimeout is a confession that the real condition was never identified, and it is both slow and wrong at the margin.
2. **Wait on scoped web-first conditions.** expect(locator).toHaveCount(n) or toContainText() bound the wait to a locator and timeout, integrate with traces, and fail with readable diffs, which raw polling loops do not.
3. **Use route interception to make waits deterministic.** Intercepting the specific API call a view depends on and asserting or faking its response converts an unpredictable timing window into an event the test can await directly.
4. **Bound every wait explicitly.** Default timeouts mask slow paths; setting a per-assertion timeout that matches the expected worst case makes genuine regressions fail fast instead of consuming the whole budget.

## Diagnosing wait-related flakiness

1. **Run with traces retained on failure.** Configuring trace: retain-on-failure and inspecting the trace viewer shows the exact actionability step that stalled, the DOM snapshot at failure, and network timing, which is almost always enough to identify the missing condition.
2. **Reproduce with artificial slowdown.** Throttling the CPU or network (or delaying a mocked response by a fixed amount) turns a rare race into a deterministic reproduction; if a test fails only under throttle, it is racing, not bugged.
3. **Grep the suite for sleep calls.** A periodic audit for fixed-duration waits finds new additions before they become load-bearing; CI can fail the build on any waitForTimeout introduced in a diff.
4. **Treat retries as a last resort, not a fix.** Retrying a racy test makes it pass while leaving the race in place; fix the wait condition first, and reserve retries for genuinely environmental flakes with a tracked quota.

## Checklist for new tests

1. **Every assertion goes through a locator-based web-first API.** No raw property reads followed by plain expects.
2. **No fixed-duration sleeps.** Any sleep in a diff requires justification in review.
3. **Async data is asserted by content.** Wait for the loaded value to render, not for a container to exist.
4. **Timeouts are explicit where the default is wrong.** Slow views get a named, commented timeout; everything else uses the sane default.
5. **Failures produce a trace or video.** Evidence capture is configured once at the project level so diagnosing a flake never requires reproducing it by hand.
