# Intl.NumberFormat range source parts

**Issue:** A price or measurement range is built by concatenating two formatted numbers. That repeats currency/unit labels, uses the wrong locale separator, and makes it impossible to style the start and end without parsing localized text.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Controls and implementation

Create one `Intl.NumberFormat` with an explicit locale and business-approved style, currency/unit, notation, and rounding policy. Use `formatRange(start, end)` for display and `formatRangeToParts()` when markup needs semantic spans. Interpret each part's `source` as `startRange`, `endRange`, or `shared`; never infer ownership from punctuation or position.

Validate finite/domain-appropriate inputs and `start <= end` before formatting. Keep original numeric values for calculation and accessibility text. Feature-detect the range methods and fall back to two complete `format()` results joined by a localized message pattern.

## Verification

Test equal endpoints, values that become equal after rounding, negative zero, negative-to-positive ranges, currencies with different fraction digits, compact notation, units, non-Latin numbering systems, RTL locales, BigInt where supported, and missing range methods. Snapshot part types and sources rather than engine-specific spaces.

## Gotchas

Formatting may collapse shared fields or show an approximation marker when distinct inputs round to the same display. Rendered text is not a reversible data format and must not determine pricing, interval inclusion, or validation.

## Sources

- Ecma International, [ECMA-402 Internationalization API](https://tc39.es/ecma402/#sec-intl.numberformat.prototype.formatrangetoparts)
