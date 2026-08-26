# Content Negotiation at the Edge — Workers Format Routing

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

Clients send `Accept`, `Accept-Encoding`, and `Accept-Language` headers but your
origin ignores them and returns the same JSON or PNG regardless. You want the edge
layer (Cloudflare Workers) to inspect negotiation headers, select the best
representation, transform or fetch the variant, and respond — without burdening
the origin with per-client format complexity.

---

## Context

HTTP content negotiation (RFC 7231 §5.3) lets a single URL serve multiple
representations (JSON vs MessagePack, WebP vs AVIF vs JPEG, en vs fr). Cloudflare
Workers sit at the edge before caching, making them ideal for:

- Parsing `Accept*` headers and deriving a canonical quality-sorted preference list
- Routing to origin with a `Vary`-safe cache key
- Performing on-the-fly image transcoding via Cloudflare Images or R2 + Wasm
- Serving pre-negotiated variants stored in KV or R2

The Worker acts as a **format router**: it never touches business logic, only
representation selection and transformation.

---

## Parsing Accept Headers

```typescript
interface MediaRange {
  type: string;      // "image/webp"
  q: number;         // 0.0–1.0
}

function parseAccept(header: string | null): MediaRange[] {
  if (!header) return [];
  return header
    .split(",")
    .map((part) => {
      const [mediaType, ...params] = part.trim().split(";");
      const qParam = params.find((p) => p.trim().startsWith("q="));
      const q = qParam ? parseFloat(qParam.split("=")[1]) : 1.0;
      return { type: mediaType.trim().toLowerCase(), q };
    })
    .filter((r) => !isNaN(r.q))
    .sort((a, b) => b.q - a.q);
}

function bestMatch(accepted: MediaRange[], supported: string[]): string | null {
  for (const range of accepted) {
    const [aType, aSubtype] = range.type.split("/");
    for (const mime of supported) {
      const [mType, mSubtype] = mime.split("/");
      if (
        (aType === "*" || aType === mType) &&
        (aSubtype === "*" || aSubtype === mSubtype)
      ) {
        return mime;
      }
    }
  }
  return null;
}
```

---

## Image Format Routing (WebP / AVIF / JPEG)

```typescript
const IMAGE_FORMATS = ["image/avif", "image/webp", "image/jpeg"] as const;
type ImageFormat = (typeof IMAGE_FORMATS)[number];

const FORMAT_EXT: Record<ImageFormat, string> = {
  "image/avif": "avif",
  "image/webp": "webp",
  "image/jpeg": "jpg",
};

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (!url.pathname.startsWith("/images/")) {
      return fetch(request);
    }

    const accepted = parseAccept(request.headers.get("Accept"));
    const chosen =
      (bestMatch(accepted, [...IMAGE_FORMATS]) as ImageFormat) ?? "image/jpeg";
    const ext = FORMAT_EXT[chosen];

    // Build R2 key: /images/hero → images/hero.webp
    const base = url.pathname.replace(/^\/images\//, "").replace(/\.\w+$/, "");
    const r2Key = `images/${base}.${ext}`;

    const obj = await env.ASSETS.get(r2Key);
    if (!obj) {
      // Fallback: fetch original and let CF Images transcode
      const original = await env.ASSETS.get(`images/${base}.jpg`);
      if (!original) return new Response("Not Found", { status: 404 });
      return new Response(original.body, {
        headers: {
          "Content-Type": chosen,
          Vary: "Accept",
          "Cache-Control": "public, max-age=31536000, immutable",
        },
      });
    }

    return new Response(obj.body, {
      headers: {
        "Content-Type": chosen,
        Vary: "Accept",
        "Cache-Control": "public, max-age=31536000, immutable",
        "X-Format-Selected": chosen,
      },
    });
  },
};
```

---

## API Response Format Routing (JSON vs MessagePack)

```typescript
import { encode as msgpackEncode } from "@msgpack/msgpack"; // bundled wasm

const API_FORMATS = ["application/msgpack", "application/json"] as const;

async function serializePayload(
  data: unknown,
  format: string
): Promise<{ body: BodyInit; contentType: string }> {
  if (format === "application/msgpack") {
    return {
      body: msgpackEncode(data),
      contentType: "application/msgpack",
    };
  }
  return {
    body: JSON.stringify(data),
    contentType: "application/json; charset=utf-8",
  };
}

export async function handleApiRequest(
  request: Request,
  data: unknown
): Promise<Response> {
  const accepted = parseAccept(request.headers.get("Accept"));
  const chosen =
    bestMatch(accepted, [...API_FORMATS]) ?? "application/json";
  const { body, contentType } = await serializePayload(data, chosen);

  return new Response(body as BodyInit, {
    headers: {
      "Content-Type": contentType,
      Vary: "Accept",
      "X-Content-Format": chosen,
    },
  });
}
```

---

## Language Negotiation with KV Fallback

```typescript
const SUPPORTED_LOCALES = ["en", "fr", "de", "es"] as const;
type Locale = (typeof SUPPORTED_LOCALES)[number];

function negotiateLocale(acceptLanguage: string | null): Locale {
  if (!acceptLanguage) return "en";
  const ranges = acceptLanguage
    .split(",")
    .map((part) => {
      const [tag, q] = part.trim().split(";q=");
      return { tag: tag.trim().split("-")[0].toLowerCase(), q: q ? parseFloat(q) : 1.0 };
    })
    .sort((a, b) => b.q - a.q);

  for (const { tag } of ranges) {
    if ((SUPPORTED_LOCALES as readonly string[]).includes(tag)) {
      return tag as Locale;
    }
  }
  return "en";
}

export async function handleLocalizedContent(
  request: Request,
  env: Env,
  slug: string
): Promise<Response> {
  const locale = negotiateLocale(request.headers.get("Accept-Language"));
  const kvKey = `content:${locale}:${slug}`;

  let content = await env.CONTENT_KV.get(kvKey);
  if (!content && locale !== "en") {
    // Fallback to English
    content = await env.CONTENT_KV.get(`content:en:${slug}`);
  }
  if (!content) return new Response("Not Found", { status: 404 });

  return new Response(content, {
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Content-Language": locale,
      Vary: "Accept-Language",
    },
  });
}
```

---

## Cache Key Normalisation with Vary

Workers Cache API requires explicit cache-key construction when `Vary` headers
are involved. The default `fetch()` cache ignores `Vary` in subrequests.

```typescript
function buildCacheKey(request: Request, format: string): Request {
  const url = new URL(request.url);
  url.searchParams.set("__fmt", format.replace("/", "-")); // deterministic suffix
  return new Request(url.toString(), {
    method: "GET",
    headers: { "Cache-Control": request.headers.get("Cache-Control") ?? "" },
  });
}

export async function cachedFormatResponse(
  request: Request,
  env: Env,
  cache: Cache
): Promise<Response> {
  const accepted = parseAccept(request.headers.get("Accept"));
  const format = bestMatch(accepted, ["image/avif", "image/webp", "image/jpeg"]) ?? "image/jpeg";
  const cacheKey = buildCacheKey(request, format);

  const cached = await cache.match(cacheKey);
  if (cached) return cached;

  const response = await fetchVariant(request, format, env);
  await cache.put(cacheKey, response.clone());
  return response;
}

async function fetchVariant(
  _request: Request,
  format: string,
  _env: Env
): Promise<Response> {
  // Implementation-specific variant fetch
  return new Response(`variant:${format}`, { headers: { "Content-Type": format } });
}
```

---

## Anti-patterns

- **Ignoring `Vary` response headers**: Caching a negotiated response without
  `Vary: Accept` serves the wrong format to subsequent clients with different
  preferences.
- **Storing format in URL query params client-side**: Breaks REST semantics;
  format selection is a client capability, not a resource identity.
- **Hardcoding quality values**: Use `q=0` to explicitly exclude unsupported
  types rather than silently falling back in ambiguous ways.
- **Negotiating on POST bodies**: Content negotiation applies to GET/HEAD only;
  POST request body format is signalled by `Content-Type`, not `Accept`.

---

## Gotchas

- Cloudflare's cache treats `Vary: Accept` as uncacheable by default at the
  CDN layer; you must use the Cache API with synthetic cache keys as shown above.
- `image/webp` is broadly supported but `image/avif` decode is CPU-heavier;
  test latency under real-world concurrency before enabling AVIF transcoding.
- MessagePack clients must send `Accept: application/msgpack` — many HTTP
  clients default to `Accept: */*`, which maps to `application/json` via
  quality ordering, so the fallback matters.
- `Accept-Language` wildcard (`*`) must be handled: treat it as lowest priority
  after all explicit tags.

---

## Verification

```bash
# WebP negotiation
curl -H "Accept: image/webp,image/*;q=0.8" https://example.com/images/hero \
  -I | grep -E "content-type|vary|x-format"

# MessagePack negotiation
curl -H "Accept: application/msgpack" https://api.example.com/users/1 \
  -o - | xxd | head

# Language negotiation
curl -H "Accept-Language: fr-FR,fr;q=0.9,en;q=0.5" \
  https://api.example.com/content/about -I | grep -E "content-language|vary"

# No preference → JSON fallback
curl https://api.example.com/users/1 -I | grep content-type
```

---

## Related

- `rfc-8942-client-hints-negotiation-and-variance.md`
- `caching-topology-cloudflare-native.md`
- `edge-cache-invalidation-event-driven-purge.md`
- `api-gateway-patterns-rate-limiting-routing.md`

---

## Sources

- RFC 7231 §5.3 — Content Negotiation
- Cloudflare Workers Cache API documentation
- MDN HTTP Content Negotiation guide
- RFC 9110 §12 — HTTP Semantics, Content Negotiation
