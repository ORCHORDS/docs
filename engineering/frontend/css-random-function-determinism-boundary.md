# CSS random function determinism boundary

**Issue:** CSS Values Level 5 drafts `random()` and sharing controls for generated numeric values. Using draft randomness for identity, security, durable layout, or test-critical output produces unstable and incompatible interfaces.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** experimental

## Controls and implementation

Use random CSS values only for decorative progressive enhancement. Feature-detect the exact syntax, provide a deterministic fallback, bound every range, and respect reduced motion. Never derive DOM identity, accessibility order, hit targets, security tokens, experiments, or persisted choices from CSS randomness. Use explicit sharing scope when several properties must agree.

## Verification

Test unsupported engines, reload/navigation, repeated components, range endpoints, invalid increments, animation, snapshots, zoom, and reduced motion. Assert semantics and interaction remain identical under any generated value.

## Gotchas

The proposal is an evolving Working Draft and seeding/sharing behavior may change. Visual randomness is not cryptographic randomness and may complicate reproducible screenshots.

## Sources

- W3C CSSWG, [CSS Values and Units Level 5 — random()](https://www.w3.org/TR/css-values-5/#randomness)
- W3C, [WCAG 2.2 — Animation from Interactions](https://www.w3.org/TR/WCAG22/#animation-from-interactions)
