# locale-fallback-strategies-2026

**Issue:** A user requests locale `fr-CA`. The app supports `en` and `fr`. The user gets `en` (default) instead of `fr` (the closest match). The user is French-speaking but in Canada; the fallback should be French, not English.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

Locale fallback is the 2026 production pattern for matching user preference to available locales. The fallback chain is explicit, not default-to-English.

## Root cause

`Intl.LocaleMatcher` (Stage 4, 2026) provides best-fit matching between requested and supported locales. The 2026 default: explicit fallback chain + Intl.LocaleMatcher for best-fit.

## The 5-step locale fallback pattern

1. **Read user preference** — cookie, URL param, Accept-Language header, user profile
2. **Build fallback chain** — e.g., `[fr-CA, fr, en]` (most specific to most general)
3. **Match against supported locales** — `[en, fr, es, de, ja]` (what the app supports)
4. **Pick the best match** — `fr` (closest to `fr-CA`)
5. **Fall back to default** — `en` if no match

The 5 steps are the 2026 production pattern.

## The Intl.LocaleMatcher pattern

```javascript
const supported = ['en', 'fr', 'es', 'de', 'ja', 'zh-Hans', 'zh-Hant'];

const matcher = new Intl.LocaleMatcher(supported, {
  algorithm: 'best-fit'
});

// User requests fr-CA
const match = matcher.match('fr-CA');
// match.locale === 'fr' (best match to fr-CA)

// User requests en-GB
const matchGB = matcher.match('en-GB');
// matchGB.locale === 'en' (no en-GB, fall back to en)

// User requests pt-BR (not supported at all)
const matchBR = matcher.match('pt-BR');
// matchBR.locale === undefined (no match) or default
```

`Intl.LocaleMatcher` is the 2026 standard for locale negotiation.

## The 4 fallback chain patterns

| Pattern | Example | When |
|---|---|---|
| Region + language | `[fr-CA, fr, en]` | regional variant first, then language, then default |
| Language + region | `[en-GB, en, en-US]` | specific dialect, then language, then closest region |
| Script + language | `[zh-Hans, zh, en]` | script-specific first (Simplified vs Traditional Chinese) |
| Default fallback | `[en]` | last resort; the app's default locale |

The 4 patterns cover the 2026 production scenarios.

## The 5 best practices

1. **Build an explicit fallback chain.** `[fr-CA, fr, en]` is documented; the chain is per-user.
2. **Persist the resolved locale.** Don't re-resolve on every request; cache per session.
3. **Use `Intl.LocaleMatcher` for best-fit.** Don't hand-roll matching; the algorithm is complex.
4. **Distinguish missing from unsupported.** `Intl.LocaleMatcher.match()` returns undefined for unsupported; handle explicitly.
5. **Document the chain.** A `LOCALES` config or i18n.ts file lists the supported locales; the fallback is a method.

## The 5 anti-patterns

1. **Default to English always.** Frustrates non-English users; even `fr` is better than `en` for a `fr-CA` user.
2. **Hand-rolled matching.** `locale.split('-')[0]` is too coarse; misses script and region subtleties.
3. **No fallback chain.** Single-locale match; `fr-CA` user gets 404 if only `en` supported.
4. **Cache the raw requested locale.** Store the resolved locale, not the requested one.
5. **Ignore `q` values in Accept-Language.** The header has quality factors; ignore them and the negotiation is wrong.

## The Accept-Language parsing pattern

```javascript
// Parse Accept-Language header with quality factors
function parseAcceptLanguage(header) {
  return header.split(',').map(lang => {
    const [tag, ...params] = lang.trim().split(';');
    const q = params
      .map(p => p.match(/q=([\d.]+)/))
      .filter(Boolean)
      .map(m => parseFloat(m[1]))[0] || 1.0;
    return { tag: tag.trim(), q };
  }).sort((a, b) => b.q - a.q);
}

// Header: fr-CA,fr;q=0.9,en;q=0.8,*;q=0.1
// Returns: [{fr-CA, 1.0}, {fr, 0.9}, {en, 0.8}, {*, 0.1}]
```

The 2026 production pattern: respect quality factors, sort by quality, match in order.

## The 5 URL patterns for locale

| Pattern | Example | When |
|---|---|---|
| Subdirectory | `/de/page` | most common, 2026 default |
| Subdomain | `de.example.com/page` | rare; complex DNS |
| ccTLD | `example.de/page` | large markets |
| Query param | `/page?lang=de` | easy to add; less SEO-friendly |
| Cookie | cookie-driven | UX preference; not URL-shareable |

The 2026 default: subdirectory (`/de/page`) with hreflang for SEO. See `i18n/hreflang-seo-2026.md`.

## The 5 supported-locales patterns

| Pattern | When | Example |
|---|---|---|
| Code list | most apps | `['en', 'fr', 'es', 'de']` |
| Object with metadata | when each locale has display name, currency, etc. | `[{code: 'en', name: 'English', currency: 'USD'}, ...]` |
| JSON file | content-driven | loaded from `/locales/supported.json` |
| Database table | CMS-driven | queried at startup |
| i18n library config | framework-specific | ICU MessageFormat + `supportedLocales` |

The 2026 default: TypeScript object with code, name, currency, flag, region.

## The 5 step pattern: cookie + URL + Accept-Language

```javascript
function getUserLocale(request) {
  // 1. Cookie (user preference, persists)
  if (request.cookies.locale) {
    return matchToSupported(request.cookies.locale);
  }
  // 2. URL param (e.g., /de/page)
  const urlLocale = request.pathname.split('/')[1];
  if (urlLocale && supported.includes(urlLocale)) {
    return urlLocale;
  }
  // 3. Accept-Language header
  const header = request.headers['accept-language'];
  if (header) {
    const parsed = parseAcceptLanguage(header);
    for (const { tag } of parsed) {
      const match = matcher.match(tag);
      if (match.locale) return match.locale;
    }
  }
  // 4. User profile
  if (request.user?.locale) {
    return matchToSupported(request.user.locale);
  }
  // 5. Default
  return 'en';
}
```

The 5-step pattern is the 2026 production default. The 5 sources cover all realistic inputs.

## The 4-step migration

For a team migrating from "default to English" to a proper fallback chain:

1. **Inventory supported locales.** List every locale the app actually has translations for.
2. **Build the fallback chain.** Per request, build `[requested, requested-language, default]`.
3. **Use `Intl.LocaleMatcher` for best-fit.** Don't hand-roll.
4. **Test edge cases.** `fr-CA` → `fr`; `en-GB` → `en`; `pt-BR` → `en`; `zh-Hant` → `zh`.

The 4 steps take a sprint; the benefit is forever.

## The 4 step persistence

After resolving the locale, persist it.

1. **Cookie** — `Set-Cookie: locale=fr; Path=/; Max-Age=31536000`
2. **URL** — for SEO, also reflect in URL (`/fr/...`)
3. **`<html lang>` attribute** — set on every page
4. **Server log** — log the resolved locale (analytics; no PII)

The 4 steps ensure consistency across requests.

## The 4 step i18n library integration

Most i18n libraries have built-in locale matching.

| Library | Locale matching API |
|---|---|
| i18next | `i18n.init({ fallbackLng: ['fr', 'en'] })` |
| react-intl | `IntlProvider` with `defaultLocale` and `locale` |
| FormatJS | `IntlProvider` with `defaultLocale` |
| next-intl | middleware matches from URL or header |

The 4 libraries handle the matching internally; the 5-step pattern above is the underlying logic.

## Verification

The tell that locale fallback is real:

- `Intl.LocaleMatcher` is used for best-fit
- An explicit fallback chain is configured per request
- Accept-Language quality factors are respected
- The resolved locale is persisted (cookie, URL, `<html lang>`)
- Edge cases (`fr-CA` → `fr`, `pt-BR` → `en`) are tested

The tell it isn't:

- Default to English for any non-supported locale
- `locale.split('-')[0]` for matching (loses region info)
- No fallback chain
- User preference ignored; always use default
- Caching the raw requested locale (e.g., `fr-CA` cached when only `fr` is supported)

## Gotchas

- **Accept-Language quality factors matter.** `fr-CA,fr;q=0.9,en;q=0.8` — `fr-CA` first, then `fr`, then `en`.
- **`Intl.LocaleMatcher` is Stage 4 as of 2026** — supported in all major browsers and Node 18+.
- **Region-specific locales are not interchangeable.** `en-GB` is not `en-US`; British spelling matters for users.
- **Script matters for Chinese.** `zh-Hans` (Simplified) vs `zh-Hant` (Traditional) — different character sets.
- **The cookie should not be domain-wide for multi-domain apps.** Set per-app or per-subdomain.

## Related

- `i18n/cldr-data-2026.md` — CLDR backing data
- `i18n/icu-message-format.md` — message format
- `i18n/hreflang-seo-2026.md` — SEO with subdirectory pattern
- `i18n/personal-name-formatting-2026.md` — name locale

## Source URLs (verified 2026-08-10)

- https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/LocaleMatcher — Intl.LocaleMatcher
- https://tc39.es/proposal-intl-locale-matching/ — TC39 proposal
- https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Accept-Language — Accept-Language spec
- https://www.rfc-editor.org/rfc/rfc4647 — RFC 4647 Matching of Language Tags
- https://www.w3.org/International/articles/language-tags/ — W3C language tags
- https://formatjs.io/docs/react-intl/components — FormatJS
- https://www.i18next.com/misc/creating-own-plugins.html#languagedetector — i18next language detector
- https://next-intl-docs.vercel.app/docs/routing/middleware — next-intl middleware
- https://docs.djangoproject.com/en/6.0/topics/i18n/translation/ — Django i18n
- https://lokalise.com/blog/the-ultimate-guide-to-internationalization-with-react-i18next-and-lokalise/ — react-i18next
