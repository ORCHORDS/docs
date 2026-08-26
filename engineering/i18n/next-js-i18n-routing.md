# next-js-i18n-routing

**Issue:** Configuring locale-aware routing in Next.js Pages Router
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Next.js Pages Router has built-in i18n routing that prefixes URLs with locale segments. Misconfiguration causes redirect loops or missing locale detection.

## Pattern / Solution
```js
// next.config.js
module.exports = {
  i18n: {
    locales: ['en', 'fr', 'de'],
    defaultLocale: 'en',
    localeDetection: true,
  },
};
```
Access locale in pages:
```tsx
import { useRouter } from 'next/router';
const { locale, locales, defaultLocale } = useRouter();
// Switch locale:
router.push(router.pathname, router.asPath, { locale: 'fr' });
```

## Gotchas
- `defaultLocale` URLs have no prefix (`/about` not `/en/about`) — handle hreflang accordingly
- `localeDetection: false` disables automatic redirect
- Middleware-based detection overrides `localeDetection` in `next.config.js`

## Related
- `next-js-app-router-i18n.md`
- `hreflang-seo-2026.md`
