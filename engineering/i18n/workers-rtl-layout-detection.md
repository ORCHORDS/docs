# RTL Language Detection and Layout Switching in Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your global e-commerce or SaaS product serves Arabic, Hebrew, Persian, and Urdu speakers. Without RTL detection at the edge, LTR-only layouts are served to right-to-left users: text alignment, flex direction, and icon placement all break. You need the Worker to detect RTL locales, inject the correct `dir` attribute, load RTL-specific CSS, and handle bidirectional text in transactional emails — all without a round-trip to the origin.

## Context

Cloudflare Workers run at the edge before the response reaches the browser. The `Accept-Language` header carries the user's preferred language; `Intl.Locale` (available in the V8 engine Workers ship) exposes `textInfo.direction` for programmatic direction detection. `HTMLRewriter` allows streaming injection of `dir="rtl"` and stylesheet `<link>` tags into any HTML response without buffering the full body.

RTL languages by BCP 47 subtag (primary language only):

| Language | Tag  | Script   |
|----------|------|----------|
| Arabic   | `ar` | Arab     |
| Hebrew   | `he` | Hebr     |
| Persian  | `fa` | Arab     |
| Urdu     | `ur` | Arab     |
| Yiddish  | `yi` | Hebr     |
| Pashto   | `ps` | Arab     |

## Solution

```typescript
// workers-rtl-layout-detection.ts
// Cloudflare Worker — RTL detection, HTMLRewriter injection, email dir handling

import { HTMLRewriter } from '@cloudflare/workers-types';

export interface Env {
  RTL_CSS_BUCKET: R2Bucket;   // optional: serve locale-specific CSS from R2
  LOCALE_KV: KVNamespace;     // cache negotiated locale per session cookie
}

// ─── 1. Direction resolution ──────────────────────────────────────────────

/** Returns 'rtl' | 'ltr' for a BCP 47 locale string. */
export function getTextDirection(locale: string): 'rtl' | 'ltr' {
  try {
    // Intl.Locale.prototype.textInfo is Stage-3 / available in V8 >= 9.6
    const info = (new Intl.Locale(locale) as any).textInfo;
    if (info?.direction === 'rtl') return 'rtl';
  } catch {
    // fall through to manual list
  }
  // Fallback manual allowlist (primary language subtag only)
  const RTL_LANGS = new Set(['ar', 'he', 'fa', 'ur', 'yi', 'ps', 'sd', 'dv']);
  const primary = locale.split('-')[0].toLowerCase();
  return RTL_LANGS.has(primary) ? 'rtl' : 'ltr';
}

// ─── 2. Accept-Language parsing ───────────────────────────────────────────

/** Parses Accept-Language header and returns locales sorted by q-value. */
export function parseAcceptLanguage(header: string | null): string[] {
  if (!header) return [];
  return header
    .split(',')
    .map((part) => {
      const [tag, q] = part.trim().split(';q=');
      return { tag: tag.trim(), q: q ? parseFloat(q) : 1.0 };
    })
    .filter(({ tag }) => tag && tag !== '*')
    .sort((a, b) => b.q - a.q)
    .map(({ tag }) => tag);
}

/** Picks the first locale whose primary language matches a supported set. */
export function negotiateLocale(
  preferred: string[],
  supported: Set<string>
): string {
  for (const tag of preferred) {
    if (supported.has(tag)) return tag;
    const primary = tag.split('-')[0];
    if (supported.has(primary)) return primary;
  }
  return 'en'; // default fallback
}

// ─── 3. HTMLRewriter handlers ─────────────────────────────────────────────

class HtmlDirInjector implements HTMLRewriterElementContentHandlers {
  constructor(
    private direction: 'rtl' | 'ltr',
    private locale: string
  ) {}

  element(el: Element) {
    // Set dir and lang on the root <html> element
    el.setAttribute('dir', this.direction);
    el.setAttribute('lang', this.locale);
  }
}

class RtlStylesheetInjector implements HTMLRewriterElementContentHandlers {
  constructor(
    private direction: 'rtl' | 'ltr',
    private cdnBase: string
  ) {}

  element(el: Element) {
    if (this.direction === 'rtl') {
      // Append RTL override stylesheet before </head>
      el.prepend(
        `<link rel="stylesheet"  />
<link rel="preload"  as="style" />
`,
        { html: true }
      );
    }
  }
}

// ─── 4. Main Worker fetch handler ─────────────────────────────────────────

const SUPPORTED_LOCALES = new Set([
  'en', 'ar', 'ar-SA', 'ar-EG', 'he', 'fa', 'ur', 'de', 'fr', 'es', 'ja', 'zh',
]);

const CDN_BASE = 'https://cdn.example.com/assets';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // ── Priority 1: URL path prefix  /ar/…  /he/…
    const pathLocale = url.pathname.split('/')[1];
    // ── Priority 2: Cookie
    const cookieLocale = getCookieValue(request.headers.get('Cookie'), 'locale');
    // ── Priority 3: Accept-Language
    const headerLocales = parseAcceptLanguage(
      request.headers.get('Accept-Language')
    );
    const headerLocale = negotiateLocale(headerLocales, SUPPORTED_LOCALES);

    const locale =
      (SUPPORTED_LOCALES.has(pathLocale) ? pathLocale : null) ??
      (cookieLocale && SUPPORTED_LOCALES.has(cookieLocale) ? cookieLocale : null) ??
      headerLocale;

    const direction = getTextDirection(locale);

    // Fetch from origin
    const response = await fetch(request);
    const contentType = response.headers.get('Content-Type') ?? '';

    // Only rewrite HTML responses
    if (!contentType.includes('text/html')) {
      return response;
    }

    const rewritten = new HTMLRewriter()
      .on('html', new HtmlDirInjector(direction, locale))
      .on('head', new RtlStylesheetInjector(direction, CDN_BASE))
      .transform(response);

    // Propagate locale in Set-Cookie for subsequent requests
    const newHeaders = new Headers(rewritten.headers);
    if (!cookieLocale) {
      newHeaders.append(
        'Set-Cookie',
        `locale=${locale}; Path=/; Max-Age=31536000; SameSite=Lax`
      );
    }
    // Vary so CDN caches separate copies per direction
    newHeaders.set('Vary', 'Accept-Language');

    return new Response(rewritten.body, {
      status: rewritten.status,
      statusText: rewritten.statusText,
      headers: newHeaders,
    });
  },
};

// ─── 5. Bidirectional email template helper ───────────────────────────────

/**
 * Wraps an email HTML body with correct dir/lang attributes and
 * injects a minimal RTL reset for email clients that ignore <html dir>.
 */
export function wrapEmailBody(
  bodyHtml: string,
  locale: string
): string {
  const dir = getTextDirection(locale);
  const rtlReset =
    dir === 'rtl'
      ? `<style>
  body, table, td, p, a, li, blockquote {
    direction: rtl !important;
    text-align: right !important;
  }
  /* Outlook-specific reset */
  [dir="rtl"] .outlook-fix { mso-table-lspace: 0pt; mso-table-rspace: 0pt; }
</style>`
      : '';

  return `<!DOCTYPE html>
<html dir="${dir}" lang="${locale}" xmlns="http://www.w3.org/1999/xhtml">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  ${rtlReset}
</head>
<body style="direction:${dir};text-align:${dir === 'rtl' ? 'right' : 'left'}">
  ${bodyHtml}
</body>
</html>`;
}

// ─── 6. Cookie utility ────────────────────────────────────────────────────

function getCookieValue(
  cookieHeader: string | null,
  name: string
): string | null {
  if (!cookieHeader) return null;
  const match = cookieHeader.match(new RegExp(`(?:^|;\\s*)${name}=([^;]*))`));
  return match ? decodeURIComponent(match[1]) : null;
}
```

## Implementation Details

**`Intl.Locale.textInfo.direction`** — The `textInfo` property is part of the Intl Locale Info proposal (Stage 3). Workers running V8 >= 9.6 support it natively. The manual allowlist fallback handles edge runtimes that do not yet ship the proposal.

**HTMLRewriter streaming** — `HTMLRewriter` processes the response body as a stream; the Worker never buffers the full HTML document in memory. Both the `<html>` and `<head>` handlers are registered separately: the `<html>` handler fires first (open tag), allowing `dir`/`lang` to appear in the raw source before the browser's HTML parser reads any content.

**RTL CSS architecture** — Maintain two stylesheet outputs from your build tool:
- `main.css` — LTR base styles.
- `rtl-overrides.css` — Uses `[dir="rtl"]` selectors to flip `margin-inline-start/end`, `border-inline-*`, flex direction, and `float` values. Logical CSS properties (`margin-inline-start` instead of `margin-left`) reduce the size of the override sheet.

**Email clients** — Many email clients strip `<html dir>` and CSS classes. The inline `style` attribute on `<body>` and the `!important` reset inside `<style>` are the most reliable bidirectional anchors across Gmail, Outlook, and Apple Mail.

**Cache** — The `Vary: Accept-Language` response header causes Cloudflare's CDN cache to store separate copies for each unique `Accept-Language` value. For high-traffic routes, also key by the `locale` cookie to avoid serving the wrong direction to cached responses.

## Anti-patterns

- **Do not** use `dir="auto"` on `<html>` — it relies on the browser scanning the first strongly-directional character, which can change per-paragraph and is unreliable for mixed-content pages.
- **Do not** hardcode RTL detection to `ar` only; Persian (`fa`) and Urdu (`ur`) share the Arabic script but are distinct BCP 47 primary languages.
- **Do not** load RTL CSS via JavaScript after paint — it causes a flash of incorrectly-laid-out content (FOILC) that disrupts Arabic users far more than an equivalent FOUC in LTR layouts.
- **Do not** set `text-align: right` as a substitute for `direction: rtl` — this breaks list markers, inline elements, and form controls.

## Gotchas

- `Intl.Locale` throws on malformed tags (e.g. `"en_US"` with underscore instead of hyphen). Always wrap in `try/catch`.
- The `Accept-Language` header can contain `*` as a wildcard entry; filter it out before tag matching.
- Some browsers send `he-IL` while your supported set contains only `he`. The `negotiateLocale` function handles this with primary-subtag fallback.
- Cloudflare's `HTMLRewriter` `.on('html', …)` fires on the *opening* `<html>` tag. If the origin already sets `dir`, the `setAttribute` call overwrites it — this is intentional.
- Email clients that use Word rendering engine (Outlook 2007-2019 on Windows) require `mso-*` CSS properties for proper RTL table layout.

## Verification

```typescript
// Unit tests (Vitest / @cloudflare/vitest-pool-workers)
import { describe, it, expect } from 'vitest';
import { getTextDirection, parseAcceptLanguage, negotiateLocale } from './workers-rtl-layout-detection';

describe('getTextDirection', () => {
  it('returns rtl for Arabic', () => expect(getTextDirection('ar')).toBe('rtl'));
  it('returns rtl for ar-SA', () => expect(getTextDirection('ar-SA')).toBe('rtl'));
  it('returns rtl for Persian', () => expect(getTextDirection('fa')).toBe('rtl'));
  it('returns rtl for Hebrew', () => expect(getTextDirection('he')).toBe('rtl'));
  it('returns ltr for English', () => expect(getTextDirection('en')).toBe('ltr'));
  it('returns ltr for Japanese', () => expect(getTextDirection('ja')).toBe('ltr'));
});

describe('parseAcceptLanguage', () => {
  it('sorts by q-value', () => {
    const result = parseAcceptLanguage('en;q=0.9,ar;q=1.0,fr;q=0.8');
    expect(result).toEqual(['ar', 'en', 'fr']);
  });
  it('filters wildcard', () => {
    const result = parseAcceptLanguage('ar,*;q=0.1');
    expect(result).not.toContain('*');
  });
});

describe('negotiateLocale', () => {
  const supported = new Set(['en', 'ar', 'he']);
  it('matches exact tag', () => expect(negotiateLocale(['ar'], supported)).toBe('ar'));
  it('falls back to primary subtag', () => expect(negotiateLocale(['ar-SA'], supported)).toBe('ar'));
  it('falls back to en when no match', () => expect(negotiateLocale(['zh'], supported)).toBe('en'));
});
```

Manual smoke test: `curl -H 'Accept-Language: ar,en;q=0.5' https://worker.example.com/` — inspect response HTML for `<html dir="rtl" lang="ar">` and the RTL stylesheet `<link>` in `<head>`.

## Related

- `documentation/categories/i18n/workers-locale-negotiation.md` — full locale negotiation algorithm with KV session caching
- `documentation/categories/i18n/hreflang-sitemap-generation.md` — hreflang annotations for RTL/LTR URL variants
- `documentation/categories/i18n/workers-currency-formatting-intl.md` — locale-aware number formatting
- Cloudflare HTMLRewriter docs: https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/

## Sources

- Unicode CLDR language direction data: https://unicode-org.github.io/cldr-staging/charts/latest/supplemental/language_plural_rules.html
- Intl Locale Info proposal (textInfo): https://github.com/tc39/proposal-intl-locale-info
- W3C i18n: Structural markup and right-to-left text in HTML: https://www.w3.org/International/questions/qa-html-dir
- Cloudflare Workers HTMLRewriter: https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/
- Campaign Monitor RTL email guide: https://www.campaignmonitor.com/resources/guides/rtl-email-guide/
