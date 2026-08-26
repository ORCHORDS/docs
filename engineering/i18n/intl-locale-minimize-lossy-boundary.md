# Intl.Locale minimize is a lossy presentation boundary

**Issue:** A system calls `Intl.Locale.prototype.minimize()` before persistence or authorization and drops explicit script/region choices that remain important to the user.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

ECMA-402 locale minimization removes subtags that can be inferred from likely-subtag data. Use it for compact display/interchange only when equivalence under the pinned locale-data version is acceptable; preserve the canonical explicit preference.

**Source:** [ECMA-402 Intl.Locale minimize](https://tc39.es/ecma402/#sec-Intl.Locale.prototype.minimize)

## Controls

- store the canonical user-selected tag separately;
- minimize only at an explicit output boundary;
- pin/runtime-version likely-subtag data where deterministic output matters;
- never use minimized strings as durable database keys or authorization scope;
- preserve Unicode extensions and private-use policy deliberately.

## Verification

Test language-only, explicit script, explicit region, variants, extensions, grandfathered/canonicalized tags, maximize/minimize round trips, and differing ICU/CLDR versions.

## Gotchas

Minimized text may change after locale-data updates. Round-tripping can recover a likely tag, not necessarily the user's original spelling or intent. Shorter is not more canonical for storage.
