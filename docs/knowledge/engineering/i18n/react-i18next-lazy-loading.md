# react-i18next-lazy-loading

**Issue:** Loading translation files on demand instead of bundling all locales upfront
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Shipping all locale JSON in the main bundle inflates initial load time. The HTTP backend plugin fetches only the active locale at runtime.

## Pattern / Solution
```bash
npm i i18next-http-backend
```
```ts
import HttpBackend from 'i18next-http-backend';
i18n.use(HttpBackend).use(initReactI18next).init({
  lng: 'en', fallbackLng: 'en',
  ns: ['common', 'dashboard'],
  backend: { loadPath: '/locales/{{lng}}/{{ns}}.json' },
  react: { useSuspense: true },
});
```
Wrap with Suspense:
```tsx
<Suspense fallback={<Spinner />}><App /></Suspense>
```

## Gotchas
- `useSuspense: false` + manual `ready` check needed if Suspense is unavailable
- Cache-busting: add `queryStringParams: { v: BUILD_HASH }` to backend options
- CORS headers required when locales are served from a CDN origin

## Related
- `react-i18next-namespaces.md`
- `locale-fallback-chain.md`
