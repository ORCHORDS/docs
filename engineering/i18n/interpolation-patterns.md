# interpolation-patterns

**Issue:** Safely interpolating dynamic values into translated strings
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Concatenating translated fragments with dynamic values breaks grammar in inflected languages. Variable interpolation keeps the full sentence intact.

## Pattern / Solution
i18next style:
```json
{ "greeting": "Hello, {{name}}!" }
```
```js
t('greeting', { name: 'Aiko' }); // -> 'Hello, Aiko!'
```
ICU style:
```
Hello, {name}!
You have {count, plural, one{# message} other{# messages}}.
Your balance is {balance, number, ::currency/USD}.
```
React component interpolation:
```tsx
// en.json: "By signing up you agree to our <1>Terms</1>"
<Trans i18nKey="terms">
  By signing up you agree to our <a >Terms</a>
</Trans>
```

## Gotchas
- Always use named placeholders -- argument order differs by language
- HTML interpolation must be explicitly marked safe to prevent XSS
- ICU `select` and `plural` require the full message in one string -- do not split

## Related
- `json-translation-keys-best-practices.md`
- `html-in-translations.md`
- `icu-message-format.md`
