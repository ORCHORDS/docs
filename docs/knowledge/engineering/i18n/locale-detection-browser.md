# locale-detection-browser

**Issue:** Detecting the user's preferred locale in the browser
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Applications need to select the best available locale on first visit without requiring the user to set a preference manually.

## Pattern / Solution
Browser-side:
```js
const preferred = navigator.languages; // ['fr-CA', 'fr', 'en-US', 'en']
const single = navigator.language;     // 'fr-CA'

import { match } from '@formatjs/intl-localematcher';
const supported = ['en', 'fr', 'de', 'ja'];
const locale = match(preferred, supported, 'en');
```
Persist:
```js
localStorage.setItem('locale', locale);
const saved = localStorage.getItem('locale') ?? detectLocale();
```
Server-side middleware:
```ts
const acceptLang = request.headers.get('accept-language') ?? '';
import Negotiator from 'negotiator';
const langs = new Negotiator({ headers: { 'accept-language': acceptLang } }).languages();
```

## Gotchas
- `navigator.languages` may return private locale -- always allow user override
- `Accept-Language` can be spoofed or absent in API clients
- CDN language detection cookies (Cloudflare) override server logic -- coordinate or disable

## Related
- `locale-negotiation-accept-language.md`
- `locale-fallback-chain.md`
- `next-js-app-router-i18n.md`
