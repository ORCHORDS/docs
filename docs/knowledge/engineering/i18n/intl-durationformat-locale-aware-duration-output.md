# Intl.DurationFormat Locale-Aware Duration Output

**Issue:** Hand-built strings such as “1 hr 02 min” hard-code unit order, separators, plural rules, digits, and direction, producing incorrect duration output across locales.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Represent a duration as numeric fields—years through nanoseconds—separately from any start/end timestamp calculation. Pass those fields to `Intl.DurationFormat` with an explicit locale and a product-defined style: `long`, `short`, `narrow`, or `digital`. Use unit-specific display options only when the design requires them.

Use `formatToParts()` when markup or accessible annotation is needed; preserve the returned order and literal separators rather than rearranging parts. Cache formatter instances by resolved locale and options in hot paths. Feature-detect and ship a tested polyfill or server-rendered fallback for unsupported runtimes.

Do not use duration formatting to calculate elapsed calendar time. Months and days are context-dependent; compute a domain duration with a suitable temporal/calendar library first, then format it.

## Verification

Create locale fixtures covering Latin and non-Latin numbering systems, RTL layout, plural categories, digital separators, zero fields, negative durations, fractional seconds, and very large values. Assert semantic parts or approved locale snapshots rather than one English string. Test assistive-technology pronunciation and bidirectional isolation around interpolated surrounding text.

## Gotchas

Duration fields must be integral and use a consistent sign; mixed positive and negative fields are invalid. Locale data and runtime support can change, so over-specific punctuation snapshots are brittle. “Digital” output is still locale-sensitive.

## Sources

- [TC39 Intl.DurationFormat specification](https://tc39.es/proposal-intl-duration-format/)
- [MDN Intl.DurationFormat](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/DurationFormat)
- [ECMA-402 internationalization specification](https://tc39.es/ecma402/)
