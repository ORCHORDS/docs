# locale-negotiation

**Issue:** A user in Brazil sees an English page despite setting Portuguese as their browser language. The site serves en-US because no locale negotiation ran; Accept-Language was ignored.
**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

The browser sends `Accept-Language: pt-BR, pt;q=0.9, en;q=0.8`. The server has locales `en`, `de`, `fr`, `ja`. No negotiation runs; the server picks the default. The user sees English despite a stronger preference for Portuguese. Wrong language, wrong format, wrong currency.

## Root cause

Locale negotiation is the process of matching what the user wants against what the site offers. The browser signals preference through `Accept-Language`; the site has a set of supported locales. The two must be reconciled, with the user's preference weighted appropriately and the site's availability as a hard constraint.

Three layers, in order of priority:

1. **URL segment or subdomain.** `/en-US/about` or `us.example.com/about` — explicit, shareable, SEO-friendly.
2. **Cookie.** A previously chosen locale, persisted across sessions.
3. **`Accept-Language` header.** The browser's signal, weighted by quality factor.
4. **Default locale.** The fallback when nothing else matches.

The negotiation algorithm picks the highest-priority match across these layers. The implementation has two standard algorithms: `lookup` (RFC 4647) and `best fit` (ECMA-402).

## The negotiation algorithm choice

`lookup` (RFC 4647): progressively remove subtags from the user's `Accept-Language` until a match is found. `pt-BR` → `pt` → `*`. Simple, predictable, conservative.

`best fit` (ECMA-402): compare the user's accepted locales against the available locales by distance, taking into account regional information. `pt-BR` is closer to a site that has `pt-BR` than to a site that has `pt-PT`. The `best fit` algorithm can match `en-US` as the best locale even if the user sent `en-GB` and the site only supports `en` and `en-US`.

Recommendation: use `best fit` as the default. It is the ECMA-402 standard, and the `@formatjs/intl-localematcher` library implements it. Most libraries default to `best fit`; check yours.

## The Intl.LocaleMatcher API

The `Intl.LocaleMatcher.match(requestedLocales, availableLocales, defaultLocale, options)` API is part of the ECMA-402 proposal and is the standard way to negotiate:

```javascript
Intl.LocaleMatcher.match(
  ['pt-BR', 'pt', 'en'],     // what the user wants
  ['en', 'de', 'ja', 'fr'],  // what the site supports
  'en',                       // fallback
  { algorithm: 'best fit' }
)  // → 'en' (no Portuguese match; default)
```

The TC39 proposal is at Stage 1 as of 2026. Most runtimes have a polyfill via `@formatjs/intl-localematcher`. The polyfill is the production path today.

## The middleware pattern (Next.js example)

```typescript
// middleware.ts
import { match } from '@formatjs/intl-localematcher'
import Negotiator from 'negotiator'
import { NextRequest, NextResponse } from 'next/server'

const defaultLocale = 'en'
const locales = ['en', 'de', 'fr', 'ja', 'pt-BR']

function getLocale(request: NextRequest) {
  const acceptedLanguage = request.headers.get('accept-language') ?? undefined
  const headers = { 'accept-language': acceptedLanguage }
  const languages = new Negotiator({ headers }).languages()
  try {
    return match(languages, locales, defaultLocale)
  } catch {
    return defaultLocale  // malformed Accept-Language → default
  }
}

export function middleware(request: NextRequest) {
  const pathname = request.nextUrl.pathname
  const pathnameIsMissingLocale = locales.every(
    (locale) => !pathname.startsWith(`/${locale}/`) && pathname !== `/${locale}`
  )
  if (pathnameIsMissingLocale) {
    const locale = getLocale(request)
    return NextResponse.redirect(new URL(`/${locale}${pathname}`, request.url))
  }
}

export const config = {
  matcher: ['/((?!api|_next|_vercel|.*\\..*).*)'],
}
```

The matcher excludes API routes, static files, and the Next.js internal paths. The middleware runs once per page request.

## The four priority rules

When detecting the locale from a request, the priority order is:

1. **URL segment** — `/en-US/about` is explicit and overrides everything
2. **Cookie** — a previously detected locale the user accepted
3. **Accept-Language** — the browser signal, used if URL and cookie are absent
4. **Default** — the fallback when nothing matches

Updating the locale: visiting a prefixed route updates the cookie. This takes precedence over a previously matched locale and is updated on each explicit visit.

## The common bugs

**Trusting `Accept-Language` blindly without parsing.** The header is a weighted list with quality factors. `pt-BR;q=0.9,en;q=0.8` means Portuguese-Brazil is preferred but English is acceptable. The `negotiator` package parses this correctly. `request.headers.get('accept-language').split(',')` does not.

**Trusting `Accept-Language` when the user has explicitly chosen a locale.** Once the user picks a language in your UI, store it in a cookie. The next request should respect the cookie, not the browser's default. Otherwise, a Brazilian user with `Accept-Language: pt-BR` who switches to English in your UI gets reverted to Portuguese on the next request.

**Crashing on malformed Accept-Language.** Bots, proxies, and some browsers send garbage. Wrap the matcher in try/catch and fall back to the default locale.

**Not handling subdomain-based locales correctly.** For sites with per-locale subdomains (`de.example.com`, `fr.example.com`), the middleware must read the host header and match against the locale-domain mapping. `x-forwarded-host` first, then `host`.

**Setting the locale once per session, not per request.** Some implementations cache the negotiated locale in a singleton. This breaks when the user navigates to a different subdomain or a different URL prefix. The negotiation should run on every page request, with the cookie as the fast path.

## The SEO consideration

If your site is publicly indexed, locale-prefixed URLs are critical for SEO. Google uses the URL structure to determine the locale; an unprefixed URL with `hreflang` annotations works but is slower to rank.

The alternates pattern: every page declares all locale-prefixed variants via `<link rel="alternate" hreflang="...">`. The middleware sets these based on the supported locales.

## Verification

The tell that locale negotiation is working:

- A Brazilian user with `Accept-Language: pt-BR` gets Portuguese
- A Brazilian user who switches to English in the UI keeps English on subsequent requests (cookie wins)
- A user with no Accept-Language header gets the default locale
- A bot with malformed headers gets the default locale, not a 500

The tell it isn't:

- All users see English regardless of browser language
- A user who switches language in the UI gets reverted on next request
- The site crashes on bots with unusual headers
- The locale detection runs on every request, ignoring cookies

## Gotchas

- **Parse `Accept-Language` with a library, not string splitting.** Quality factors and weighted lists require a real parser.
- **Cookie overrides header.** Once the user chooses a locale explicitly, respect it on subsequent requests.
- **Wrap the matcher in try/catch.** Malformed headers happen; the fallback is the default locale, not a 500.
- **Run negotiation on every page request.** The URL or cookie may have changed; do not cache the result in a singleton.
- **URL segments are the most explicit and SEO-friendly form.** Use them when possible; cookies are a fallback.
- **The `best fit` algorithm handles regional proximity.** Use it instead of `lookup` for global sites with regional variants.

## Related

- `i18n/icu-message-format.md` — message formatting after locale is selected
- `i18n/timezone-iana-2026.md` — pairing locale with timezone
- `i18n/rtl-bidi-handling.md` — setting `dir` from the negotiated locale

## Source URLs (verified 2026-08-10)

- https://next-intl.dev/docs/routing/middleware
- https://github.com/tc39/proposal-intl-localematcher
- https://specification.website/spec/i18n/locale-content/
- https://medium.com/@cxkeeley/a-comprehensive-guide-to-internationalization-in-next-js-36d9db8db9c9
- https://stackoverflow.com/questions/77292174/intl-localematcher-in-next-js-rangeerror-incorrect-locale-information-provided
