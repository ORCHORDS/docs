# CSS caret styling and blink-animation policy

**Issue:** A custom editor hides the insertion caret, uses low-contrast styling, or depends on uncontrolled blinking that conflicts with accessibility and user preferences.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** progressive enhancement; newer caret properties have limited support

CSS UI defines caret styling, including `caret-color` and newer controls such as `caret-shape` and `caret-animation`. Keep the platform caret as the semantic editing indicator; styling must remain visible across focus, selection, themes, forced colors, and composition.

**Source:** [CSS Basic User Interface Level 4 — insertion caret](https://drafts.csswg.org/css-ui-4/#insertion-caret)

## Controls

- preserve `auto` as the baseline and change caret styling only for a demonstrated editing need;
- ensure sufficient contrast against every editable background and selection color;
- scope changes to editable controls, not all focused elements;
- feature-detect newer properties and accept native fallback;
- honor forced-colors, reduced-motion, and platform accessibility behavior;
- never represent validation, security, or save state solely through caret color or shape.

## Verification

Test light/dark themes, forced colors, high contrast, zoom, keyboard focus, mouse placement, empty fields, selection, password controls, contenteditable, IME composition, RTL and vertical writing modes, and unsupported engines. Confirm caret visibility after font loading and during scroll.

## Gotchas

A transparent caret can make editing unusable while the control still receives input. Blink timing and shape may be platform-controlled despite CSS. Custom fake carets commonly break selection, mobile keyboards, assistive technology, and composition; avoid them.
