# accessibility-is-not-optional

**Issue:** Accessibility is treated as a nice-to-have and retrofitted under legal pressure at great cost
**Date:** 2026-08-11
**Status:** documented

## What happened
A public-facing web application was developed over two years with no accessibility consideration. An advocacy organization filed an ADA lawsuit citing that screen reader users could not complete core tasks. Settlement required a full accessibility audit, remediation of over 400 issues, and quarterly audits for two years. The engineering cost was $600k — roughly 40x what accessibility-first development would have cost.

## The lesson
Accessibility (WCAG 2.1 AA at minimum) is a legal requirement in many jurisdictions and a basic obligation to disabled users. Build it in from the start: use semantic HTML, test with screen readers, ensure keyboard navigability, maintain sufficient color contrast. Retrofit is 10-40x more expensive than building it right the first time.

## Why it matters
Beyond legal risk, roughly 15-20% of the global population has some form of disability. Inaccessible products exclude a significant user segment. Retrofit is expensive and disruptive. The ADA, EAA, and similar laws are increasingly enforced.

## How to apply
- [ ] Include accessibility in the definition of done for every new component and feature.
- [ ] Run automated accessibility checks (axe, Lighthouse) in CI — fail builds on critical violations.
- [ ] Conduct manual keyboard navigation and screen reader testing (NVDA, VoiceOver) for all new flows.
- [ ] Check color contrast ratios (WCAG AA requires 4.5:1 for normal text) in design review.
- [ ] Include users with disabilities in usability testing.

## Related
- `internationalisation-costs-triple-if-retrofitted.md`
- `user-consent-flows-need-ux-review.md`
