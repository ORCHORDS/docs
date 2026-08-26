# Cloudflare Pages Redirects File Advanced Patterns

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your `_redirects` file only handles simple path rewrites, but you need conditional redirects based on query strings, country-level geofencing, language negotiation, or splat-preserving versioned URL migrations. Naïve line ordering causes silent rule shadowing, and some patterns that work in Netlify's syntax fail silently on Pages.

## Context

Cloudflare Pages processes `_redirects` at the edge before any Functions middleware. Rules are evaluated top-to-bottom and the first match wins. Pages supports HTTP status codes 301, 302, 303, 307, 308 and the special code 200 for proxying (splat rewrites). The file limit is 2 000 rules. For patterns that exceed the file's expressiveness — geo, cookie, header matching — you must use Pages Functions (`functions/_middleware.ts`). This article covers the full `_redirects` grammar and the middleware escape hatch.

---

## 1. Splat and Placeholder Basics

```
# _redirects
# Basic 301 permanent redirect
/old-path   /new-path   301

# Named placeholder — :segment captures one path segment
/blog/:slug  /posts/:slug  301

# Splat — * captures zero or more path segments (including slashes)
/docs/*  /v2/docs/:splat  301

# 200 proxy rewrite (invisible to the browser, no redirect)
/api/*   https://api-worker.workers.dev/:splat   200

# Force 302 for A/B test pages
/landing   /landing-variant-b   302
```

---

## 2. Version Migration with Splat Preservation

```
# Redirect all v1 docs to v2 keeping sub-paths intact
/v1/*   /v2/:splat   308

# Redirect versioned API paths, preserving query strings automatically
/api/v1/*   /api/v2/:splat   308

# Rename a top-level section preserving depth
/help/*   /support/:splat   301

# Redirect a renamed slug — must come BEFORE the wildcard rule or it shadows
/blog/how-to-use-widgets   /blog/widget-guide   301
/blog/*                    /blog/:splat          200
```

> Rule ordering matters: more specific rules must appear before wildcard rules that would match the same path.

---

## 3. Query String Matching (Pages-Specific)

```
# Pages supports query string conditions via ?param=value syntax
# Redirect legacy share links to new format
/share?id=:id   /p/:id   301

# Multiple conditions are AND-ed
/search?type=product&q=:q   /shop/search?query=:q   302

# Fallback for /share without a recognised param (must come after specific rules)
/share   /   302
```

Note: query string capture only works with the `:named` placeholder syntax. Glob `*` cannot appear in the query portion.

---

## 4. Country-Based Geofencing via Functions Middleware

```typescript
// functions/_middleware.ts
import type { PagesFunction } from '@cloudflare/workers-types';

const GEO_RULES: Array<{ country: string; from: string; to: string; status: 301 | 302 }> = [
  { country: 'DE', from: '/', to: '/de/', status: 302 },
  { country: 'FR', from: '/', to: '/fr/', status: 302 },
];

export const onRequest: PagesFunction = async ({ request, next }) => {
  const url = new URL(request.url);
  const country = request.cf?.country as string | undefined;

  for (const rule of GEO_RULES) {
    if (rule.country === country && url.pathname === rule.from) {
      // Don't redirect if user already has a locale cookie
      const cookies = request.headers.get('Cookie') ?? '';
      if (cookies.includes('locale=')) break;

      return Response.redirect(new URL(rule.to, url), rule.status);
    }
  }

  return next();
};
```

---

## 5. Language Negotiation Redirect

```typescript
// functions/_middleware.ts  (extend from above or combine)
const SUPPORTED_LOCALES = ['en', 'de', 'fr', 'es', 'ja'] as const;
type Locale = (typeof SUPPORTED_LOCALES)[number];

function negotiateLocale(acceptLanguage: string): Locale {
  const preferred = acceptLanguage
    .split(',')
    .map((s) => {
      const [lang, q = 'q=1'] = s.trim().split(';');
      return { lang: lang.trim().slice(0, 2).toLowerCase(), q: parseFloat(q.split('=')[1]) };
    })
    .sort((a, b) => b.q - a.q);

  for (const { lang } of preferred) {
    if (SUPPORTED_LOCALES.includes(lang as Locale)) return lang as Locale;
  }
  return 'en';
}

export const onRequest: PagesFunction = async ({ request, next }) => {
  const url = new URL(request.url);
  // Only intercept root path; skip if already localised
  if (url.pathname !== '/' || url.pathname.match(/^\/(en|de|fr|es|ja)\//)) {
    return next();
  }

  const accept = request.headers.get('Accept-Language') ?? '';
  const locale = negotiateLocale(accept);
  if (locale !== 'en') {
    return Response.redirect(new URL(`/${locale}/`, url), 302);
  }
  return next();
};
```

---

## 6. Redirect Audit: Detecting Shadowed Rules

```typescript
// scripts/validate-redirects.ts  (run in CI, not in Workers)
import { readFileSync } from 'fs';

const lines = readFileSync('public/_redirects', 'utf8')
  .split('\n')
  .map((l) => l.trim())
  .filter((l) => l && !l.startsWith('#'));

const rules = lines.map((line) => {
  const [from, to, status = '301'] = line.split(/\s+/);
  return { from, to, status: Number(status) };
});

const seen: string[] = [];
for (const rule of rules) {
  const shadower = seen.find((prev) => {
    // Naïve check: if a previous wildcard pattern matches the current 'from'
    const re = new RegExp('^' + prev.replace(/\*/g, '.*').replace(/:[^/]+/g, '[^/]+') + '$');
    return re.test(rule.from.split('?')[0]);
  });
  if (shadower) {
    console.warn(`Rule "${rule.from}" may be shadowed by earlier rule "${shadower}"`);
  }
  seen.push(rule.from.split('?')[0]);
}
console.log(`Validated ${rules.length} redirect rules.`);
```

```json
// package.json — add to CI
{
  "scripts": {
    "validate-redirects": "ts-node scripts/validate-redirects.ts"
  }
}
```

---

## Anti-patterns

- **Putting wildcard rules before specific rules** — `/*` as the first rule will match everything; Pages stops at the first match, so every more-specific rule below it is dead.
- **Using `200` status for external URLs** — the 200 (proxy) rewrite only works for same-origin paths or Workers routes you control; external domains require a real redirect code.
- **Exceeding 2 000 rules** — Pages silently ignores rules beyond the limit with no build error; consolidate using wildcards or move bulk rules to a middleware function.
- **Relying on `_redirects` for auth-gated paths** — the file runs before Functions but has no access to cookies or headers; use `_middleware.ts` for conditional logic.
- **Duplicate `from` paths** — only the first occurrence is used; duplicates are silently dropped.

## Gotchas

- The `_redirects` file must live in the **output directory** (e.g. `dist/` or `public/`), not the repo root. For frameworks that copy the `public/` folder, place it there; for custom build outputs check `wrangler pages deploy <dir>`.
- Query string parameters in `_redirects` are matched literally against the URL; URL-encoded characters (e.g. `%20`) do not match unencoded equivalents.
- Pages Functions middleware (`_middleware.ts`) runs **after** `_redirects`; if a `_redirects` rule matches first, the middleware never sees the request.
- The `308` (Permanent Redirect Preserving Method) is preferred over `301` for `POST` form submissions; use `301` only for `GET` navigations.
- The `:splat` placeholder in the destination is only populated when `*` appears in the source path; named placeholders (`:slug`) use their own names.

## Verification

```bash
# Preview locally with wrangler pages dev — it respects _redirects:
wrangler pages dev ./dist --compatibility-date=2026-01-01

# Test a redirect rule:
curl -sI http://localhost:8788/old-path | grep location
# Expect: location: /new-path

# Test splat preservation:
curl -sI http://localhost:8788/v1/guide/intro | grep location
# Expect: location: /v2/guide/intro

# Run the audit script:
npm run validate-redirects
```

## Related

- `cloudflare-pages-routes-json-spa-fallback.md`
- `cloudflare-pages-headers-csp-mobile.md`
- `cloudflare-pages-middleware-auth-gating.md`
- `edge-middleware-i18n-routing-cloudflare-pages.md`
- `workers-signed-exchanges-sxg-pages.md`

## Sources

- https://developers.cloudflare.com/pages/configuration/redirects/
- https://developers.cloudflare.com/pages/functions/middleware/
- https://developers.cloudflare.com/pages/configuration/headers/
- https://httpwg.org/specs/rfc9110.html#status.308
