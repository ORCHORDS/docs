# Locale Negotiation on Cloudflare Pages with Accept-Language Header

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Your Cloudflare Pages app serves multiple locales but users who have never set a language preference land on the default English content even when their browser clearly signals `fr-CA` or `pt-BR`. You want the edge to detect the best-match locale from the `Accept-Language` header, redirect or rewrite to the appropriate locale path, and store the choice so later requests skip re-negotiation — all before a single byte of JavaScript runs in the browser.

## Context

Cloudflare Pages supports Workers-based middleware via `functions/_middleware.ts`. These files execute at the edge on every request, making them the ideal place to parse `Accept-Language`, run BCP 47 language matching, and either issue a `302` redirect or rewrite the request path. The key challenge is correctly implementing RFC 7231 quality-value (q-factor) parsing and CLDR-based language matching so that, for example, `fr-CA` falls back to `fr` before falling back to `en`, rather than defaulting immediately to English.

## Parsing Accept-Language with Q-Factor Weighting

The `Accept-Language` header contains a comma-separated list of language tags with optional `q` weights. Tags without an explicit `q` value have an implicit weight of `1.0`. Parse, sort descending by weight, then iterate until a supported locale matches.

```typescript
// functions/_middleware.ts
interface WeightedLocale {
  tag: string;
  q: number;
}

function parseAcceptLanguage(header: string): WeightedLocale[] {
  return header
    .split(",")
    .map((entry) => {
      const [rawTag, rawQ] = entry.trim().split(";");
      const tag = rawTag.trim().toLowerCase();
      const q = rawQ ? parseFloat(rawQ.replace(/q=/i, "").trim()) : 1.0;
      return { tag, q: isNaN(q) ? 1.0 : q };
    })
    .filter(({ tag }) => tag.length > 0 && tag !== "*")
    .sort((a, b) => b.q - a.q);
}

const SUPPORTED_LOCALES = ["en", "fr", "pt-BR", "de", "ja"] as const;
type SupportedLocale = (typeof SUPPORTED_LOCALES)[number];
const DEFAULT_LOCALE: SupportedLocale = "en";

/**
 * BCP 47 lookup: try exact match, then language-only subtag.
 * e.g. "fr-CA" → tries "fr-CA", then "fr".
 */
function bestMatchLocale(
  candidates: WeightedLocale[]
): SupportedLocale {
  for (const { tag } of candidates) {
    // Exact match (normalised to lower-case for comparison)
    const exact = SUPPORTED_LOCALES.find(
      (l) => l.toLowerCase() === tag
    );
    if (exact) return exact;

    // Language-only subtag fallback
    const lang = tag.split("-")[0];
    const langMatch = SUPPORTED_LOCALES.find(
      (l) => l.toLowerCase().split("-")[0] === lang
    );
    if (langMatch) return langMatch;
  }
  return DEFAULT_LOCALE;
}
```

## Redirect vs Cookie Persistence Strategy

On the first visit, issue a `302` redirect to the locale-prefixed path and set a `Locale` cookie so subsequent requests skip re-negotiation entirely. On middleware re-entry, read the cookie first; only parse `Accept-Language` when no cookie is present.

```typescript
// functions/_middleware.ts (continued)
const LOCALE_COOKIE = "preferred_locale";
const LOCALE_PATH_RE = /^\/(en|fr|pt-BR|de|ja)(\/|$)/;

export async function onRequest(context: EventContext<Env, string, unknown>) {
  const { request, next } = context;
  const url = new URL(request.url);

  // Skip static assets and API routes
  if (
    url.pathname.startsWith("/cdn-cgi/") ||
    url.pathname.startsWith("/api/")
  ) {
    return next();
  }

  // If the path already carries a locale prefix, persist the choice and continue
  const pathMatch = LOCALE_PATH_RE.exec(url.pathname);
  if (pathMatch) {
    const detectedLocale = pathMatch[1] as SupportedLocale;
    const response = await next();
    const mutable = new Response(response.body, response);
    mutable.headers.append(
      "Set-Cookie",
      `${LOCALE_COOKIE}=${detectedLocale}; Path=/; Max-Age=31536000; SameSite=Lax`
    );
    return mutable;
  }

  // 1. Cookie wins
  const cookie = request.headers.get("Cookie") ?? "";
  const cookieLocale = cookie
    .split(";")
    .map((c) => c.trim())
    .find((c) => c.startsWith(`${LOCALE_COOKIE}=`))
    ?.split("=")[1] as SupportedLocale | undefined;

  if (cookieLocale && (SUPPORTED_LOCALES as readonly string[]).includes(cookieLocale)) {
    url.pathname = `/${cookieLocale}${url.pathname}`;
    return Response.redirect(url.toString(), 302);
  }

  // 2. Accept-Language header
  const acceptHeader = request.headers.get("Accept-Language") ?? "en";
  const candidates = parseAcceptLanguage(acceptHeader);
  const locale = bestMatchLocale(candidates);

  url.pathname = `/${locale}${url.pathname}`;
  const redirectResp = Response.redirect(url.toString(), 302);
  const mutable = new Response(redirectResp.body, redirectResp);
  mutable.headers.append(
    "Set-Cookie",
    `${LOCALE_COOKIE}=${locale}; Path=/; Max-Age=31536000; SameSite=Lax`
  );
  return mutable;
}
```

## Handling Missing or Malformed Locale Gracefully

Never throw on an unrecognised locale. Treat parse failures as `q=1.0` so the first entry still participates in matching. When the entire header is absent or its value is `*`, return the default locale without crashing.

```typescript
// Defensive wrapper used in production
export function safeNegotiateLocale(
  acceptLanguageHeader: string | null
): SupportedLocale {
  if (!acceptLanguageHeader || acceptLanguageHeader.trim() === "") {
    return DEFAULT_LOCALE;
  }
  try {
    const candidates = parseAcceptLanguage(acceptLanguageHeader);
    if (candidates.length === 0) return DEFAULT_LOCALE;
    return bestMatchLocale(candidates);
  } catch {
    return DEFAULT_LOCALE;
  }
}

// Unit-testable pure function — no Workers API dependencies
// Test vectors:
// safeNegotiateLocale("fr-CA,fr;q=0.9,en;q=0.8") → "fr"
// safeNegotiateLocale("pt-BR;q=1.0,en;q=0.5")    → "pt-BR"
// safeNegotiateLocale("zh-TW,zh;q=0.9")           → "en"  (no zh support)
// safeNegotiateLocale(null)                        → "en"
```

## Anti-patterns

- Calling `Intl.LocaleMatcher` (not available in Workers runtime as of 2026) and crashing silently when it is undefined — implement BCP 47 matching manually or bundle a small polyfill.
- Redirecting on every request including `/favicon.ico` and `/_next/static/**`, causing redirect loops and inflating billing.
- Storing the negotiated locale only in a `sessionStorage` write from JS — the first HTML document fetch has already been served without locale context.
- Performing q-factor sorting with `>=` instead of `>`, causing ties to be resolved in parse order rather than stably.

## Gotchas

- Cloudflare strips `Vary: Accept-Language` responses from cache by default; add `Cache-Control: private` or set a cache rule that includes `Accept-Language` in the cache key if you serve locale-specific content without redirecting.
- When the app is deployed to a custom domain that also uses Cloudflare's shared cache, a missing `Vary` header can serve the wrong locale to users sharing the same edge node — always verify with `curl -sI` and check the `CF-Cache-Status` header.

## Verification

```bash
# Should redirect to /fr/...
curl -sI -H "Accept-Language: fr-CA,fr;q=0.9,en;q=0.8" \
  https://your-site.pages.dev/ | grep -E "location:|set-cookie:"

# Should redirect to /pt-BR/...
curl -sI -H "Accept-Language: pt-BR;q=1,en;q=0.3" \
  https://your-site.pages.dev/ | grep location

# Should use cookie preference, ignoring Accept-Language
curl -sI -H "Accept-Language: de" \
  -H "Cookie: preferred_locale=ja" \
  https://your-site.pages.dev/ | grep location

# Confirm Vary header is present on locale-prefixed pages
curl -sI https://your-site.pages.dev/en/ | grep -i vary
```

## Related

- `i18n/locale-negotiation-accept-language.md`
- `i18n/locale-url-routing-workers-middleware.md`
- `i18n/locale-persistence-cookies-storage-2026.md`
- `i18n/cloudflare-workers-geolocation-locale-routing.md`
- `i18n/i18n-content-fallback-chain-kv-workers.md`

## Sources

- https://developers.cloudflare.com/pages/functions/middleware/
- https://www.rfc-editor.org/rfc/rfc7231#section-5.3.5
- https://www.w3.org/International/articles/language-tags/
- https://unicode.org/reports/tr35/#LanguageMatching
