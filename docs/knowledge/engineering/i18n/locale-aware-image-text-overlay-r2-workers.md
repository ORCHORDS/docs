# Locale-Aware Dynamic Image Text Overlay — Workers + R2

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You generate Open Graph share images or social banners on the fly and need the overlay text
(product names, prices, CTA copy) to render correctly in Arabic, Japanese, Hebrew, or Thai —
right script, right direction, correct line-breaking — without shipping a full server-side
graphics library. Static pre-generated images per locale explode your R2 storage and CDN
invalidation surface.

## Context

Cloudflare Workers cannot call native canvas or font APIs directly. The practical stack is:
1. Fetch a locale-keyed SVG template from R2.
2. Inject escaped, direction-aware text into the SVG using `HTMLRewriter` or string
   interpolation with a safe escaper.
3. Return the SVG directly (for web) or pipe through a Cloudflare Images Transform URL
   (for PNG rasterisation).

R2 holds per-locale base SVG templates and font subsets. Workers handle request-time text
injection and cache the result in the Cache API keyed by locale + content hash.

---

## 1 — R2 layout: locale-keyed SVG templates

```
r2://og-templates/
  en/base.svg
  ar/base.svg     ← RTL template with text-anchor="end" x="90%"
  ja/base.svg     ← narrow font, CJK-safe text wrapping
  he/base.svg
  th/base.svg
```

Upload templates with:
```bash
wrangler r2 object put og-templates/ar/base.svg --file ./templates/ar/base.svg
```

An RTL SVG template (`ar/base.svg`) example structure:
```xml
<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" direction="rtl">
  <rect width="1200" height="630" fill="#0f172a"/>
  <!-- Placeholders injected at request time -->
  <text id="og-title"    x="90%" y="200" text-anchor="end" font-size="56"
        fill="#f8fafc" font-family="Cairo, sans-serif">TITLE_PLACEHOLDER</text>
  <text id="og-subtitle" x="90%" y="290" text-anchor="end" font-size="32"
        fill="#94a3b8" font-family="Cairo, sans-serif">SUBTITLE_PLACEHOLDER</text>
</svg>
```

---

## 2 — Safe SVG text escaper

```typescript
// src/svg-escape.ts

/** Escape characters that break SVG text content. */
export function escapeSvg(raw: string): string {
  return raw
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

/** Truncate to maxChars grapheme clusters — safe for CJK / emoji. */
export function truncateGraphemes(text: string, max: number): string {
  const seg = new Intl.Segmenter(undefined, { granularity: 'grapheme' });
  const clusters = [...seg.segment(text)];
  if (clusters.length <= max) return text;
  return clusters.slice(0, max - 1).map(s => s.segment).join('') + '…';
}
```

---

## 3 — Locale direction and font family map

```typescript
// src/locale-svg-config.ts

interface SvgLocaleConfig {
  dir: 'ltr' | 'rtl';
  fontFamily: string;
  titleMaxGraphemes: number;
  subtitleMaxGraphemes: number;
  templateKey: string;     // R2 object key
}

const LOCALE_CONFIG: Record<string, SvgLocaleConfig> = {
  'ar': { dir: 'rtl', fontFamily: 'Cairo, sans-serif',         titleMaxGraphemes: 40, subtitleMaxGraphemes: 70, templateKey: 'ar/base.svg' },
  'he': { dir: 'rtl', fontFamily: 'Frank Ruhl Libre, serif',   titleMaxGraphemes: 50, subtitleMaxGraphemes: 80, templateKey: 'he/base.svg' },
  'ja': { dir: 'ltr', fontFamily: 'Noto Sans JP, sans-serif',  titleMaxGraphemes: 20, subtitleMaxGraphemes: 35, templateKey: 'ja/base.svg' },
  'zh': { dir: 'ltr', fontFamily: 'Noto Sans SC, sans-serif',  titleMaxGraphemes: 20, subtitleMaxGraphemes: 35, templateKey: 'zh/base.svg' },
  'th': { dir: 'ltr', fontFamily: 'Sarabun, sans-serif',       titleMaxGraphemes: 45, subtitleMaxGraphemes: 75, templateKey: 'th/base.svg' },
};

const FALLBACK: SvgLocaleConfig = {
  dir: 'ltr', fontFamily: 'Inter, sans-serif',
  titleMaxGraphemes: 60, subtitleMaxGraphemes: 100,
  templateKey: 'en/base.svg',
};

export function getSvgConfig(locale: string): SvgLocaleConfig {
  const lang = locale.split('-')[0];
  return LOCALE_CONFIG[locale] ?? LOCALE_CONFIG[lang] ?? FALLBACK;
}
```

---

## 4 — Worker: fetch template from R2 and inject text

```typescript
// src/index.ts
import { escapeSvg, truncateGraphemes } from './svg-escape';
import { getSvgConfig }                 from './locale-svg-config';

interface Env { OG_TEMPLATES: R2Bucket }

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url      = new URL(req.url);
    const locale   = url.searchParams.get('locale') ?? 'en';
    const title    = url.searchParams.get('title')    ?? '';
    const subtitle = url.searchParams.get('subtitle') ?? '';

    const cfg = getSvgConfig(locale);

    // Cache key: locale + content hash
    const cacheKey = `og:${locale}:${title}:${subtitle}`;
    const cache    = caches.default;
    const cached   = await cache.match(new Request(`https://og-cache/${btoa(cacheKey)}`));
    if (cached) return cached;

    // Fetch base SVG from R2
    const obj = await env.OG_TEMPLATES.get(`og-templates/${cfg.templateKey}`);
    if (!obj) return new Response('Template not found', { status: 404 });

    let svg = await obj.text();

    // Inject localised, escaped, truncated text
    svg = svg
      .replace('TITLE_PLACEHOLDER',    escapeSvg(truncateGraphemes(title,    cfg.titleMaxGraphemes)))
      .replace('SUBTITLE_PLACEHOLDER', escapeSvg(truncateGraphemes(subtitle, cfg.subtitleMaxGraphemes)));

    const res = new Response(svg, {
      headers: {
        'Content-Type': 'image/svg+xml',
        'Cache-Control': 'public, max-age=86400',
        'Content-Language': locale,
      },
    });

    // Store in Cache API
    await cache.put(new Request(`https://og-cache/${btoa(cacheKey)}`), res.clone());
    return res;
  },
};
```

---

## 5 — wrangler.toml binding

```toml
name = "og-image-worker"
compatibility_date = "2026-01-01"

[[r2_buckets]]
binding     = "OG_TEMPLATES"
bucket_name = "og-templates"
```

---

## Anti-patterns

- **Injecting raw user text into SVG without escaping** — an `&` or `<` in a product name
  breaks the SVG; a `<script>` in a subtitle is an XSS vector.
- **One LTR template for all locales** — Arabic and Hebrew text injected into a left-anchored
  template will appear mirrored; maintain RTL-specific templates.
- **Using `.length` for truncation** — CJK characters and emoji are all one code unit but
  display at double width; use `Intl.Segmenter` grapheme count instead.
- **Caching SVGs without a content hash in the key** — two different titles for the same locale
  collide and one user sees another's image.

## Gotchas

- SVG `<text>` does not word-wrap natively. For long strings, split on `Intl.Segmenter` word
  boundaries and emit multiple `<tspan>` elements at increasing `dy` offsets.
- Google Fonts are blocked inside Cloudflare Workers (CSP). Embed the font as a base64
  data URI in the SVG template stored in R2, or reference a self-hosted Workers asset URL.
- Cloudflare Images Transform (`/cdn-cgi/image/format=png`) can rasterise the SVG response,
  but only if the Worker response has `Content-Type: image/svg+xml` — set it explicitly.

## Verification

```typescript
import { escapeSvg, truncateGraphemes } from './svg-escape';

console.assert(escapeSvg('<img src=x onerror=alert(1)>') === '&lt;img src=x onerror=alert(1)&gt;');
console.assert(escapeSvg('A & B') === 'A &amp; B');
// CJK truncation: each kanji = 1 grapheme
const jp = '日本語テスト文字列テスト文字列テスト文字列テスト文字列テスト文字列';
console.assert(truncateGraphemes(jp, 10).length < jp.length);
// Emoji = 1 grapheme each
console.assert(truncateGraphemes('👋🌍🎉', 2) === '👋🌍…');
```

## Related

- `locale-aware-og-social-meta-workers.md`
- `rtl-text-detection-workers-htmlrewriter.md`
- `locale-aware-markdown-typography-workers.md`
- `r2-font-subsetting-multi-script-pipeline-2026.md`
- `intl-segmenter-grapheme-safe-editing.md`

## Sources

- Cloudflare R2 docs — https://developers.cloudflare.com/r2/
- SVG `direction` attribute — https://developer.mozilla.org/en-US/docs/Web/SVG/Attribute/direction
- `Intl.Segmenter` — https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/Segmenter
- Cloudflare Images Transform — https://developers.cloudflare.com/images/transform-images/
