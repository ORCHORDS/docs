# react-i18next-setup

**Issue:** Bootstrapping react-i18next in a React application
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
New React project needs i18n. `useTranslation` returns key strings instead of translated values because i18next was not initialized before the app renders.

## Pattern / Solution
```ts
// src/i18n.ts
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import en from './locales/en/common.json';
import fr from './locales/fr/common.json';

i18n.use(initReactI18next).init({
  resources: { en: { common: en }, fr: { common: fr } },
  lng: 'en',
  fallbackLng: 'en',
  defaultNS: 'common',
  interpolation: { escapeValue: false },
});

export default i18n;
```
Import before `<App />` in `main.tsx`:
```tsx
import './i18n';
import { createRoot } from 'react-dom/client';
createRoot(document.getElementById('root')!).render(<App />);
```
Use in components:
```tsx
const { t } = useTranslation('common');
return <h1>{t('welcome')}</h1>;
```

## Gotchas
- Import order matters: `i18n.ts` must run before any component that calls `useTranslation`
- `escapeValue: false` is safe only because React escapes JSX by default
- Missing `initReactI18next` plugin causes silent key pass-through

## Related
- `react-i18next-namespaces.md`
- `json-translation-keys-best-practices.md`
