# app-store-review-can-take-two-weeks

**Issue:** Teams that don't account for app store review time in their release planning miss launch dates and cannot ship urgent fixes quickly
**Date:** 2026-08-11
**Status:** documented

## What happened
A critical payment bug was found in a production iOS app. A fix was ready within four hours. The App Store review took nine days. For nine days, users experienced payment failures. The team had no expedited review process established and no server-side feature flag to disable the broken code path while the review was pending.

## The lesson
App store review is a mandatory step in the mobile release pipeline with unpredictable duration (typically 1-3 days but up to 2 weeks for new features or after rejection). Plan your release timeline with buffer. For critical hotfixes, design server-side kill switches that can disable broken features without a new binary. Establish an expedited review relationship with Apple before you need it.

## Why it matters
Web deployments are seconds. Mobile deployments are days. Every release plan that doesn't account for review time will cause a missed deadline. Critical bugs cannot be fixed instantaneously on mobile without pre-built server-side escape hatches.

## How to apply
- [ ] Add at least 5 business days of app store review buffer to any mobile release deadline.
- [ ] Build feature flags for every major feature that can be toggled server-side without a new binary.
- [ ] Submit for review at least one week before any external commitment (partner launch, marketing date).
- [ ] For iOS, apply for expedited review only for genuinely critical issues — Apple penalizes misuse.
- [ ] Never couple mobile release dates to server-side release dates without acknowledging the review buffer.

## Related
- `feature-flags-before-code-changes.md`
- `crash-free-rate-below-99-kills-reviews.md`
