# next-js-app-router-i18n

**Issue:** Implementing i18n in Next.js App Router (no built-in locale routing)
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
App Router removed the built-in `i18n` config. Locale routing must be done via middleware and a `[lang]` dynamic segment.

## Pattern / Solution
```
app/[lang]/layout.tsx
app/[lang]/page.tsx
middleware.ts
```
```ts
// middleware.ts
import { match } from '@formatjs/intl-localematcher';
import Negotiator from 'negotiator';
const locales = ['en', 'fr', 'de'];
export function middleware(request) {
  const headers = { 'accept-language': request.headers.get('accept-language') ?? '' };
  const languages = new Negotiator({ headers }).languages();
  const locale = match(languages, locales, 'en');
  return Response.redirect(new URL(`/${locale}${request.nextUrl.pathname}`, request.url));
}
export const config = { matcher: ['/((?!_next|.*\\..*).*)'] };
```
```tsx
// app/[lang]/layout.tsx
export default function Layout({ children, params: { lang } }) {
  return <html lang={lang}>{children}</html>;
}
```

## Gotchas
- Keep middleware lightweight — no DB calls
- Static export requires pre-generating all locale variants via `generateStaticParams`

## Related
- `next-js-i18n-routing.md`
- `locale-detection-browser.md`
