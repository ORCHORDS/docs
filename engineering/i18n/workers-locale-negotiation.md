# Locale Negotiation Algorithm in Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Worker needs to pick one canonical locale for each request from a combination of signals: a URL path prefix (`/fr/`), a `locale` cookie, and the `Accept-Language` header. Without a principled algorithm you get inconsistent language selection, users who set a preference being overridden by the browser header, and cache-busting from unmatched subtags. You also need to redirect bare paths (`/`) to the negotiated locale URL and store the result in KV so repeat requests skip re-negotiation.

## Context

Locale negotiation is described in BCP 47 (RFC 5646) and the related RFC 4647 (matching). The algorithm proceeds in priority order:

1. **URL path prefix** — explicit, user-controlled, cacheable.
2. **URL query parameter** (`?lang=fr`) — useful for shareable links.
3. **Cookie** (`locale=fr`) — persists the user's last explicit selection.
4. **`Accept-Language` header** — the browser's preference, quality-weighted.
5. **Default locale** — site-level fallback (e.g. `en`).

Matching follows BCP 47 lookup: try the full tag first, then progressively strip subtags (`zh-Hant-TW` → `zh-Hant` → `zh`). Never use `und` (undetermined) as a real locale.

## Solution

```typescript
// workers-locale-negotiation.ts
// Full locale negotiation for Cloudflare Workers with KV session caching

export interface Env {
  SESSION_KV: KVNamespace;  // stores negotiated locale per session ID
}

// ─── 1. Supported locales registry ───────────────────────────────────────

/** BCP 47 tags the site actively supports, in preference order. */
export const SUPPORTED_LOCALES: readonly string[] = [
  'en',       // default
  'de', 'de-AT', 'de-CH',
  'fr', 'fr-CA', 'fr-BE',
  'es', 'es-419', 'es-MX',
  'pt', 'pt-BR',
  'ar', 'ar-SA', 'ar-EG',
  'zh', 'zh-TW', 'zh-HK',
  'ja', 'ko',
  'he', 'fa', 'ur',
];

export const SUPPORTED_SET = new Set(SUPPORTED_LOCALES);
export const DEFAULT_LOCALE = 'en';

// ─── 2. Accept-Language parser ────────────────────────────────────────────

export interface LangTag {
  tag: string;
  q: number;
}

export function parseAcceptLanguage(header: string | null): LangTag[] {
  if (!header) return [];
  return header
    .split(',')
    .map((part) => {
      const trimmed = part.trim();
      const semicolon = trimmed.indexOf(';q=');
      if (semicolon === -1) return { tag: trimmed, q: 1.0 };
      return {
        tag: trimmed.slice(0, semicolon),
        q:   parseFloat(trimmed.slice(semicolon + 3)) || 0,
      };
    })
    .filter(({ tag }) => tag && tag !== '*' && tag !== 'und')
    .sort((a, b) => b.q - a.q);
}

// ─── 3. BCP 47 lookup matching ────────────────────────────────────────────

/**
 * Implements RFC 4647 §3.4 "Lookup" scheme.
 * Tries the full tag, then strips rightmost subtag until a match or empty.
 *
 * @returns matched locale from supported set, or null
 */
export function lookupLocale(
  tag: string,
  supported: Set<string>
): string | null {
  let candidate = tag.replace(/_/g, '-'); // normalise underscore
  while (candidate.length > 0) {
    if (supported.has(candidate)) return candidate;
    const lastDash = candidate.lastIndexOf('-');
    if (lastDash === -1) break;
    candidate = candidate.slice(0, lastDash);
  }
  return null;
}

/**
 * Matches a list of preferred tags (sorted by q-value) against the
 * supported locale set. Returns the first match or the default locale.
 */
export function negotiateFromList(
  preferred: LangTag[],
  supported: Set<string>,
  defaultLocale: string
): string {
  for (const { tag } of preferred) {
    const match = lookupLocale(tag, supported);
    if (match) return match;
  }
  return defaultLocale;
}

// ─── 4. Full negotiation with priority chain ──────────────────────────────

export interface NegotiationResult {
  locale: string;
  source: 'url-path' | 'url-query' | 'cookie' | 'header' | 'default';
  redirect?: string;  // set when the request should redirect to a localized URL
}

/**
 * Runs the full priority chain and returns the negotiated locale
 * plus redirect target when applicable.
 */
export function negotiateLocale(
  request: Request,
  supported: Set<string>,
  defaultLocale: string
): NegotiationResult {
  const url = new URL(request.url);
  const segments = url.pathname.split('/').filter(Boolean);

  // Priority 1: URL path prefix  /fr/about → 'fr'
  if (segments.length > 0 && supported.has(segments[0])) {
    return { locale: segments[0], source: 'url-path' };
  }

  // Priority 2: URL query parameter  ?lang=fr
  const queryLang = url.searchParams.get('lang');
  if (queryLang) {
    const match = lookupLocale(queryLang, supported);
    if (match) {
      // Clean the ?lang= param and redirect to path-prefixed URL
      url.searchParams.delete('lang');
      url.pathname = `/${match}${url.pathname}`;
      return { locale: match, source: 'url-query', redirect: url.toString() };
    }
  }

  // Priority 3: Cookie
  const cookieLang = parseCookie(request.headers.get('Cookie'), 'locale');
  if (cookieLang) {
    const match = lookupLocale(cookieLang, supported);
    if (match) {
      return {
        locale: match,
        source: 'cookie',
        redirect: `/${match}${url.pathname}${url.search}`,
      };
    }
  }

  // Priority 4: Accept-Language header
  const parsed = parseAcceptLanguage(request.headers.get('Accept-Language'));
  const headerLocale = negotiateFromList(parsed, supported, defaultLocale);
  if (headerLocale !== defaultLocale) {
    return {
      locale: headerLocale,
      source: 'header',
      redirect: `/${headerLocale}${url.pathname}${url.search}`,
    };
  }

  // Priority 5: Default
  return {
    locale: defaultLocale,
    source: 'default',
    redirect: `/${defaultLocale}${url.pathname}${url.search}`,
  };
}

// ─── 5. KV session caching ───────────────────────────────────────────────

const SESSION_TTL = 60 * 60 * 24 * 30; // 30 days

/** Reads the session's stored locale from KV. */
export async function getSessionLocale(
  kv: KVNamespace,
  sessionId: string
): Promise<string | null> {
  return kv.get(`session-locale:${sessionId}`);
}

/** Persists the negotiated locale for the session. */
export async function setSessionLocale(
  kv: KVNamespace,
  sessionId: string,
  locale: string
): Promise<void> {
  await kv.put(`session-locale:${sessionId}`, locale, { expirationTtl: SESSION_TTL });
}

// ─── 6. Worker handler ────────────────────────────────────────────────────

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const sessionId = parseCookie(request.headers.get('Cookie'), 'session_id');

    // Fast path: KV already has a locale for this session
    if (sessionId) {
      const cached = await getSessionLocale(env.SESSION_KV, sessionId);
      if (cached) {
        // Still validate the URL has the prefix; redirect if missing
        const url = new URL(request.url);
        const segments = url.pathname.split('/').filter(Boolean);
        if (segments[0] !== cached) {
          return Response.redirect(`/${cached}${url.pathname}${url.search}`, 302);
        }
        return fetch(request); // pass through to origin
      }
    }

    // Full negotiation
    const { locale, source, redirect } = negotiateLocale(
      request,
      SUPPORTED_SET,
      DEFAULT_LOCALE
    );

    // Persist to KV for future requests
    const effectiveSessionId = sessionId ?? crypto.randomUUID();
    await setSessionLocale(env.SESSION_KV, effectiveSessionId, locale);

    // Redirect to localized URL when needed
    if (redirect) {
      const headers = new Headers({ Location: redirect });
      if (!sessionId) {
        headers.set(
          'Set-Cookie',
          `session_id=${effectiveSessionId}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${SESSION_TTL}`
        );
      }
      return new Response(null, { status: 302, headers });
    }

    // URL already has locale prefix — pass through
    const response = await fetch(request);
    const headers = new Headers(response.headers);
    headers.set('Vary', 'Accept-Language, Cookie');
    headers.set('X-Locale', locale);
    headers.set('X-Locale-Source', source);
    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers,
    });
  },
};

// ─── 7. Utilities ─────────────────────────────────────────────────────────

function parseCookie(header: string | null, name: string): string | null {
  if (!header) return null;
  const re = new RegExp(`(?:^|;\\s*)${escapeRegex(name)}=([^;]*)`);
  const m = header.match(re);
  return m ? decodeURIComponent(m[1]) : null;
}

function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// ─── 8. Fallback chain helper (for zh-TW → zh → en patterns) ─────────────

/**
 * Builds the full fallback chain for a given locale tag.
 * Useful for loading translation files with graceful degradation.
 *
 * @example fallbackChain('zh-TW', 'en') => ['zh-TW', 'zh', 'en']
 */
export function fallbackChain(locale: string, defaultLocale: string): string[] {
  const chain: string[] = [];
  let candidate = locale.replace(/_/g, '-');
  while (candidate.length > 0) {
    chain.push(candidate);
    const lastDash = candidate.lastIndexOf('-');
    if (lastDash === -1) break;
    candidate = candidate.slice(0, lastDash);
  }
  if (!chain.includes(defaultLocale)) chain.push(defaultLocale);
  return chain;
}
// fallbackChain('zh-Hant-TW', 'en') => ['zh-Hant-TW', 'zh-Hant', 'zh', 'en']
```

## Implementation Details

**Priority ordering** — URL path prefix is the highest priority because it is explicit (the user typed or followed a URL), is crawlable by search engines, and is the foundation for separate CDN cache keys per locale. Cookie beats `Accept-Language` because it reflects a previous explicit user choice (e.g. a language switcher click).

**BCP 47 lookup vs. filtering** — RFC 4647 defines two matching schemes: *filtering* (returns all matching locales) and *lookup* (returns the best single match). Lookup is correct for selecting a single site locale. The `lookupLocale` function above implements the Lookup algorithm by stripping subtags rightward.

**KV session caching** — Re-running the full negotiation algorithm on every request is cheap (< 1 ms), but the KV read adds ~1–3 ms. The trade-off is worthwhile: it eliminates the round-trip redirect on every request after the first, which saves a full RTT for returning users.

**`Vary` header** — Setting `Vary: Accept-Language, Cookie` ensures Cloudflare's CDN stores separate cache entries for each locale variant and never serves the wrong language to cached responses. Be careful: a highly variable `Accept-Language` header can fragment the cache excessively. The redirect-to-locale-URL pattern sidesteps this by making the URL the cache key.

**`zh-TW` → `zh` fallback** — Traditional Chinese users (`zh-TW`, `zh-HK`) should fall back to `zh` (Simplified), not `en`. The fallback chain in `fallbackChain()` handles this. However, `zh` and `zh-TW` are not mutually intelligible, so it is better to support both explicitly in `SUPPORTED_LOCALES`.

## Anti-patterns

- **Do not** use `navigator.language` in a Worker — it is a browser API, not available in the Workers runtime.
- **Do not** do case-sensitive locale comparison — `Accept-Language` tags may arrive in any case (`EN`, `en-us`, `EN-US`). Normalise with `.toLowerCase()` before matching.
- **Do not** redirect on every request — cache the negotiated locale in KV and use `X-Locale` headers for analytics; only redirect once per session.
- **Do not** store locale solely in a session cookie without a path-prefix strategy — locale-specific content will be cached under the same URL by CDN and served to all locales.

## Gotchas

- Chrome sometimes sends `Accept-Language: en-US,en;q=0.9` even when the OS is set to French. This is a known Chrome behavioural quirk in some enterprise configurations; always honour the cookie over the header.
- The `?lang=` query parameter is useful for machine-generated URLs (emails, ads) but should be consumed and converted to a redirect — leave it in the URL and CDN caches will fragment per value.
- `zh-TW` and `zh-Hant-TW` are both valid representations of Traditional Chinese (Taiwan). Normalise incoming tags and add both to `SUPPORTED_SET` or rely on the subtag-stripping algorithm.
- Some subsets of Accept-Language parsing libraries interpret `;` as a tag separator rather than a parameter separator, producing malformed tags. The parser above handles the raw header format correctly.

## Verification

```typescript
import { describe, it, expect } from 'vitest';
import {
  parseAcceptLanguage, lookupLocale, negotiateFromList, fallbackChain
} from './workers-locale-negotiation';

const SUPPORTED = new Set(['en', 'de', 'fr', 'zh', 'zh-TW', 'ar']);

describe('parseAcceptLanguage', () => {
  it('parses multiple tags with q-values', () => {
    const r = parseAcceptLanguage('fr-CH, fr;q=0.9, en;q=0.8, de;q=0.7');
    expect(r[0].tag).toBe('fr-CH');
    expect(r[0].q).toBe(1.0);
    expect(r[1].tag).toBe('fr');
  });
  it('filters wildcard and und', () => {
    const r = parseAcceptLanguage('*,und;q=0.1,en');
    expect(r.map((x) => x.tag)).not.toContain('*');
    expect(r.map((x) => x.tag)).not.toContain('und');
  });
});

describe('lookupLocale', () => {
  it('matches exact tag', () => expect(lookupLocale('zh-TW', SUPPORTED)).toBe('zh-TW'));
  it('strips to parent zh', () => expect(lookupLocale('zh-Hant-TW', SUPPORTED)).toBe('zh'));
  it('returns null for unsupported', () => expect(lookupLocale('ja', SUPPORTED)).toBeNull());
  it('normalises underscores', () => expect(lookupLocale('fr_BE', SUPPORTED)).toBe('fr'));
});

describe('fallbackChain', () => {
  it('zh-TW chain includes zh and en', () =>
    expect(fallbackChain('zh-TW', 'en')).toEqual(['zh-TW', 'zh', 'en'])
  );
  it('en chain is just [en]', () =>
    expect(fallbackChain('en', 'en')).toEqual(['en'])
  );
});
```

## Related

- `documentation/categories/i18n/workers-rtl-layout-detection.md` — applying RTL direction after locale is negotiated
- `documentation/categories/i18n/hreflang-sitemap-generation.md` — generating alternate URLs for each supported locale
- `documentation/categories/i18n/workers-icu-plural-rules.md` — using the negotiated locale for plural form selection

## Sources

- RFC 5646 — Tags for Identifying Languages: https://www.rfc-editor.org/rfc/rfc5646
- RFC 4647 — Matching of Language Tags: https://www.rfc-editor.org/rfc/rfc4647
- W3C Language negotiation: https://www.w3.org/International/questions/qa-lang-negotiation
- Cloudflare Workers KV: https://developers.cloudflare.com/kv/
- BCP 47 subtag registry: https://www.iana.org/assignments/language-subtag-registry
