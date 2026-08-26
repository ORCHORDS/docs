# Georgian Script Localization on Cloudflare Workers and Pages

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A product expanding into Georgia (the country) needs to serve UI copy, search results, and URL slugs in the Georgian script (Mkhedruli). Common failure modes include treating Georgian strings as ASCII-safe (breaking slug generation), missing locale-aware collation for D1-backed search, and font-loading pipelines that omit the Georgian Unicode block (U+10A0–U+10FF, U+2D00–U+2D2F). Cloudflare Workers must handle normalization, slug generation, and collation at the edge.

## Context

Georgian has three historical scripts — Asomtavruli (U+10A0–U+10CF), Nuskhuri (U+2D00–U+2D2F), and Mkhedruli (U+10D0–U+10FF) — but modern standard Georgian uses Mkhedruli exclusively. The alphabet has 33 letters; it is unicameral (no uppercase/lowercase distinction in Mkhedruli, though Asomtavruli/Nuskhuri pairs exist). Georgian is left-to-right, phonetically consistent, and has no ligatures — making it one of the simpler scripts to handle once font coverage is confirmed. Key edge cases are: correct locale-aware sorting (CLDR `ka` collation), slug generation that preserves Mkhedruli characters in URLs (RFC 3987 / IRI-safe), and search normalization that strips Asomtavruli variants for modern-text search.

## Georgian Slug Generation in Workers

```typescript
// src/georgian-slug.ts

/**
 * Georgian Mkhedruli characters are valid IRI path characters (RFC 3987)
 * and modern browsers display them decoded in the address bar.
 * Slug strategy: preserve Georgian letters, replace spaces with hyphens,
 * strip ASCII punctuation, percent-encode only characters outside
 * the Georgian + Latin safe set.
 */
export function georgianSlug(title: string): string {
  return title
    .normalize("NFC")                     // compose any decomposed sequences
    .toLowerCase()                        // Georgian has no case in Mkhedruli, safe no-op
    .replace(/[\s_]+/g, "-")             // spaces / underscores → hyphen
    .replace(/[^ა-ჿⴀ-⴯Ⴀ-჏a-z0-9\-]/g, "") // strip unsafe chars
    .replace(/-+/g, "-")                  // collapse repeated hyphens
    .replace(/^-|-$/g, "");              // trim leading/trailing hyphens
}

// Examples:
// georgianSlug("კლიმატის ცვლილება")   → "კლიმატის-ცვლილება"
// georgianSlug("Tbilisi / თბილისი")   → "tbilisi-თბილისი"
// georgianSlug("  --ვარდი--  ")        → "ვარდი"
```

## Locale-Aware D1 Collation for Georgian Search Results

```typescript
// src/georgian-search.ts
// D1/SQLite does not ship the `ka` ICU collation, so we sort results
// in the Worker after retrieval using Intl.Collator.

interface Env {
  DB: D1Database;
}

interface Article {
  id:    number;
  title: string;
  slug:  string;
}

const KA_COLLATOR = new Intl.Collator("ka", {
  sensitivity: "base",   // case/accent-insensitive (Georgian has no case, but be explicit)
  usage:       "sort",
});

export async function searchGeorgian(
  query: string,
  env:   Env
): Promise<Article[]> {
  // Normalize query before D1 LIKE search
  const normalizedQuery = query.normalize("NFC");

  // D1 LIKE with % is case-sensitive for non-ASCII; retrieve a broad candidate set
  const { results } = await env.DB
    .prepare(
      `SELECT id, title, slug
       FROM articles
       WHERE locale = 'ka'
         AND title LIKE '%' || ?1 || '%'
       LIMIT 200`
    )
    .bind(normalizedQuery)
    .all<Article>();

  // Sort in the Worker with proper Georgian collation order
  return (results ?? []).sort((a, b) =>
    KA_COLLATOR.compare(a.title, b.title)
  );
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const q       = new URL(request.url).searchParams.get("q") ?? "";
    const results = await searchGeorgian(q, env);

    return new Response(JSON.stringify(results), {
      headers: { "Content-Type": "application/json; charset=utf-8" },
    });
  },
};
```

## Font Serving for Georgian Script from R2

```typescript
// src/font-handler.ts
interface Env {
  FONT_BUCKET: R2Bucket;
}

const FONT_MANIFEST: Record<string, string> = {
  "bpg-nino-mtavruli.woff2": "fonts/georgian/bpg-nino-mtavruli.woff2",
  "noto-sans-georgian.woff2": "fonts/georgian/noto-sans-georgian.woff2",
};

export async function handleFontRequest(
  request: Request,
  env: Env
): Promise<Response | null> {
  const name = new URL(request.url).pathname.split("/").pop() ?? "";
  const key  = FONT_MANIFEST[name];
  if (!key) return null;

  const cached = await caches.default.match(request);
  if (cached) return cached;

  const obj = await env.FONT_BUCKET.get(key);
  if (!obj) return new Response("Not found", { status: 404 });

  const resp = new Response(obj.body, {
    headers: {
      "Content-Type":  "font/woff2",
      "Cache-Control": "public, max-age=31536000, immutable",
    },
  });

  await caches.default.put(request, resp.clone());
  return resp;
}
```

```css
/* pages/styles/georgian.css */
@font-face {
  font-family: "GeorgianSans";
  src: url("/fonts/noto-sans-georgian.woff2") format("woff2");
  font-display: swap;
  unicode-range:
    U+10A0-10FF,   /* Georgian (Mkhedruli + Asomtavruli) */
    U+2D00-2D2F;   /* Georgian Supplement (Nuskhuri) */
}

:lang(ka) {
  font-family: "GeorgianSans", "BPG Nino Mtavruli", "Sylfaen", sans-serif;
  line-height: 1.7;
}
```

## Asomtavruli-to-Mkhedruli Normalization for Search

```typescript
// src/georgian-normalize.ts

/**
 * Asomtavruli (U+10A0–U+10CF) is the liturgical uppercase script.
 * For modern search normalization, fold Asomtavruli to Mkhedruli equivalents
 * so that searching "ა" also matches its Asomtavruli counterpart "Ⴀ".
 */
const ASOMTAVRULI_TO_MKHEDRULI: Map<string, string> = new Map(
  Array.from({ length: 0x30 }, (_, i) => [
    String.fromCodePoint(0x10A0 + i), // Asomtavruli
    String.fromCodePoint(0x10D0 + i), // corresponding Mkhedruli
  ])
);

export function foldToMkhedruli(text: string): string {
  return Array.from(text)
    .map(ch => ASOMTAVRULI_TO_MKHEDRULI.get(ch) ?? ch)
    .join("");
}

// foldToMkhedruli("ႠႬჂႠ") → "ანყა" (if mapping holds for those offsets)
```

## Anti-patterns

- `encodeURIComponent`-ing Georgian slugs before storing them in D1 — the encoded form (`%E1%83%99%E1%83%9A%E1%83%98`) is unreadable in browser address bars and bloats the column; store the raw Mkhedruli string and percent-encode only at URL render time.
- Using `COLLATE NOCASE` in D1/SQLite for Georgian — `NOCASE` is ASCII-only and does nothing for Georgian characters; all Georgian sort order in D1 must be handled in the Worker layer via `Intl.Collator`.
- Bundling full Noto Sans (all scripts) instead of subsetting — the full NotoSans covers 800+ scripts and is several MB; subset to Georgian Unicode ranges only.

## Gotchas

- Georgian has no uppercase/lowercase distinction in Mkhedruli, but `String.prototype.toLowerCase()` and `toUpperCase()` are still safe to call — they are no-ops for Mkhedruli, which means code that normalizes case before comparison does not break.
- Asomtavruli (U+10A0–U+10CF) and Mkhedruli (U+10D0–U+10FF) are different blocks at different offsets — a simple `ch.toLowerCase()` will NOT map between them. Use the explicit fold map above.

## Verification

```bash
# Verify slug generation
node -e "
const { georgianSlug } = require('./dist/georgian-slug');
console.log(georgianSlug('კლიმატის ცვლილება')); // → კლიმატის-ცვლილება
console.log(georgianSlug('Tbilisi / თბილისი'));  // → tbilisi-თბილისი
"

# Upload Georgian font to R2 and test font worker
wrangler r2 object put FONT_BUCKET/fonts/georgian/noto-sans-georgian.woff2 \
  --file ./NotoSansGeorgian-Regular-subset.woff2

curl -I "http://localhost:8787/fonts/noto-sans-georgian.woff2"
# Expected: Content-Type: font/woff2, Cache-Control: public, max-age=31536000, immutable

# Test D1 search
wrangler d1 execute DB --local \
  --command "INSERT INTO articles (locale, title, slug) VALUES ('ka', 'კლიმატის ცვლილება', 'კლიმატის-ცვლილება')"
curl "http://localhost:8787?q=კლი" | jq .
```

## Related

- `i18n/locale-aware-url-slug-normalization.md`
- `i18n/unicode-collation-d1-sqlite-locale-sort.md`
- `i18n/multilingual-font-loading-subsetting.md`
- `i18n/r2-font-subsetting-multi-script-pipeline-2026.md`

## Sources

- https://unicode.org/charts/PDF/U10A0.pdf
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/r2/
- https://fonts.google.com/noto/specimen/Noto+Sans+Georgian
- https://www.unicode.org/cldr/charts/46/collation/ka.html
