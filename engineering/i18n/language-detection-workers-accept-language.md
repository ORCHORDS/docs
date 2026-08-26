# Language Detection via Accept-Language Header Parsing in Cloudflare Workers

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

example project users on mobile receive the wrong language on first visit. Android Chrome sends a
multi-valued `Accept-Language: en-US,en;q=0.9,ar;q=0.8` header and the Worker picks
`en-US` even though the user's app is in Arabic. iOS Safari omits the quality value
for the first tag (`Accept-Language: fr-FR,fr;q=0.9,en;q=0.8`) which is standard, but
Samsung Internet 24 sends duplicate language tags with inconsistent casing
(`Accept-Language: ko-KR,KO;q=0.8`) that a naive `split(",")` parser mishandles.
Some corporate mobile MDM solutions strip or replace `Accept-Language` entirely.

## Context

example project (example.com) is a Next.js static export on Cloudflare Pages. A Cloudflare Worker
acts as the API and locale-routing layer. Locale detection happens in the Worker on every
request and the resolved locale is used to: (a) select the correct static HTML file from
Cloudflare Pages, (b) set `lang` and `dir` on the HTML element via `HTMLRewriter`, (c)
choose the currency and number formats returned by the API. A correct, robust
Accept-Language parser at the edge is therefore critical to the entire localisation stack.

---

## RFC 5646 Accept-Language Header Structure

`Accept-Language` is defined in RFC 7231 §5.3.5. Each entry is a language tag optionally
followed by a quality weight `q=` in the range 0.0–1.0. Entries without a `q=` have an
implicit weight of `1.0`.

```
Accept-Language: ar-SA,ar;q=0.9,en-US;q=0.8,en;q=0.7,*;q=0.5
```

| Field   | Value   | Weight | Notes                              |
|---------|---------|--------|------------------------------------|
| ar-SA   | ar-SA   | 1.0    | implicit; most preferred           |
| ar      | ar      | 0.9    | fallback to any Arabic             |
| en-US   | en-US   | 0.8    | English (US) fallback              |
| en      | en      | 0.7    | generic English                    |
| *       | *       | 0.5    | wildcard — accept anything         |

The parser must:
1. Split on `,` (but not on `,` inside quotes — rare but valid in extensions).
2. Parse each tag and its `q=` value.
3. Sort descending by weight.
4. For equal weights, preserve the header order (the RFC does not require stable sort,
   but browsers emit entries in preference order within equal weights).

---

## Robust Edge-Safe Parser Implementation

```typescript
// workers/src/accept-language.ts
export interface LangTag {
  tag: string;      // normalised BCP 47 tag
  quality: number;  // 0.0 – 1.0
}

export function parseAcceptLanguage(header: string | null): LangTag[] {
  if (!header) return [];

  return header
    .split(",")
    .map(entry => {
      const [rawTag, ...rest] = entry.trim().split(";");
      const tag = normaliseTag(rawTag.trim());
      const qPart = rest.find(p => p.trim().startsWith("q="));
      const quality = qPart ? parseFloat(qPart.split("=")[1]) : 1.0;
      return { tag, quality: isNaN(quality) ? 1.0 : Math.min(1.0, Math.max(0.0, quality)) };
    })
    .filter(({ tag }) => tag.length > 0 && tag !== "*")
    .sort((a, b) => b.quality - a.quality || 0);
}

function normaliseTag(raw: string): string {
  try {
    // Intl.getCanonicalLocales normalises casing and sub-tags
    const [canonical] = Intl.getCanonicalLocales(raw);
    return canonical;
  } catch {
    return ""; // invalid tag — filter out
  }
}
```

| Raw header entry        | Parsed tag | quality |
|-------------------------|------------|---------|
| `fr-FR`                 | fr-FR      | 1.0     |
| `KO;q=0.8`              | ko         | 0.8     |
| `zh-Hant-TW;q=0.7`      | zh-Hant-TW | 0.7     |
| `en_US`                 | (dropped)  | —       |
| `*;q=0.1`               | (dropped)  | —       |

---

## Locale Matching: Negotiating Against Supported Locales

Parsing the header is only half the job. The Worker must match the ranked list against
example project's supported locales using lookup (best-fit) matching, not exact string comparison.

```typescript
const SUPPORTED_LOCALES = ["en-US", "ar-SA", "fr-FR", "de-DE", "hi-IN", "ko-KR"];
const DEFAULT_LOCALE = "en-US";

export function negotiateLocale(header: string | null): string {
  const tags = parseAcceptLanguage(header);

  for (const { tag } of tags) {
    // Exact match
    if (SUPPORTED_LOCALES.includes(tag)) return tag;

    // Language-only fallback: "ar" matches "ar-SA"
    const lang = tag.split("-")[0];
    const match = SUPPORTED_LOCALES.find(s => s.startsWith(lang + "-") || s === lang);
    if (match) return match;
  }

  return DEFAULT_LOCALE;
}
```

Using `@formatjs/intl-localematcher` gives BCP 47-compliant best-fit matching:

```typescript
import { match } from "@formatjs/intl-localematcher";

export function negotiateLocaleRFC(header: string | null): string {
  const requested = parseAcceptLanguage(header).map(l => l.tag);
  if (requested.length === 0) return DEFAULT_LOCALE;
  try {
    return match(requested, SUPPORTED_LOCALES, DEFAULT_LOCALE, {
      algorithm: "best fit",
    });
  } catch {
    return DEFAULT_LOCALE;
  }
}
```

---

## Mobile Browser Quirks vs Desktop

| Browser / Platform          | Accept-Language quirk                                          | Impact on parsing              |
|-----------------------------|----------------------------------------------------------------|--------------------------------|
| iOS Safari 17               | First tag has no `q=`; uses system locale, not app UI locale  | Implicit q=1.0, correct        |
| Android Chrome 124          | Includes all OS languages in order; can be 6–8 entries long   | Parser must handle long lists  |
| Samsung Internet 24         | Duplicate tags; inconsistent casing (e.g. `KO` for `ko`)     | Normalise with `getCanonicalLocales` |
| Android WebView (embedded)  | May inherit app locale, not device locale; can be just `en`   | Lang-only fallback required    |
| Firefox for Android 126     | Sends `*` as last entry; can appear mid-list if user edited   | Filter wildcards explicitly    |
| Mobile MDM-managed devices  | Header stripped or replaced with corporate default (`en-US`)  | Cookie override beats header   |
| iOS in-app browser (WKWebView) | Uses app bundle locale, not device locale                 | Locale may not match CF-Timezone |

---

## Cookie and URL Override Strategy

A user preference cookie must take precedence over the header to allow explicit locale
switching. The resolution order from highest to lowest priority:

```
1. URL prefix  →  /ar/events      (set at navigation time)
2. User cookie →  locale=ar-SA    (set when user switches language)
3. Accept-Language header         (parsed on every request)
4. CF-Timezone country hint       (weak geographic signal)
5. Default locale                 (en-US)
```

```typescript
export function resolveLocale(request: Request): string {
  // 1. URL prefix
  const url = new URL(request.url);
  const prefix = url.pathname.split("/")[1];
  if (SUPPORTED_LOCALES.includes(prefix)) return prefix;

  // 2. Cookie
  const cookie = request.headers.get("Cookie") ?? "";
  const m = cookie.match(/\blocale=([^;]+)/);
  if (m) {
    const decoded = decodeURIComponent(m[1]);
    if (SUPPORTED_LOCALES.includes(decoded)) return decoded;
  }

  // 3. Accept-Language header
  const negotiated = negotiateLocaleRFC(request.headers.get("Accept-Language"));
  if (negotiated !== DEFAULT_LOCALE) return negotiated;

  // 4. CF-Timezone country hint (map country → default locale)
  const country = (request as any).cf?.country as string | undefined;
  if (country) {
    const hint = COUNTRY_LOCALE_HINTS[country];
    if (hint) return hint;
  }

  return DEFAULT_LOCALE;
}
```

---

## Anti-patterns

- Splitting on `,` and taking the first element without parsing `q=` weights — correct
  only when the first element has q=1.0, but breaks when q=0.0 entries appear first.
- Using `Accept-Language.split(",")[0].split(";")[0].trim()` as the locale — drops
  regional subtags inconsistently and ignores quality negotiation entirely.
- Storing the raw `Accept-Language` header in D1 for analytics — the header can be
  2 KB+ on mobile Chrome; extract and store only the resolved locale tag.
- Setting a permanent cookie on every request without a max-age — accumulates duplicate
  `Set-Cookie` headers and bloats responses.
- Using `CF-IPCountry` as the primary locale signal — country ≠ language (e.g. `CH` has
  four official languages).

---

## Gotchas

- `Intl.getCanonicalLocales` throws a `RangeError` for malformed tags like `en_US`
  (underscore instead of hyphen) — always wrap in try/catch.
- Some privacy-focused mobile browsers (Brave, Firefox Focus) send `Accept-Language: en`
  regardless of device locale to reduce fingerprinting — user cannot easily change locale
  without the UI language switcher.
- The `*` wildcard in Accept-Language means "any language not already listed" per RFC
  7231, not "any language" — a common parser error is treating it as a match-all.
- Cloudflare Workers parse headers case-insensitively (`accept-language` and
  `Accept-Language` are the same); always use `request.headers.get("Accept-Language")`,
  not manual header map lookups.
- Quality value `q=0` means explicitly *not acceptable* — if `ar;q=0` appears, the user
  has opted out of Arabic even if an Arabic tag appeared elsewhere in the list.

---

## Verification

```typescript
// vitest
import { parseAcceptLanguage, negotiateLocale } from "../src/accept-language";

describe("parseAcceptLanguage", () => {
  it("handles implicit q=1.0", () => {
    const result = parseAcceptLanguage("fr-FR,fr;q=0.9");
    expect(result[0]).toEqual({ tag: "fr-FR", quality: 1.0 });
  });

  it("normalises Samsung Internet casing", () => {
    const result = parseAcceptLanguage("ko-KR,KO;q=0.8");
    expect(result[1].tag).toBe("ko");
  });

  it("filters wildcards", () => {
    const result = parseAcceptLanguage("en;q=0.9,*;q=0.5");
    expect(result.every(r => r.tag !== "*")).toBe(true);
  });
});

describe("negotiateLocale", () => {
  it("falls back language-only when region not supported", () => {
    expect(negotiateLocale("ar-EG")).toBe("ar-SA");
  });
  it("returns default when no match", () => {
    expect(negotiateLocale("xx-YY")).toBe("en-US");
  });
});
```

---

## Related

- `locale-negotiation-accept-language.md`
- `locale-detection-browser.md`
- `language-detection-2026.md`
- `content-negotiation-vary-header.md`
- `cloudflare-workers-geolocation-locale-routing.md`
- `locale-fallback-chain.md`

---

## Sources

- RFC 7231 §5.3.5 Accept-Language: https://datatracker.ietf.org/doc/html/rfc7231#section-5.3.5
- RFC 4647 Matching of Language Tags: https://datatracker.ietf.org/doc/html/rfc4647
- MDN Accept-Language: https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Accept-Language
- @formatjs/intl-localematcher: https://formatjs.io/docs/polyfills/intl-localematcher
- Cloudflare Workers Request Object: https://developers.cloudflare.com/workers/runtime-apis/request/
- Chrome Intl language preferences: https://chromium.googlesource.com/chromium/src/+/main/chrome/browser/ui/browser_ui_prefs.cc
