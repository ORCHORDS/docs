# CLDR locale quotation marks and nested quotations

**Issue:** A product hard-codes English curly quotes, causing incorrect primary or nested quotation marks in other locales.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

Quotation marks are locale data. Resolve the active content locale through CLDR and use its quotation-start, quotation-end, alternate-quotation-start, and alternate-quotation-end delimiters. Keep this separate from translating the quoted text.

**Sources:** [Unicode LDML general specification — delimiters](https://unicode.org/reports/tr35/tr35-general.html#Delimiter_Elements) · [CLDR locale data](https://cldr.unicode.org/)

## Controls

- obtain primary and alternate delimiters from the same pinned CLDR/runtime version;
- carry an explicit content locale instead of inferring it from device region or UI language;
- track nesting depth so odd/even levels select the intended delimiter pair;
- escape text for the output context before wrapping it; quote characters are not an HTML-safety mechanism;
- preserve author-supplied quotation marks when editing faithful source material.

## Verification

- fixture tests cover at least one English, German, French, Japanese, and Arabic locale;
- nested quotation fixtures assert both opening and closing delimiters;
- fallback behavior is deterministic for unsupported or malformed locale tags;
- snapshots are regenerated intentionally when CLDR data changes.

## Gotchas

- punctuation placement is a separate locale/editorial rule.
- straight ASCII quotes are not a universal fallback for published text.
- runtime locale data can differ across browsers and OS versions; server/client rendering must not silently disagree.
