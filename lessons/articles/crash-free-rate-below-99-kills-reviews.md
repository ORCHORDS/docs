# crash-free-rate-below-99-kills-reviews

**Issue:** Mobile app crash rates above 1% trigger algorithmic App Store demotion and a cascade of one-star reviews
**Date:** 2026-08-11
**Status:** documented

## What happened
A React Native update introduced a memory leak on Android devices with less than 3 GB RAM — a significant portion of the user base in the target markets. Crash-free rate fell from 99.7% to 97.1%. App Store and Google Play ratings dropped from 4.5 to 3.9 within two weeks. App store algorithms reduced the app's search ranking. Organic installs fell 40% before the fix shipped.

## The lesson
Track crash-free session rate in real time using a crash reporting tool (Firebase Crashlytics, Sentry). Set an alert threshold at 99.0% — below this is a release-blocking incident. Test on real low-end devices that represent your user base, not just flagship test devices.

## Why it matters
Both Apple App Store and Google Play use crash rates as ranking signals. A crash-free rate below 99% triggers demotion, which reduces organic installs, which compounds revenue loss. Users who crash write reviews immediately; users with good experiences often do not.

## How to apply
- [ ] Integrate crash reporting (Crashlytics, Sentry) before the first production release.
- [ ] Set a real-time alert: page on-call if crash-free rate drops below 99.0% for 15 minutes.
- [ ] Define 99.5% crash-free as a release gate — do not ship if the current rate is below it.
- [ ] Test release candidates on the lowest-spec device that represents 10%+ of your user base.
- [ ] Triage crash reports within 24 hours of a new release — the first hour has the most signal.

## Related
- `battery-drain-kills-app-ratings.md`
- `app-store-review-can-take-two-weeks.md`
- `monitor-before-and-after-deploy.md`
