# i18n-string-externalization-2026

**Issue:** A team ships a product with hardcoded English strings in JSX/components. The team needs to extract all strings into message catalogs. The team reads about i18next, react-intl, FormatJS, and gets confused about which to pick.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The 4 React i18n libraries compared

| Library | Format | Bundle | API style | ICU | Best for |
|---|---|---|---|---|---|
| react-i18next | JSON | ~10KB | Hook (`useTranslation`) | Via i18next-icu | Most React apps |
| react-intl (FormatJS) | JSON / ICU | ~25KB | Component + hook | Native | Apps needing full ICU |
| LinguiJS | PO/MO, ICU | ~10KB | Component + macro | Native | Lingua-style extraction |
| JSX/i18n via ttag | PO | ~5KB | Tagged template | Yes | TypeScript, build-time extraction |

## The 4-step decision rule

1. **Most React apps** → react-i18next. Best ecosystem, simple.
2. **Need full ICU MessageFormat 2** → react-intl.
3. **Lingua-style workflow (annotation at build time)** → LinguiJS.
4. **TypeScript-first, minimal runtime** → ttag.

## The 5 anti-patterns

1. **Hardcoded strings in components.** Block localization entirely.
2. **Concatenating translated strings.** Breaks in any language with different word order.
3. **Passing dynamic content as translation key.** Translator cannot anticipate values.
4. **Plural as `"1 item"` / `"N items"` lookup.** Use ICU plural.
5. **Skipping namespace organization.** 500 flat keys are unmaintainable; use nested namespaces.

## The 5 best practices

1. **Set up extraction** with `i18next-parser` or `formatjs` CLI in CI.
2. **Namespace by feature** (`common`, `checkout`, `settings`).
3. **Use ICU MessageFormat** for any plural/gender/select.
4. **Source-language catalog** in version control, no English strings as fallback at runtime.
5. **Lazy-load namespaces** for large apps.

## Source URLs (verified 2026-08-10)

- https://react.i18next.com/
- https://formatjs.io/docs/react-intl
- https://lingui.dev/
- https://ttag.js.org/
- https://github.com/i18next/i18next-parser
