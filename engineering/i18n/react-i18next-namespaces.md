# react-i18next-namespaces

**Issue:** Organizing translations into namespaces to avoid key collisions and enable code-splitting
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Large apps with hundreds of translation keys become hard to manage in a single JSON file. Namespaces partition keys by feature or page.

## Pattern / Solution
```
locales/en/common.json
locales/en/auth.json
locales/en/dashboard.json
```
Register in `i18n.init`:
```ts
i18n.init({
  ns: ['common', 'auth', 'dashboard'],
  defaultNS: 'common',
  resources: { en: { common: en, auth: auth } }
});
```
Per-component:
```tsx
const { t } = useTranslation('auth');
const { t: tc } = useTranslation(['auth', 'common']);
tc('auth:login.title');
tc('common:save');
```

## Gotchas
- Requesting an unregistered namespace logs a warning and returns the key
- `defaultNS` fallback only applies to calls without an explicit NS argument
- Namespace names are part of the public contract — rename with care

## Related
- `react-i18next-setup.md`
- `react-i18next-lazy-loading.md`
