# in-app-review-api-pitfalls

**Issue:** Both stores provide an official in-app review prompt — Google Play's In-App Review API and Apple's `requestReview` family — and both impose opaque, time-bound quotas and give almost no feedback about whether the dialog actually appeared. Teams ship "rate us" flows that silently never show, get rejected for policy violations they didn't know existed (incentivized ratings, custom star widgets, review-gating), or tank their rating by prompting at the wrong moment. This article covers the real 2025-2026 behavior of both APIs, how to test what cannot be seen, and the store policy traps around soliciting reviews.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Google Play In-App Review API behavior

1. **A time-bound quota you cannot query.** Play enforces an undocumented, roughly monthly per-user quota on how often the review dialog appears. Calling the API does not guarantee the dialog, and there is no API to check remaining quota — design assuming most calls after the first will do nothing visible.
2. **`launchReviewFlow` "succeeds" even when nothing shows.** The flow completes normally whether or not the dialog was displayed; the completion event is not a "dialog shown" signal. Never gate UX (e.g. reward, "thanks!" screen, one-time dialog dismissal) on the assumption the prompt appeared.
3. **No feedback about the user's action.** The API deliberately hides whether the user rated, dismissed, or interacted — there is no completion callback payload and no way to detect the star value. Any "did they rate?" logic must live server-side keyed to Play ratings, which is also delayed and aggregated.
4. **Quota is per-app-per-user and survives reinstalls.** Uninstall/reinstall does not reliably reset the quota (it is account- and device-linked), so "reinstall to see the prompt again" is not a valid manual test on production builds.
5. **Prompt only when the app is foreground and stable.** The dialog requires a visible activity and can be killed if your process dies mid-flow; launching it during navigation, ads, or payment flows also violates Play guidance on placement. Fire it after a completed, positive user moment (level finished, successful sync), never during onboarding.

## Apple requestReview behavior (UIKit, SwiftUI, StoreKit 2)

1. **~3 prompts per 365 days, system-decided.** `SKStoreReviewController.requestReview()` (UIKit), `requestReview(in:)` (SwiftUI), and the StoreKit 2 `requestReview` action all funnel to the same system service, which caps prompts at about three per rolling year per app and may simply decline to show — submitting the request is legal even when ignored, but the error/return only reflects the request, not display.
2. **Test appearance only via TestFlight or a debug workaround.** In debug/Xcode runs the prompt always shows (with limited function), which hides quota behavior; TestFlight builds never show the real dialog. The only faithful environment is a production-signed App Store build, where you get the real quota. Plan verification accordingly (see testing section).
3. **`StoreKit` requestReview error handling exists since iOS 16.4 — read it carefully.** The async/await variant can throw for request-level failures, but a successful call still does not confirm display. Do not log analytics "review_prompt_shown" on success; log "review_prompt_requested" and treat display as unknowable.
4. **iOS 18 system settings override.** Users can disable review prompts entirely (Settings > App Store > In-App Ratings & Reviews off), and the system suppresses prompts after app updates and during certain states (e.g. logout screens, car Play contexts per AppKit guidance). Assume a fixed percentage of users can never be prompted.
5. **Do not call it programmatically on launch or from background restoration.** Apple guidance: no prompts during first launch, immediately after launch, while a modal/payment flow is up, or during state restoration (`mobile-app-lifecycle-process-death.md` — restored sessions mid-review-prompt are a known crash-prone overlap). Prompt after a completed positive interaction.

## Policy traps that get apps rejected or pulled

1. **Incentivized reviews are prohibited on both stores.** Offering anything (coins, features, contest entry, "unlock by rating") in exchange for a rating or for a 5-star selection is a documented removal reason on Play and an App Store guideline 2.3 / 3.1 violation. This includes gates that change behavior based on whether the user opened the review flow.
2. **Review gating / conditional prompting is risky.** "Only ask users who say they love us" via a custom NPS-style widget, then deep-linking detractors nowhere (or to support) manipulates ratings. Apple allows internal surveys but rejects apps whose flow is designed to filter who reaches the store review; safest pattern is to survey everyone equally and offer the store prompt to everyone who engages.
3. **Custom star UIs that submit to the store are rejected.** Widgets that capture 1-5 stars in your own UI and then open the store review page (or call the API) misrepresent the system dialog. Custom surveys are fine; mimicking the native rating widget is not.
4. **Never use the private rating URL as a workaround.** Jumping to `https://play.google.com/store/apps/details?id=...&reviewId=0` or the App Store write-a-review URL to bypass the quota is allowed technically (plain links), but spamming it via repeated dialogs violates both stores' guidelines on harassment — and iOS blocks programmatic `SKStoreReviewController` substitutes from auto-opening the store sheet.
5. **Placement inside commerce flows is a violation magnet.** Prompts appearing during/around checkout, subscriptions, or ads are consistently flagged in review (both automated Play detection and App Review). Keep an allowlist of "safe moments" in code review — a single misplaced `requestReview()` call in a shared component is a common accidental rejection cause.

## Testing what you cannot see

1. **Android: use internal test tracks for repeatable prompts.** On internal-app-sharing / test-track builds the quota is relaxed and the debug overlay (`FakeReviewManager` via the Play Core `review-testing` artifact, or `ReviewManagerFactory` with `forceReviewManager` in debug builds) lets you verify the flow repeatedly; swap the fake for the real manager only in release via DI so production behavior is untouched.
2. **iOS: verify in a sandbox/production-signed build on a real device.** Debug builds always show the dialog (masking quota), TestFlight never does. Use a sandbox Apple ID / TestFlight-adjacent sandbox and expect real-quota behavior only in App Store-signed builds; budget one manual production verification per release train.
3. **Assert the request, not the display, in e2e.** UI tests (Detox/Maestro/XCUITest) should assert that tapping the trigger calls the API (mock/inject the manager — see `mobile-e2e-testing.md` on mocking native modules) and that the app remains functional if the dialog never appears. Testing the native dialog itself is out of scope and flaky by design.
4. **Instrument conservative analytics.** Log `review_requested` with trigger context (session count, last-prompt timestamp from server config), never `review_shown`. Combine with feature flags / remote config (see `mobile-feature-flags-remote-config.md`) so prompting cadence can be tuned or disabled post-launch without a release.
5. **Respect user-level frequency caps server-side.** Since both stores hide quota state, track last-request time per user on your backend (or in local storage with a server-issued override) and enforce your own minimum interval (e.g. 90+ days, max 2-3 per year). This protects rating conversion and avoids burning the store quota on moments users find annoying.

## Related

- `android-play-store-submission.md` / `ios-app-store-submission.md` — the review processes themselves
- `app-store-policy-hotspots-2026.md` — broader 2026 policy landscape
- `mobile-feature-flags-remote-config.md` — tuning prompt cadence without releases
- `mobile-analytics-patterns.md` — request-scoped (not display-scoped) event design
