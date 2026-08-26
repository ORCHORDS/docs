# mobile-crash-free-rate-slos

**Issue:** "The app feels stable" is not an SLO. Crash-free rate turns stability into a number teams can alert on and gate releases with, but the metric is widely misunderstood. Crash-free sessions and crash-free users are different numbers (users almost always reads higher, which is why vendors lead with it); every vendor defines a session differently, so Crashlytics, Sentry, and Play Vitals numbers for the same app do not agree and cannot be compared; and the benchmarks have moved — 99% was "acceptable" years ago, while 2025-era data puts the competitive baseline at 99.9-99.95% crash-free sessions, with Instabug correlating sub-99.9% apps with store ratings under three stars. This article covers metric definitions, realistic target-setting, measurement pitfalls, and how to operate crash-free rate as an actual SLO with error budgets and rollout gates.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Metric Definitions

1. **Crash-free sessions.** The percentage of sessions that did not end in a crash. Firebase defines a session as starting when the app foregrounds and ending when it backgrounds or terminates — so a crash during a background task may not attach to a session, and a user who crashes twice in one long session counts once.

2. **Crash-free users.** The percentage of users who experienced no crash in the period. One crash across ten sessions from a power user moves this number less than the same crash hitting ten one-session users, which is why it runs higher than the sessions figure and why it can mask concentrated pain.

3. **Users overstates lived experience.** A single user who crashes every session still counts as only one crashed user; the sessions metric captures that misery, the users metric hides it. Report both, gate on sessions, and trend users.

4. **ANRs and hangs are separate metrics.** Android vitals tracks ANR rate independently (watch for the 0.47% bad-behavior threshold), and iOS reports hangs; neither lowers crash-free rate. A fleet can be crash-free and still be slow-frozen garbage — track hang/ANR dashboards beside crash dashboards, not inside them.

## Benchmarks and Target Setting

1. **The classic ladder.** Community rule of thumb: 99% crash-free sessions is the floor for shipping, 99.5% is decent, 99.9%+ is excellent. Below 99% you are visibly bleeding users and reviews regardless of how good the product is.

2. **The 2025 baseline claim.** Current stability reporting (AlphaBin's 2025 numbers) treats 99.95% crash-free sessions as the baseline for top apps. Treat 99.9% as the SLO floor for any app with paying users, and 99.95% as the stretch target once you have symbolicated pipelines running (see the crash symbolication article).

3. **Ratings correlation justifies the budget.** Instabug's benchmark data shows apps under 99.9% crash-free sessions are far likelier to sit under three stars. Use this when arguing for stability work over features: the rating compound effect is cheaper to keep than to rebuild.

4. **Tier your targets.** Set distinct SLOs per app tier: payments/KYC flows (the example project case) justify 99.95%+, content and social apps can reasonably live at 99.5-99.9%. One number for a portfolio of apps leads to over-investing in toys and under-investing in money paths.

## Measurement Pitfalls

1. **Vendor definitions differ.** Crashlytics, Sentry, and Play Vitals all define sessions and crashes differently (Vitals counts sessions the OS sees; Crashlytics counts SDK-observed ones; Sentry slices by release and session). Pick one system of record for the SLO and never cross-compare absolute numbers between them.

2. **Slice by version, OS, and device.** An aggregate 99.7% can hide a 95% crash-free rate on the newest release for one OEM on one OS minor. Every SLO dashboard must break down by app version, OS version, and top devices — the aggregate number is for executives, decisions happen on the slices.

3. **Crashes that never upload.** Crashes at startup, offline at crash time, and instant kill paths never reach the backend; your true rate is always somewhat worse than reported. Track "crash suspicion" signals (sessions with no clean end, vitals-observed crashes vs SDK ones) to bound the blind spot.

4. **Release-window skew.** A staged rollout at 5% means the new version's crash data is thin and noisy for days. Compare cohorts on equal exposure windows (sessions-at-risk, not calendar days) before declaring a regression.

5. **Definition drift across platforms.** Combining iOS and Android into one number mixes two sessionization models (iOS backgrounding differs from Android process death — see the process-death article). Report per-platform SLOs and only then a weighted portfolio view.

## Operating the SLO

1. **Error budgets with burn alerts.** A 99.9% sessions SLO over 28 days buys a monthly crash budget; alert on budget burn rate (for instance, 5% of budget in one hour) rather than on the rate crossing the line, which is always too late. This mirrors standard SRE error-budget practice adapted to crash counts.

2. **Gate staged rollouts on the SLO.** Make crash-free sessions per version a hard rollout gate: halt at 1% if the version trends above the fleet SLO burn threshold. Combine with the staged-rollout article's halt criteria so stability and review-score signals halt the same lever.

3. **Trend alerts, not point alerts.** Day-over-day deltas and new-issue detection (a crash signature with zero history) catch regressions before the rolling rate moves. A new signature on a fresh release with any volume above trivial is a page, not a ticket.

4. **Root-cause discipline.** Every SLO breach gets a symbolicated stack, a responsible owner, and either a fix or a documented risk acceptance. Crash clusters without owners are how a 99.95% app decays to 99.5% in two quarters while every dashboard stays green on a weekly cadence.

5. **Publish the number.** Put crash-free sessions per release on the release checklist and in the release notes draft. Visibility is the cheapest stability tool that exists; hidden numbers regress.
