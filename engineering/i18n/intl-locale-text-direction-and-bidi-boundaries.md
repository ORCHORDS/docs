# Intl.Locale Text Direction and Bidirectional Boundaries

**Issue:** Inferring layout direction from a language-code prefix fails for locale aliases and script subtags, while setting global RTL without isolating embedded identifiers can reorder mixed text dangerously.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Resolve and canonicalize the active locale, then use `Intl.Locale.prototype.getTextInfo().direction` when supported. Feature-detect because older implementations exposed a `textInfo` accessor and support remains limited. Use pinned CLDR layout data for fallback rather than a hand-maintained language list.

Set the document or component `dir` from the resolved direction so CSS logical properties and native bidi behavior work. Use `dir="auto"` for user-generated text whose direction is content-dependent. Isolate embedded order numbers, email addresses, URLs, hashes, and code with `bdi` or an equivalent Unicode isolation boundary; do not reverse strings or icons indiscriminately.

## Verification

Test Arabic/Hebrew/Persian, Latin, explicit script subtags, locale aliases, mixed numbers and punctuation, URLs/email, user-generated text, nested direction overrides, screen readers, copy/paste, and unsupported runtimes. Verify logical margins/padding, icon semantics, table order, and form error placement.

## Gotchas

Locale direction is a default, not proof of each string's direction. CSS visual reordering must not corrupt DOM reading order. Mirroring directional icons is semantic; brand marks and media controls may not mirror.

## Sources

- [MDN Intl.Locale.getTextInfo](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/Locale/getTextInfo)
- [ECMA-402 Locale text info](https://tc39.es/ecma402/#sec-Intl.Locale.prototype.getTextInfo)
- [Unicode Bidirectional Algorithm](https://unicode.org/reports/tr9/)
