# react-native-localization

**Issue:** Internationalizing React Native apps with runtime locale switching and plural rules
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Hardcoded English strings and missing plural forms cause app store rejections in non-English markets.

## Pattern / Solution
```sh
npm install react-i18next i18next
npm install @react-native-async-storage/async-storage  # for persisting locale
```

```ts
// i18n.ts
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import { getLocales } from 'react-native-localize';

const deviceLocale = getLocales()[0].languageCode; // e.g. 'fr'

i18n.use(initReactI18next).init({
  lng: deviceLocale,
  fallbackLng: 'en',
  resources: {
    en: { translation: { greeting: 'Hello {{name}}', item_count: '{{count}} item', item_count_other: '{{count}} items' } },
    fr: { translation: { greeting: 'Bonjour {{name}}', item_count: '{{count}} élément', item_count_other: '{{count}} éléments' } },
  },
  interpolation: { escapeValue: false },
});

export default i18n;
```

```jsx
import { useTranslation } from 'react-i18next';

function Screen() {
  const { t, i18n } = useTranslation();
  return (
    <>
      <Text>{t('greeting', { name: 'Alice' })}</Text>
      <Text>{t('item_count', { count: 3 })}</Text>
      <Button title="Switch to FR" onPress={() => i18n.changeLanguage('fr')} />
    </>
  );
}
```

## Gotchas
- RTL layouts require `I18nManager.forceRTL(true)` + app restart on React Native
- `react-native-localize` must be linked natively; Expo users should use `expo-localization`
- Lazy loading translation files avoids bundling all languages — use `i18next-http-backend`
- Pluralization rules differ per language; always use the `_other` key as the fallback

## Related
- `react-native-accessibility.md`
- `mobile-gdpr-mobile.md`
