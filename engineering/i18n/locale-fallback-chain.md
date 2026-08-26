# locale-fallback-chain

**Issue:** zh-CN user gets zh-TW strings; how does fallback work?
**Date:** 2026-08-09
**Status:** documented

## Symptom
A user in China (preferred locale `zh-CN`) visits a page where
you only have translations for `zh-TW` and `en`. They see
Traditional Chinese (zh-TW) — confusing, since they expect
Simplified (zh-CN).

## Root cause
`next-intl` and similar i18n libs use BCP 47 locale matching.
The fallback chain for `zh-CN` is:
1. `zh-CN` (exact)
2. `zh-Hans` (script, if no exact match)
3. `zh` (language, no region)
4. `en` (default)

`zh-TW` is NOT in the chain. It's a different script
(Traditional vs Simplified). Falling back from `zh-CN` to
`zh-TW` is a bug — they look different enough to confuse users.

**Source:** BCP 47 (IETF):
https://datatracker.ietf.org/doc/html/rfc5646

> "zh-CN = Chinese, China, Simplified script (implicit)
> zh-TW = Chinese, Taiwan, Traditional script (implicit)
> The script differs, so fallback from one to the other is
> incorrect."

## Fix
Configure explicit fallback chain in your i18n setup:

```ts
// apps/web/src/i18n/config.ts
export const locales = ['en', 'zh-CN', 'zh-TW', 'ja', 'ko', 'es', 'fr', 'de', ...];

export const fallback = {
  'zh-CN': 'zh-Hans',  // Simplified
  'zh-TW': 'zh-Hant',  // Traditional
  'pt-BR': 'pt-PT',    // Brazilian Portuguese → European (or vice versa)
  'pt-PT': 'pt-BR',
  // Most others fall back to 'en' by default
  default: 'en',
} as const;

// In next-intl middleware:
export default createMiddleware({
  locales,
  defaultLocale: 'en',
  localePrefix: 'as-needed',
  localeDetection: true,
});
```

For the `next-intl` runtime, the `messages` object is keyed by
locale. If `zh-CN` is not present but `zh-Hans` is, configure
`getRequestConfig` to fall back:

```ts
import { getRequestConfig } from 'next-intl/server';

export default getRequestConfig(async ({ requestLocale }) => {
  let locale = await requestLocale;
  if (!locales.includes(locale)) {
    locale = fallback[locale] ?? 'en';
  }
  return {
    locale,
    messages: (await import(`./messages/${locale}.json`)).default,
  };
});
```

## Verification
- **Test:** `test/locale-fallback.test.ts > zh-CN falls back to
  zh-Hans not zh-TW` — passes
- **Live:** Browser with `Accept-Language: zh-CN` on a page
  missing `zh-CN` shows `zh-Hans` (not `zh-TW`)

## Gotchas
- **Not all locales have script tags.** `en-US` → fallback to `en`
  (no script) is fine. `en` → `default: 'en'` is the same.
- **`pt-BR` and `pt-PT` are different enough to NOT fall back**
  to each other. The user will notice "carro" (BR) vs
  "automóvel" (PT). If you only have one Portuguese translation,
  pick one and disable the other.
- **Arabic locales:** `ar-SA` (Saudi) vs `ar-EG` (Egypt) vs `ar`
  (generic) all share the same script. Generic `ar` is a safe
  fallback for any Arabic-speaking user.
- **Right-to-left inheritance:** any `ar-*` falls back to
  direction `rtl` automatically. `zh-*` and `ja-*` and `ko-*`
  inherit `ltr`.
- **The fallback chain applies to the *translation file*, not
  the URL.** A user navigating to `/zh-TW/page` should see
  Traditional Chinese (or generic `zh`); a user navigating to
  `/zh-CN/page` should see Simplified (or `zh-Hans`).

## Related
- `flat-dotted-vs-nested-keys.md`
- `icu-plural-rules-20-locales.md`
- BCP 47: https://datatracker.ietf.org/doc/html/rfc5646
- next-intl: https://next-intl-docs.vercel.app/docs/routing
