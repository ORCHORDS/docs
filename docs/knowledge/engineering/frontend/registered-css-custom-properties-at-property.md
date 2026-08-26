# Registered CSS custom properties with @property

**Issue:** A custom property is treated as an untyped token stream, so invalid values survive until use, animations jump discretely, or inheritance behaves differently from the component contract. Teams then add JavaScript parsing that disagrees with CSS computed-value rules.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Problem and applicability

The CSS Properties and Values API registers a custom property with a syntax, inheritance rule, and optional initial value. Authors can register declaratively with @property or through CSS.registerProperty.

Use registration when a design token needs typed validation, predictable inheritance, interpolation, or a defined fallback at computed-value time. Keep ordinary double-dash custom properties for open-ended token composition where registration would be unnecessarily restrictive.

## Controls and implementation

1. Choose one stable property name and one ownership boundary. Registration is global to the document, even when the property is consumed inside a shadow tree.
2. In @property, provide syntax and inherits descriptors. Provide initial-value unless the universal syntax is used; when required, the initial value must be computationally independent rather than depend on layout or another unresolved context.
3. Match syntax to the actual value domain, such as length, color, number, or a documented alternative. Do not broaden it to universal syntax just to hide invalid author input.
4. Set inherits explicitly. Component-local state often needs false; theme tokens commonly need true. Never assume registration preserves the inheritance behavior an unregistered property previously had.
5. Treat CSS.registerProperty as a one-time bootstrap action. Duplicate or inconsistent registration throws; make hot reload, micro-frontends, and repeated module evaluation idempotent at the application boundary.
6. Define an unregistered fallback declaration for engines that do not support the feature. Feature-detect CSS.registerProperty when JavaScript behavior depends on it and use normal cascade fallbacks for CSS.
7. Audit animations after registration. Typed properties can interpolate according to their value type, but the consuming property and browser still determine visible behavior and performance.
8. Version changes to syntax, inheritance, or initial value as a public component-contract change. A stricter registration can invalidate previously accepted declarations throughout the page.

## Verification

Test valid and invalid specified values, missing values, inheritance across ordinary DOM and shadow boundaries, @property parsing failure, duplicate JavaScript registration, hot reload, animation endpoints and interruption, computed styles, unsupported browsers, and initial values under different font and viewport conditions.

Confirm an invalid value resolves according to the registered-property rules without producing a hidden JavaScript/CSS disagreement. Test forced colors and user styles when the property controls visual meaning.

## Gotchas

- Registration is not scoped to the stylesheet, component, or shadow root that declared it.
- An @property rule with invalid required descriptors is ignored as a rule.
- Typed interpolation does not guarantee compositor-only animation.
- Changing inherits can alter every unset descendant and should receive regression coverage.

## Official sources

- [CSS Properties and Values API Level 1](https://drafts.css-houdini.org/css-properties-values-api-1/)
- [CSS Cascading Variables Level 1](https://www.w3.org/TR/css-variables-1/)
