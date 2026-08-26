# markdown-in-translations

**Issue:** Handling Markdown formatting inside translated strings
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Some UIs render translated strings as Markdown. Translators may remove or misplace Markdown syntax, breaking rendered output.

## Pattern / Solution
Preferred: avoid Markdown; use rich-text component interpolation:
```tsx
t('privacy_notice', { link: <a >Privacy Policy</a> })
```
If Markdown is unavoidable, document expected syntax in context notes:
```json
{
  "terms_notice": "By signing up you agree to our Privacy Policy and Terms.",
  "@terms_notice": { "comment": "Markdown link syntax. Variables: {privacyUrl}, {termsUrl}" }
}
```
Render:
```tsx
import ReactMarkdown from 'react-markdown';
<ReactMarkdown>{t('terms_notice', { privacyUrl: '/privacy', termsUrl: '/terms' })}</ReactMarkdown>
```

## Gotchas
- Square brackets used for Markdown links conflict with Japanese quotation brackets
- Strip Markdown before passing to screen readers using `remark-strip-markdown`
- Translators may translate link anchor text but must not translate URL variables

## Related
- `html-in-translations.md`
- `interpolation-patterns.md`
- `translation-context-notes.md`
