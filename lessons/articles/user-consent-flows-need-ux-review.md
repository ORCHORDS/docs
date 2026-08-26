# user-consent-flows-need-ux-review

**Issue:** Legally compliant consent flows that are confusing or deceptive in practice expose the company to regulatory action
**Date:** 2026-08-11
**Status:** documented

## What happened
A company's cookie consent banner was reviewed by legal and deemed compliant. However, the "Reject all" button was a small grey link in a corner, while "Accept all" was a large prominent button. A UX researcher flagged this as a dark pattern. A regulator's investigation confirmed the design did not meet the GDPR requirement for freely given consent. The fine was €2.2M.

## The lesson
Consent flows must be reviewed by both legal (for regulatory compliance) and UX (for genuine user comprehension and freedom). Dark patterns — pre-ticked boxes, buried reject options, confusing language — invalidate consent legally even if the underlying text is compliant.

## Why it matters
Regulators increasingly focus on UX patterns, not just text. An accessible, honest consent flow protects user autonomy and company liability. Dark patterns save a fraction of consent rates at the cost of potentially millions in fines.

## How to apply
- [ ] Have both legal and UX review consent flows before launch.
- [ ] Ensure "reject" and "accept" options are equally prominent — same button weight, same placement.
- [ ] Never pre-tick consent boxes for non-essential processing.
- [ ] Test consent flows with real users to verify they understand what they are agreeing to.
- [ ] A/B test consent copy for clarity, not to maximize acceptance rates.

## Related
- `gdpr-by-design-not-retrofit.md`
- `accessibility-is-not-optional.md`
