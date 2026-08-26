# translation-pipeline

**Issue:** Translation pipeline — source, build, deploy
**Date:** 2026-08-09
**Status:** documented

## Symptom
You have 20 locales. You update the English text. You
forget to update the other 19. The UI shows
mismatched text. Users complain.

## Root cause
**Translations drift.** Use a translation pipeline.

**Source:** Various i18n tools.

## The "translation files" pattern

For translation files, JSON per locale:
```
/locales
  /en
    common.json
  /fr
    common.json
  /es
    common.json
```

The files are per locale.

## The "namespaced" pattern

For namespaced files:
```
/locales
  /en
    common.json
    auth.json
    billing.json
  /fr
    common.json
    auth.json
    billing.json
```

The files are per namespace.

## The "key structure" pattern

For keys, dot-separated:
```json
{
  "auth.signup.title": "Sign up",
  "auth.signup.email_label": "Email",
  "auth.signin.title": "Sign in"
}
```

The keys are hierarchical.

## The "i18next" pattern

For i18next:
```ts
import i18n from 'i18next';
import en from './locales/en.json';
import fr from './locales/fr.json';

i18n.init({
  resources: { en: { translation: en }, fr: { translation: fr } },
  lng: 'en',
  fallbackLng: 'en',
  interpolation: { escapeValue: false },
});

i18n.t('auth.signup.title');  // "Sign up"
i18n.changeLanguage('fr');
i18n.t('auth.signup.title');  // "S'inscrire"
```

The library handles the loading.

**Source:** i18next:
https://www.i18next.com/

## The "extraction" pattern

For extraction, use a CLI:
```bash
# i18next-parser
npx i18next-parser 'src/**/*.{ts,tsx}'
```

The CLI extracts keys from code.

## The "missing key detection" pattern

For missing keys, fail CI:
```ts
// In tests
test('all keys are translated', () => {
  const en = require('./locales/en.json');
  const fr = require('./locales/fr.json');
  const missing = findMissingKeys(en, fr);
  expect(missing).toEqual([]);
});
```

The CI catches missing keys.

## The "translation service" pattern

For a translation service:
- **Crowdin:** Popular, free for OSS
- **Lokalise:** Mature
- **Phrase:** Mature
- **POEditor:** Simple

```ts
// Pull from Crowdin
npx crowdin pull
```

The service provides translation.

## The "machine translation" pattern

For machine translation (pre-fill):
- **DeepL:** Quality
- **Google Translate:** Free, OK
- **OpenAI:** Flexible

```ts
async function autoTranslate(text: string, targetLang: string, env: Env): Promise<string> {
  const response = await env.AI.run('@cf/meta/m2m100-1.2b', {
    text,
    source_lang: 'en',
    target_lang: targetLang,
  });
  return response.translated_text;
}
```

The text is pre-translated.

## The "translation memory" pattern

For translation memory, store the source + translation:
```sql
CREATE TABLE translation_memory (
  id TEXT PRIMARY KEY,
  source_text TEXT NOT NULL,
  target_lang TEXT NOT NULL,
  target_text TEXT NOT NULL,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

Reuse the past translations.

## The "build-time vs runtime" pattern

For build-time:
- **Pros:** Smaller bundle, faster runtime
- **Cons:** Rebuild per locale change

For runtime:
- **Pros:** Dynamic loading
- **Cons:** Larger bundle, network

For most apps, **build-time for default + runtime for
others**.

## The "lazy load" pattern

For lazy loading:
```ts
const fr = await import('./locales/fr.json');
i18n.addResourceBundle('fr', 'translation', fr.default);
```

The locale is loaded on demand.

## The "plural ICU" pattern

For ICU plurals:
```json
{
  "messages": "{count, plural, one {# message} other {# messages}}"
}
```

The ICU is in the JSON.

## The "translation anti-pattern" anti-patterns

### 1. Hard-coded strings
- **Issue:** Not translatable
- **Fix:** Use keys

### 2. No missing key check
- **Issue:** Mismatched text
- **Fix:** CI check

### 3. Inconsistent keys
- **Issue:** Hard to find
- **Fix:** Hierarchical

### 4. Stale translations
- **Issue:** Old text
- **Fix:** Translation memory + review

### 5. No plural support
- **Issue:** "1 messages"
- **Fix:** ICU MessageFormat

## Verification
- **Test:** Each locale renders
- **Test:** Missing keys fail
- **Test:** Plurals work
- **Live:** Locale coverage monitored
- **Audit:** Quarterly review

## Gotchas
- **The "hard-coded strings" anti-pattern.** Use keys.
- **The "no missing key check" anti-pattern.** CI.
- **The "stale translations" anti-pattern.** Review.

## Related
- `icu-messageformat-advanced.md`
- `icu-plural-rules-20-locales.md`
- `locale-fallback-chain.md`
- `feature-cookbook-localization.md`
- `data-i18n-marker-pattern.md`
- i18next: https://www.i18next.com/
- Crowdin: https://crowdin.com/
- DeepL: https://www.deepl.com/
