# Locale-Specific Image Alt Text with R2 and Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Images stored in Cloudflare R2 need descriptive `alt` text returned in the viewer's language.
A single English alt string fails WCAG 2.1 SC 1.1.1 for non-English audiences and hurts SEO in
language-specific Google indexes. The challenge is storing per-locale alt text without duplicating
the binary asset and serving the right string with minimal latency.

## Context

R2 objects support up to 8 KB of custom HTTP metadata on each object. For a small fixed set of
locales this is sufficient; for many locales or long descriptions a thin D1 table is more
appropriate. Workers sits in front of R2 and can inject the correct `alt` string into JSON API
responses or into HTML fragments before returning them to the client.

Locale is resolved from the incoming request using `Accept-Language` negotiation or an explicit
`?lang=` query parameter. The resolved tag must be a valid BCP 47 subtag before it is used as a
lookup key.

---

## Storing Alt Text as R2 Custom Metadata

R2 metadata keys are ASCII strings; use a predictable prefix like `alt-` followed by the
BCP 47 primary subtag (lower-cased).

```typescript
// upload-with-alt.ts  (one-time migration / CMS publish step)
const altTexts: Record<string, string> = {
  en: "A red fox leaping over a frozen stream",
  fr: "Un renard roux sautant par-dessus un ruisseau gelé",
  ar: "ثعلب أحمر يقفز فوق جدول متجمد",
  ja: "凍った小川を飛び越える赤いキツネ",
};

const metadata: Record<string, string> = {};
for (const [locale, text] of Object.entries(altTexts)) {
  metadata[`alt-${locale}`] = text;          // e.g. "alt-en", "alt-fr"
}

await env.IMAGES.put("fox-jump.webp", imageBytes, {
  httpMetadata: { contentType: "image/webp" },
  customMetadata: metadata,
});
```

**Limit:** R2 custom metadata total must stay under 8 KB. For descriptions over ~200 chars per
locale, or more than ~15 locales, use D1 instead (see below).

---

## Serving Alt Text from a Worker

```typescript
// src/image-meta.ts
interface Env {
  IMAGES: R2Bucket;
}

const SUPPORTED = ["en", "fr", "de", "ar", "ja", "zh", "ko", "es", "pt"] as const;
type Locale = (typeof SUPPORTED)[number];

function resolveLocale(req: Request): Locale {
  const lang = new URL(req.url).searchParams.get("lang")
    ?? req.headers.get("Accept-Language")
    ?? "en";
  // Extract primary subtag, lower-case it.
  const primary = lang.split(/[,;]/)[0].trim().split("-")[0].toLowerCase();
  return (SUPPORTED as readonly string[]).includes(primary)
    ? (primary as Locale)
    : "en";
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    // /meta/<object-key>  →  JSON with alt, src, width, height
    const key = url.pathname.replace(/^\/meta\//, "");
    if (!key) return new Response("Not found", { status: 404 });

    const obj = await env.IMAGES.head(key);          // head = metadata only, no body
    if (!obj) return new Response("Not found", { status: 404 });

    const locale = resolveLocale(req);
    const alt =
      obj.customMetadata?.[`alt-${locale}`] ??
      obj.customMetadata?.["alt-en"] ??              // English fallback
      "";

    return Response.json({
      src: `https://images.example.com/${key}`,
      alt,
      locale,
    });
  },
};
```

---

## D1 Fallback for Many Locales

When the alt text set is large, store it in D1 and cache reads in KV.

```sql
-- schema.sql
CREATE TABLE image_alt (
  image_key  TEXT NOT NULL,
  locale     TEXT NOT NULL,          -- BCP 47 primary subtag
  alt_text   TEXT NOT NULL,
  PRIMARY KEY (image_key, locale)
);
CREATE INDEX idx_image_alt_key ON image_alt (image_key);
```

```typescript
// src/alt-from-d1.ts
async function getAlt(
  key: string,
  locale: string,
  env: { DB: D1Database; KV: KVNamespace }
): Promise<string> {
  const cacheKey = `alt:${key}:${locale}`;
  const cached = await env.KV.get(cacheKey);
  if (cached !== null) return cached;

  const row = await env.DB
    .prepare("SELECT alt_text FROM image_alt WHERE image_key = ?1 AND locale = ?2")
    .bind(key, locale)
    .first<{ alt_text: string }>();

  const fallback = row?.alt_text ?? "";
  // Cache for 1 hour; alt text changes infrequently.
  await env.KV.put(cacheKey, fallback, { expirationTtl: 3600 });
  return fallback;
}
```

---

## Injecting Alt Text into HTML with HTMLRewriter

For server-side rendered pages, rewrite `<img>` tags on the fly without a separate API call.

```typescript
class AltInjector implements HTMLRewriterElementContentHandlers {
  constructor(
    private altMap: Map<string, string>  // r2Key → alt string
  ) {}

  element(el: Element) {
    const src = el.getAttribute("data-r2-key");
    if (!src) return;
    const alt = this.altMap.get(src) ?? "";
    el.setAttribute("alt", alt);
    el.removeAttribute("data-r2-key");
  }
}

// Usage in a Worker fetch handler:
// const rewriter = new HTMLRewriter().on("img[data-r2-key]", new AltInjector(altMap));
// return rewriter.transform(upstreamResponse);
```

---

## Anti-patterns

- **Using the full BCP 47 tag as the metadata key** (`alt-zh-Hant-TW`): R2 key length and the
  8 KB cap punish verbose keys. Normalize to the primary subtag (`zh`) and store script or region
  variants in D1.
- **Storing alt text only in the filename**: filenames are not surfaced in API responses and cannot
  differ per locale.
- **Trusting `Accept-Language` verbatim as a D1 parameter**: always extract and validate the
  primary subtag before using it in a query.

## Gotchas

- `env.IMAGES.head()` does not transfer the object body — use it for metadata-only lookups.
  `env.IMAGES.get()` streams the full binary, incurring egress costs.
- R2 custom metadata values must be ASCII. Store non-ASCII alt text (Arabic, Japanese, etc.) as
  percent-encoded strings, or move to D1 which accepts full UTF-8.
- `HTMLRewriter` processes HTML in streaming chunks; do not attempt to read attributes set by an
  earlier rewriter pass in the same chain.

## Verification

```bash
# Check metadata is attached to an R2 object via wrangler
wrangler r2 object get IMAGES fox-jump.webp --pipe | head -c 0

# Call the meta endpoint and inspect alt field
curl "https://your-worker.example.com/meta/fox-jump.webp?lang=ar" | jq .alt

# Validate HTML output has correct alt text
curl -s "https://your-worker.example.com/gallery" \
  -H "Accept-Language: fr" | grep -oP 'alt="[^"]+"'
```

## Related

- `locale-aware-image-text-overlay-r2-workers.md`
- `locale-aware-og-social-meta-workers.md`
- `i18n-accessibility-screen-readers-2026.md`
- `kv-locale-key-sharding-high-traffic.md`

## Sources

- Cloudflare R2 Custom Metadata — https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- WCAG 2.1 SC 1.1.1 Non-text Content — https://www.w3.org/TR/WCAG21/#non-text-content
- BCP 47 primary language subtag — RFC 5646 §2.2.1
- Cloudflare HTMLRewriter — https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/
