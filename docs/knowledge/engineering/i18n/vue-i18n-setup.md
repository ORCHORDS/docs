# vue-i18n-setup

**Issue:** Setting up Vue I18n v9+ in a Vue 3 / Vite project
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Vue 3 with Composition API requires Vue I18n v9+. Legacy Options API syntax causes TypeScript errors and missing reactivity.

## Pattern / Solution
```bash
npm i vue-i18n@9
```
```ts
// src/i18n.ts
import { createI18n } from 'vue-i18n';
import en from './locales/en.json';
import ja from './locales/ja.json';
export const i18n = createI18n({
  legacy: false,
  locale: 'en',
  fallbackLocale: 'en',
  messages: { en, ja },
});
```
```ts
// main.ts
createApp(App).use(i18n).mount('#app');
```
```vue
<script setup>
import { useI18n } from 'vue-i18n';
const { t, locale } = useI18n();
</script>
<template>
  <p>{{ t('greeting') }}</p>
  <button @click="locale = 'ja'">日本語</button>
</template>
```

## Gotchas
- `legacy: true` enables `$t()` global but disables Composition API `useI18n()`
- `fallbackLocale` chain: `['fr-CA', 'fr', 'en']` tries each in order

## Related
- `json-translation-keys-best-practices.md`
- `locale-fallback-chain.md`
