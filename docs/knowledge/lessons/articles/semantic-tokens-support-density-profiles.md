# Shared semantic tokens support distinct density profiles

**Issue**

Sharing a design system does not require every form factor to use identical spacing, typography, navigation, or information density. Raw-value reuse can make touch layouts cramped or desktop workflows inefficient.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Separate semantic tokens such as control target, content gap, readable measure, and focus ring from raw scale values.
- Define a small set of density profiles by interaction and content constraints, not device brand.
- Keep component state, naming, accessibility semantics, and visual hierarchy common while allowing composition and density to vary.
- Ensure compact profiles still meet target-size, text-spacing, focus, and zoom requirements.
- Version token contracts and make platform overrides explicit rather than scattered local exceptions.

## Verification

1. Render every component/state across supported density profiles.
2. Run visual diffs plus semantic accessibility assertions; pixel similarity alone is not the goal.
3. Test large text, translated copy, coarse pointer targets, keyboard focus, and forced colors.
4. Verify a token change reports all affected components before release.

## Gotchas

- A single global spacing multiplier rarely preserves every component invariant.
- Compact does not mean smaller interactive targets.
- Platform-native conventions can require different composition while retaining the same semantic token.
- Design-token sharing does not justify sharing inaccessible DOM structure.

## Official sources

- [W3C Design Tokens Format Module](https://www.designtokens.org/tr/drafts/format/)
- [WCAG Target Size](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html)
- [WCAG Text Spacing](https://www.w3.org/WAI/WCAG22/Understanding/text-spacing.html)
