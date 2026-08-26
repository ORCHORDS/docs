# locale-display-names-2026

**Issue:** A team builds a language picker dropdown. The team shows "en-US" codes to users. Users don't recognize codes. The team needs to show locale names in each user's own language ("English (US)" for English speakers, "Anglais (États-Unis)" for French speakers, "Inglés (Estados Unidos)" for Spanish speakers).

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The 4 Intl APIs for display names

1. **`Intl.DisplayNames(locale, options)`** - language, region, script, currency names in any target locale.
2. **`Intl.supportedValuesOf('language')`** - list of supported language tags.
3. **`Intl.supportedValuesOf('region')`** - supported region codes.
4. **`Intl.supportedValuesOf('currency')`** - supported currency codes.

## The 5-step language picker pattern

1. Get supported locales from your app's catalog.
2. For each locale, render `Intl.DisplayNames(targetLocale, { type: 'language' }).of(locale)`.
3. Sort by display name in the user's locale.
4. Cache the display names per (locale, targetLocale) pair.
5. Fallback to native locale name if `Intl.DisplayNames` doesn't support the code.

## The 5 anti-patterns

1. **Showing raw locale codes to users.** "en-US" is meaningless to most.
2. **Showing English names for all locales.** "Spanish (Spain)" shown to a French user is wrong audience.
3. **Translating locale names manually.** ICU CLDR already has them.
4. **Hardcoding the locale list.** `Intl.supportedValuesOf` is the source of truth.
5. **No fallback for unsupported locales.** Show the code with a tooltip explaining the locale.

## Gotchas

- `Intl.DisplayNames` returns `undefined` for codes it doesn't recognize; handle gracefully.
- Long form ("English (United States)") vs short form ("English (US)") - choose based on context.
- Currency display names need `type: 'currency'`; language/region/script have their own.
- `style: 'long' | 'short' | 'narrow'` controls verbosity.
- Some languages have variant names ("zh-Hant" vs "zh-Hans"); display in the user's own script.

## Source URLs (verified 2026-08-10)

- https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/DisplayNames
- https://tc39.es/ecma402/#sec-intl-displaynames-objects
- https://www.unicode.org/reports/tr35/tr35-general.html#Display_Names
