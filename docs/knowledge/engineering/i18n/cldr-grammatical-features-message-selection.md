# CLDR grammatical features for message selection

**Issue:** Translating only by plural category can produce grammatically invalid messages when a locale also requires gender, case, or definiteness agreement.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Decision

Treat grammatical features as typed localization inputs. Use the locale’s CLDR grammatical-feature data to determine which distinctions are supported, then let translators author complete message variants. Do not generate inflection by concatenating translated fragments.

## Controls

- Resolve locale inheritance before reading supplemental grammatical-feature data.
- Model CLDR gender, case, and definiteness as separate dimensions from plural rules.
- Limit selectable values to those published for the resolved locale and usage.
- Require a deterministic fallback when a requested feature or translated variant is absent.
- Keep runtime values semantic: pass a unit or entity plus grammatical metadata, not pretranslated fragments.
- Validate message catalogs so every referenced feature value has a reachable variant.
- Pin and record the CLDR release used by build and runtime.

## Verification

For each supported locale, generate a matrix of plural category and supported grammatical dimensions. Test nominative/default fallbacks, locales with no grammatical data, locale inheritance, and missing variants. Have native-language review for high-impact user flows; mechanical tests cannot prove natural wording.

## Gotchas

CLDR describes available grammatical distinctions and data; it is not a universal natural-language inflection engine. Supported features vary by locale and may evolve between CLDR releases. Plural categories can interact with grammatical case, but one cannot be substituted for the other.

## Sources

- [Unicode LDML Part 2: Grammatical Features](https://unicode.org/reports/tr35/tr35-general.html#Grammatical_Features)
- [Unicode CLDR releases](https://cldr.unicode.org/index/downloads)
