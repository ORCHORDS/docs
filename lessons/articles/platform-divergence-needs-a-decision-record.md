# Deliberate Platform Divergence Needs a Decision Record

**Issue:** Mobile and desktop implementations drift for both valid platform reasons and accidental delivery reasons. Without a recorded decision, temporary omissions become permanent and purposeful adaptations are repeatedly “fixed” toward false uniformity.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Lesson

Record material divergence as a time-bounded product and engineering decision. Preserve the common user invariant while documenting why presentation, interaction, capability, or lifecycle behavior differs.

## Controls

- Give each divergence a stable ID linked to the affected capability and platforms.
- Record context, user outcome, platform constraint or opportunity, alternatives, accessibility and safety impact, data implications, owner, approval, review trigger, and sunset condition.
- Distinguish platform-native adaptation from unavailable capability and from short-term delivery debt.
- Define the invariant that must remain common even when workflows differ.
- Require new platforms and major platform changes to re-evaluate existing decisions.
- Surface divergence to support, documentation, analytics, and test planning.
- Close records only after evidence shows convergence, replacement, or permanent acceptance.

## Verification

- Sample visible differences and require a live record or classify them as defects.
- Test the common invariant and the platform-specific path independently.
- Trigger review on platform API, form-factor, permission, or policy changes.
- Confirm expired temporary records block release or have explicit renewal.

## Gotchas

A decision record is not permission to ship a weaker safety or accessibility outcome. “Native convention” needs a cited platform behavior and user rationale. Divergence by operating system can still be wrong when the true boundary is window, input, permission, or hardware capability.

## Official sources

- [Apple Human Interface Guidelines: getting started](https://developer.apple.com/design/human-interface-guidelines/getting-started)
- [Android adaptive app guidance](https://developer.android.com/develop/adaptive-apps/guides/adaptive-dos-and-donts)
