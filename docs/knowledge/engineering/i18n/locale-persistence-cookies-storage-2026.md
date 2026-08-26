# Locale Persistence: Cookies, Storage, URL (2026)

## Symptom

A user picks "Francais" from the language switcher. They refresh -- it
reverts to English. They log in -- it reverts. They open a deep link from
email -- it reverts. Or worse: the server renders French, the client
hydrates English, and React throws a hydration mismatch warning.

The root cause is inconsistent locale persistence strategy across
cookies, localStorage, sessionStorage, URL, and the user profile.

## The four sources of truth

1. **URL** (`/fr-FR/dashboard` or `?lang=fr`) -- the canonical source.
   Shareable, bookmarkable, indexable by search engines.
2. **Cookie** (`lng=fr-FR; Path=/; SameSite=Lax`) -- read by the server
   for SSR and by every subdomain. Survives refresh.
3. **localStorage** (`localStorage.setItem('lng', 'fr-FR')`) -- client
   only, large limit, not sent to server. Good for SPA fallback.
4. **User profile** (database column `preferred_locale`) -- the durable
   preference for authenticated users, overrides everything when present.

## Resolution order (recommended)

```
1. URL path/query param     (explicit, shareable)
2. User profile (if logged in)
3. Cookie                    (survives session)
4. localStorage              (SPA-only fallback)
5. Accept-Language header    (first visit)
6. Default locale            (last resort)
```

## Gotchas

- **SSR needs the cookie, not localStorage.** `localStorage` is undefined
  on the server. If you only persist to localStorage, the server cannot
  know the user's locale and will render the default -- causing hydration
  mismatch flash. Always set a cookie for SSR apps.
- **Hydration mismatch.** Server reads `Accept-Language` -> renders `en`.
  Client reads `localStorage` -> expects `fr`. React 18+ throws. Fix:
  set cookie on first response, render from cookie on both sides.
- **Cookie size limits.** Cookies are capped at ~4KB total per domain.
  Don't store the full message catalog in a cookie -- store the locale
  code only.
- **Subdomain leakage.** A cookie set on `app.example.com` is NOT visible
  on `marketing.example.com`. If you want cross-subdomain, set
  `Domain=.example.com`. But this also means the locale leaks to sibling
  apps that may not support it.
- **`SameSite=Lax` and redirect loops.** If your locale detection
   redirects `/` to `/fr/`, third-party links may hit a cookieless first
   request and redirect twice. Use a 302, not 301, and check for an
   existing cookie before redirecting.
- **localStorage throws in private mode.** Safari private browsing and
  some incognito modes throw on `localStorage.setItem`. Wrap in try/catch
  and fall back to cookie or in-memory.
- **URL locale vs cookie locale drift.** User shares `/de/product/123`
  with a friend whose cookie says `es`. Which wins? Convention: URL wins
  for the current page, but do NOT silently rewrite the cookie -- ask
  or surface a banner ("Switch to German?").
- **Authenticated users expect their preference everywhere.** If profile
  says `ja-JP` but they click an `en` link, persist the choice back to
  the profile asynchronously so next login keeps it.
- **Don't trust the client for routing security.** Locale in URL is
  display metadata, not auth. Never use it for access control.
- **Bots ignore cookies.** SEO crawlers won't carry your locale cookie
  across requests, so hreflang tags + URL-based locale are mandatory for
  indexed multilingual content.
- **Race condition on first paint.** If you read localStorage in a
  `useEffect` after mount, you get a flash of default-locale content.
  Read synchronously in a module-level IIFE or use a `<script>` in `<head>`
  to set `document.documentElement.lang` and `dir` before React mounts.

## Minimal cookie set snippet

```js
function persistLocale(locale) {
  document.documentElement.lang = locale;
  document.documentElement.dir = isRtl(locale) ? 'rtl' : 'ltr';
  document.cookie = `lng=${locale}; Path=/; Max-Age=31536000; SameSite=Lax`;
  try { localStorage.setItem('lng', locale); } catch {}
}
```

## Checklist

1. Pick ONE source of truth per request (URL > cookie > header > default).
2. Always set a cookie if you do SSR.
3. Sync profile preference for logged-in users.
4. Test the hydration path with cookies cleared.
5. Verify crawlers see correct hreflang (no cookie reliance).
