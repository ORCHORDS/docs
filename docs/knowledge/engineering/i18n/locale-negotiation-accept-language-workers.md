# Content Negotiation from `Accept-Language` Header in a Cloudflare Worker

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Worker serves internationalised content and needs to pick the best supported locale from the browser's `Accept-Language` header without relying on a client-side cookie or URL parameter on the first visit. The header may contain complex values like `zh-Hant-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7` and must be parsed, quality-weighted, and matched against your supported locale list, including script-subtag disambiguation (Traditional vs Simplified Chinese).

---

## Context

The `Accept-Language` header is a comma-separated list of BCP 47 language tags, each optionally followed by a quality value (`q=0.9`). Tags without a `q` value have implicit quality `1.0`. Matching must use `Intl.Locale` canonicalisation to normalise tags (removing unnecessary subtags, expanding aliases) before comparing against supported locales. BCP 47 subtag lookup means `zh-Hant` (Traditional Chinese) and `zh-Hans` (Simplified Chinese) are distinct; falling through from `zh-TW` to `zh` without checking the script subtag would pick the wrong variant. The negotiated locale drives `Content-Language` response header and must appear in `Vary: Accept-Language` to ensure CDN caches serve the correct variant.

---

## Section 1 — Supported locale configuration

```toml
# wrangler.toml
[vars]
# Comma-separated ordered list of locales the app supports.
# Order determines tie-breaking when quality values are equal.
SUPPORTED_LOCALES = "en,en-US,en-GB,de,de-DE,fr,fr-FR,ja,zh-Hans,zh-Hant,ar,pt,pt-BR,ru,es,es-MX"
DEFAULT_LOCALE    = "en"
```

---

## Section 2 — Locale negotiation library

```typescript
// src/i18n/negotiate.ts

export interface NegotiationResult {
  locale:  string;   // The matched supported locale tag
  quality: number;   // The q-value of the matched preference
  source:  'header' | 'default';
}

interface WeightedTag {
  tag:     string;
  quality: number;
}

/**
 * Parse an Accept-Language header into a quality-sorted list of tags.
 * e.g. "zh-Hant-TW,zh;q=0.9,en-US;q=0.8" ->
 *   [ { tag: 'zh-Hant-TW', quality: 1.0 },
 *     { tag: 'zh',         quality: 0.9 },
 *     { tag: 'en-US',      quality: 0.8 } ]
 */
export function parseAcceptLanguage(header: string): WeightedTag[] {
  return header
    .split(',')
    .map(part => {
      const [rawTag, qPart] = part.trim().split(/;\s*q=/i);
      const tag     = rawTag.trim();
      const quality = qPart !== undefined ? parseFloat(qPart) : 1.0;
      return { tag, quality };
    })
    .filter(({ tag, quality }) =>
      tag.length > 0 &&
      !isNaN(quality) &&
      quality >= 0 &&
      quality <= 1
    )
    .sort((a, b) => b.quality - a.quality);
}

/**
 * Canonicalise a BCP 47 tag using `Intl.Locale`. Returns null if the tag
 * is malformed and the Intl constructor throws.
 */
function canonicalise(tag: string): string | null {
  try {
    return new Intl.Locale(tag).toString();
  } catch {
    return null;
  }
}

/**
 * Check whether `candidate` is covered by `supported`.
 * Rules (in priority order):
 * 1. Exact match after canonicalisation.
 * 2. Script-subtag match: both share language + script (zh-Hant-TW → zh-Hant).
 * 3. Base-language match (no script): supported='de', candidate='de-DE'.
 *
 * NOTE: Script subtags are checked BEFORE base-language to prevent
 * zh-Hant → zh-Hans mismatches.
 */
function isMatch(candidate: Intl.Locale, supported: Intl.Locale): boolean {
  // 1. Exact
  if (candidate.toString() === supported.toString()) return true;

  // 2. Script subtag match (language + script must both agree)
  if (
    candidate.language === supported.language &&
    candidate.script   &&
    supported.script   &&
    candidate.script === supported.script
  ) {
    return true;
  }

  // 3. Base language match — only when neither side specifies a script
  // (avoid collapsing zh-Hant into zh or zh-Hans)
  if (
    candidate.language === supported.language &&
    !candidate.script &&
    !supported.script
  ) {
    return true;
  }

  return false;
}

/**
 * Given a parsed Accept-Language list and a supported-locale list, return
 * the best supported locale or the default.
 */
export function negotiate(
  preferences: WeightedTag[],
  supported: string[],
  defaultLocale: string
): NegotiationResult {
  const supportedLocales = supported
    .map(s => {
      try { return new Intl.Locale(s); } catch { return null; }
    })
    .filter((l): l is Intl.Locale => l !== null);

  for (const { tag, quality } of preferences) {
    const canonical = canonicalise(tag);
    if (!canonical) continue;
    const candidateLocale = new Intl.Locale(canonical);

    for (const supportedLocale of supportedLocales) {
      if (isMatch(candidateLocale, supportedLocale)) {
        return { locale: supportedLocale.toString(), quality, source: 'header' };
      }
    }
  }

  return { locale: defaultLocale, quality: 0, source: 'default' };
}
```

---

## Section 3 — Worker handler

```typescript
// src/index.ts
import { parseAcceptLanguage, negotiate } from './i18n/negotiate';

export interface Env {
  SUPPORTED_LOCALES: string;
  DEFAULT_LOCALE:    string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const acceptLang = request.headers.get('Accept-Language') ?? '';
    const supported  = env.SUPPORTED_LOCALES.split(',').map(s => s.trim());
    const defaultLoc = env.DEFAULT_LOCALE ?? 'en';

    const preferences = parseAcceptLanguage(acceptLang);
    const { locale }  = negotiate(preferences, supported, defaultLoc);

    // Fetch localised content — replace with your actual content layer.
    const content = `Hello from locale: ${locale}`;

    return new Response(content, {
      headers: {
        'Content-Type':     'text/plain; charset=utf-8',
        // Inform the client which language was served.
        'Content-Language': locale,
        // Tell CDN/proxies to cache separately per Accept-Language value.
        'Vary':             'Accept-Language',
      },
    });
  },
};

// Example negotiation outcomes:
// Accept-Language: zh-Hant-TW,zh;q=0.9,en;q=0.8
//   → locale: 'zh-Hant'  (script subtag match, not collapsed to 'zh')
//
// Accept-Language: zh-CN,zh;q=0.9
//   → locale: 'zh-Hans'  (zh-CN canonicalises with Hans script)
//
// Accept-Language: de-AT,de;q=0.9
//   → locale: 'de-DE'    (base-language match, de-DE listed before de)
//
// Accept-Language: xx-YY
//   → locale: 'en'       (no match → default)
```

---

## Anti-patterns

- **Simple string prefix matching (`locale.startsWith(tag)`)** — This incorrectly equates `zh-Hant` with `zh-Hans` because both start with `zh`. Always use `Intl.Locale` and compare language + script fields separately.
- **Ignoring quality values and taking the first tag** — Browsers send tags in preference order but also attach explicit `q` values that override position in some cases; sort by quality before iterating.
- **Not setting `Vary: Accept-Language`** — Without this header, a Cloudflare CDN cache may serve a German-language response to an English-speaking user because it cached on URL alone.
- **Trusting raw tag strings without canonicalisation** — `EN-US`, `en_US`, and `en-Latn-US` are all valid inputs from various user agents; `Intl.Locale` normalises them before comparison.

---

## Gotchas

- `Intl.Locale` is available in Workers on compatibility date `2022-03-21` and later. Earlier dates may not expose it.
- `zh-CN` canonicalises to `zh-Hans-CN` in some runtimes (the script is implied). Your supported list should include `zh-Hans`, not `zh-CN`, to match correctly after canonicalisation.
- The `q=0` value means "not acceptable" — filter out tags with `quality === 0` before matching.
- `Content-Language` should reflect the *actual* language of the response body, not the negotiated tag. If you served `en` content after failing to find a German translation, set `Content-Language: en`.
- Workers behind Cloudflare Cache may not see the original `Accept-Language` if you cache on URL only; use Cache API with a cache key that includes the locale, or use `cf.cacheTtlByStatus` carefully.

---

## Verification

```bash
npx wrangler dev

# Exact match
curl -H 'Accept-Language: de-DE,de;q=0.9' http://localhost:8787/
# Expected header: Content-Language: de-DE

# Script-subtag match (Traditional Chinese)
curl -H 'Accept-Language: zh-Hant-TW,zh;q=0.9,en;q=0.8' http://localhost:8787/
# Expected header: Content-Language: zh-Hant

# Simplified Chinese via zh-CN
curl -H 'Accept-Language: zh-CN' http://localhost:8787/
# Expected header: Content-Language: zh-Hans

# Quality-value ordering
curl -H 'Accept-Language: en;q=0.5,fr;q=0.9' http://localhost:8787/
# Expected header: Content-Language: fr  (higher q wins)

# No match → default
curl -H 'Accept-Language: xx-YY' http://localhost:8787/
# Expected header: Content-Language: en

# Verify Vary header is present
curl -I -H 'Accept-Language: de' http://localhost:8787/ | grep -i vary
# Expected: Vary: Accept-Language
```

---

## Related

- `translation-key-missing-fallback-kv-workers.md`
- `plural-rules-intl-pluralrules-workers.md`
- `date-time-formatting-intl-datetimeformat-workers.md`

---

## Sources

- RFC 9110 Accept-Language — https://www.rfc-editor.org/rfc/rfc9110#field.accept-language
- BCP 47 Language Tags — https://www.rfc-editor.org/rfc/rfc5646
- MDN Intl.Locale — https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/Locale
- Cloudflare Workers headers — https://developers.cloudflare.com/workers/runtime-apis/request/
