# CLDR character labels for picker accessibility

**Issue:** An emoji, symbol, or character picker exposes English-only group names, raw Unicode code points, or unlabeled icon grids. Search and screen-reader navigation then fail outside the source locale.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Controls and implementation

Load version-pinned CLDR `characterLabel` and `characterLabelPattern` data for localized groups such as activities, punctuation, scripts, subscripts, and stroke counts. Keep category labels separate from per-character names and search annotations. Format parameterized labels through the locale's plural/message system rather than string concatenation.

Expose each group with a programmatic heading and each selectable item with a localized accessible name. Retain the underlying code point or sequence as data, not as the primary spoken label. Provide a documented fallback chain for missing locale data and preserve search aliases across CLDR upgrades so saved queries do not break unexpectedly.

## Verification

Test screen-reader group navigation, CJK stroke-count plurals, RTL layout, missing labels, locale fallback, emoji sequences, symbols without annotations, keyboard operation, zoom, and a CLDR-version upgrade. Review translated labels in context because a technically valid category term can still be unclear.

## Gotchas

Character labels describe groups and composition patterns; they are not universal names for every sequence. Unicode character names are stable identifiers but often poor localized UI copy, while emoji annotations serve a different search/name role.

## Sources

- Unicode Consortium, [LDML Part 2: Annotations Character Labels](https://unicode.org/reports/tr35/tr35-general.html#Character_Labels)
