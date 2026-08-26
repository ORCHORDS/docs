# mobile-staged-rollout-phased-release

**Issue:** Shipping a mobile release to 100% of users on day one bets the entire user base on untested production behavior — and mobile has no instant rollback: once a binary is on devices, a fix requires a new store review cycle (hours to days). Both stores provide staged delivery mechanisms (Google Play staged rollouts, Apple phased release), but they behave differently, are frequently misunderstood ("pause" vs "halt", automatic vs manual percentages), and only reduce risk if you wire them to monitoring gates that actually stop promotion when crash rates or key metrics regress. This article covers how each store's mechanism works in 2025-2026, what the thresholds and timelines are, and how to build the gate-then-promote loop.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why staged delivery is the mobile rollback story

1. **There is no unpublish-and-revert for binaries.** Unlike a web deploy, you cannot shrink the installed base: users who already received the version keep it even when you halt the rollout. The only "rollbacks" are shipping a hotfix (full review cycle) or force-disabling features remotely — which is why `mobile-feature-flags-remote-config.md` kill switches and staged rollout are complementary, not alternatives.
2. **Store review approves the binary once, delivery is separate.** Both stores review the version before any user gets it; staged percentages then control distribution to *automatic updaters*. This means the reviewed artifact is fixed — you cannot patch mid-rollout without a new version and a new review.
3. **Small cohorts surface long-tail device bugs.** The first 1-5% includes your oddest devices (low RAM, aggressive OEM battery managers, weird locales). Crash clusters that never appeared on the test fleet (see `mobile-device-fragmentation-test-matrix.md`) show up here while 95% of users are still on the known-good version.
4. **Reputational asymmetry favors slow promotion.** A one-star review wave from a bad rollout outlasts the extra day a staged release costs. Standard practice in 2025-2026 is: promote percentage only when crash-free users and ANR rates are statistically indistinguishable from the previous version.

## Google Play staged rollout mechanics

1. **You choose arbitrary percentages (0.1% increments up to 100%).** Staged rollout is set on the production track when releasing; typical ladders are 1% → 5% → 20% → 50% → 100%, holding each stage for 24-48h of live traffic. Users are selected randomly and stickily — a device selected for the stage keeps the new version.
2. **Halting stops new deliveries but never downgrades existing ones.** Per Play Console docs, a halted rollout means no *additional* users receive the version; users who already updated keep it. Resuming later continues from where you stopped; you cannot rewrite history, only stop the bleeding.
3. **Updating a staged release restarts the review and resets the stage.** If you upload a fixed version while 5% runs the bad one, the new version goes through review and starts its own rollout (you can start it at a higher percentage). The bad 5% keeps running the old binary until they get the next update — hence kill switches matter.
4. **Staged rollout percentages interact with testing tracks.** Internal → closed → open → production staged is the full funnel; issues found in closed testing reduce the production stage ladder you need. But open-test users are self-selected enthusiasts, so production 1% still finds new bugs.
5. **Play Console exposes per-version Android Vitals (crash rate, ANR rate) sliced by the staged cohort.** Gate promotion on the *new version's* crash rate, not the app-wide blended rate — at 1% rollout, a blended dashboard hides a 10x regression.

## App Store phased release mechanics

1. **The curve is fixed: 1, 2, 5, 10, 20, 50, 100% over 7 days.** Per App Store Connect docs, once you opt a version into phased release, Apple automatically expands availability on that schedule (day 1 = 1%, cumulative). You do not pick custom percentages like on Play.
2. **You can pause for up to 30 days total, any number of times.** Pausing freezes the curve; resuming continues to the next scheduled step. There is no true "halt" — and crucially, users who manually visit the App Store product page always get the new version immediately; phased release only throttles *automatic updates*.
3. **Expedited review is the emergency lever.** For a critical fix after pausing, request expedited review and roll the new version to 100% (skipping phasing for the fix). Apple grants these for genuine breakage; do not burn the goodwill on routine releases.
4. **Version release controls are separate and upstream.** "Manually release this version" vs "automatically release" vs "phased" — a common mistake is enabling manual release, approving the version weeks before intending to ship, then wondering why phased release never started. The phased curve begins when the version is released to automatic updates.
5. **Mark pausing in the release calendar.** Because the 7-day curve pauses across weekends/holidays silently, teams lose track of which day the 20% step lands. Keep a runbook entry per release with the intended pause points tied to metric checks.

## Building the gate: thresholds, monitoring, and the halt decision

1. **Define promotion gates before the release, numerically.** Typical 2025-2026 gates: crash-free sessions ≥ previous version − 0.1pp, ANR rate not worse than baseline, no new top-10 crash signature, and no regression in the launch funnel metric that pays the bills. Without pre-agreed numbers the gate becomes a debate while the rollout clock keeps running.
2. **Wait for statistical significance at each stage.** At 1% of a small user base, a handful of crashes is noise. Compute the minimum sample (or use crash-reporting tools' regression detection) before deciding; hold stages longer early when traffic is low.
3. **Automate the gate if you can, but keep a human halt authority.** CI/CD (see `mobile-ci-cd-fastlane.md`) can query Crashlytics/Sentry via API and block the promotion step in the pipeline. The halt/pause button itself should have a named on-call owner — a 2 a.m. regression needs a decision in minutes, not a thread.
4. **Watch server-side signals, not just client crashes.** Staged rollout shifts traffic to new API versions (headers, payloads) at the same percentage; gateway error rates, p99 latency per app version, and feature-flag evaluation errors are early rollout gates too. A release can be crash-free and still be economically broken (payments failing silently).
5. **Rehearse the halt path.** Quarterly, practice: pause/halt in the console, flip the remote kill switch, and confirm the rollback feature-flag actually disables the broken path on devices already running the bad version. A kill switch that was never exercised in prod is a hope, not a control.
6. **Log rollout stage into analytics events.** Tag events with app version; when postmorteming, the stage timeline (from console export or runbook) plus per-version metrics tells you exactly which cohort saw what — this is the evidence trail for "how many users were affected."

## Related

- `android-play-store-submission.md`
- `ios-app-store-submission.md`
- `mobile-feature-flags-remote-config.md`
- `mobile-crash-reporting.md`
- `mobile-ci-cd-fastlane.md`
