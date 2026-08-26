# i18n-architecture-2026

**Issue:** A team builds a new product. The team debates single-locale-first vs i18n-from-day-1. The team reads about Unicode, locale resolution, message extraction, runtime selection. The team needs the 2026 reference for i18n architecture decisions.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The 5 architectural decisions

1. **Locale resolution.** Browser `Accept-Language`, IP geolocation, user preference, URL path. Order matters.
2. **Message storage.** JSON in repo, JSON in CDN, database, TMS. Affects engineer/translator workflow.
3. **Plural and gender handling.** ICU MessageFormat vs template strings. Affects translator UI.
4. **Date/time/number formatting.** `Intl.*` APIs vs library. Affects bundle size and CLDR data.
5. **Right-to-left support.** CSS logical properties, `dir` attribute, icon mirroring. Affects component library.

## The 5-step i18n-from-day-1 pattern

1. **Set up message catalog** before any user-facing string.
2. **Wrap all UI components** with translation function.
3. **Externalize** strings at write time, not after.
4. **Test with pseudo-loc** on every PR.
5. **Real locale** (German, Arabic) in CI visual regression.

## The 5 anti-patterns

1. **"We'll localize later"** - 2-year refactor.
2. **Hardcoded English** in components.
3. **Concatenation** ("Hello, " + name).
4. **String IDs in user-facing copy** (showing "common.greeting" in UI).
5. **No plural handling** (single "item"/"items" lookup, not CLDR).

## Gotchas

- Locale resolution order: user preference > URL path > Accept-Language > IP > default.
- Locale matching with regional variants (en-GB vs en-US) is non-trivial.
- Plural categories differ across languages (some have 6 forms, not 2).
- ICU MessageFormat is verbose; for simple cases, plain `{{var}}` is fine.
- The default locale is a fallback, not a target - log when fallback is used.

## Source URLs (verified 2026-08-10)

- https://formatjs.io/docs/getting-started/message-syntax
- https://www.i18next.com/translation-function/formatting
- https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Accept-Language
- https://www.unicode.org/reports/tr35/tr35-general.html
