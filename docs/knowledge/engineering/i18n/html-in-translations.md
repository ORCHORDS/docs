# html-in-translations

**Issue:** Safely including HTML markup inside translated strings
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Some translated strings need inline HTML (`<strong>`, `<a>`, `<br>`). Embedding raw HTML creates XSS risk if variables contain user input.

## Pattern / Solution
React component interpolation (safest):
```json
{ "accept_terms": "I accept the <terms>Terms of Service</terms>" }
```
```tsx
<Trans i18nKey="accept_terms">
  I accept the <a >Terms of Service</a>
</Trans>
```
Controlled HTML allowlist:
```js
import DOMPurify from 'dompurify';
const safe = DOMPurify.sanitize(t('notice'), {
  ALLOWED_TAGS: ['strong', 'em', 'a', 'br'],
  ALLOWED_ATTR: ['href'],
});
element.innerHTML = safe;
```

## Gotchas
- Never use `dangerouslySetInnerHTML` with unsanitized translator output
- `href` values inside translations can contain `javascript:` -- validate URLs
- `<Trans>` counts child elements by index; adding/removing JSX shifts indexes

## Related
- `markdown-in-translations.md`
- `interpolation-patterns.md`
