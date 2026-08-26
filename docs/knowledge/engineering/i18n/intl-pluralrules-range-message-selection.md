# Intl.PluralRules Range Message Selection

**Issue:** Choosing a plural form from only the range endpoint produces incorrect grammar because languages define plural categories for the pair as a whole.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Resolve the locale and use `Intl.PluralRules(locale, {type:"cardinal"}).selectRange(start,end)` to select the message variant for a numeric range. Provide translations for every category the locale can return—`zero`, `one`, `two`, `few`, `many`, and `other`—with a safe `other` fallback.

Format the two numbers with `Intl.NumberFormat.formatRange()` using compatible rounding options. Feed plural selection the same displayed numeric values/precision so grammar is not selected from hidden digits. Keep plural-rule keys in the translation catalog; do not build sentences by appending suffixes.

## Verification

Use CLDR-derived fixtures for languages with several range categories, equal endpoints, decimals, negative values, zero, and values that round to the same display. Verify RTL/bidi isolation and screen-reader output. Test environments lacking `selectRange` with a versioned message-format fallback.

## Gotchas

Range rules are not necessarily the rule of either endpoint. Cardinal and ordinal rules differ. Locale-data updates can change expected categories, so test semantic variants rather than English snapshots alone.

## Sources

- [MDN Intl.PluralRules.selectRange](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/PluralRules/selectRange)
- [ECMA-402 PluralRules selectRange](https://tc39.es/ecma402/#sec-intl.pluralrules.prototype.selectrange)
- [Unicode CLDR plural rules](https://cldr.unicode.org/index/cldr-spec/plural-rules)
