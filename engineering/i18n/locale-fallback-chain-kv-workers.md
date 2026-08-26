# Multi-Locale Fallback Chain for Translation Lookups in KV

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You store translations in Cloudflare KV and need a `t(key, locale)` function that gracefully falls back from `en-GB` to `en` to a hard-coded default, without hammering KV with redundant reads, and without blocking the response on cold locale-file fetches.

## Context

Cloudflare KV is eventually consistent and optimised for read-heavy workloads. A per-key lookup for every translatable string is expensive; bulk-loading a locale's entire JSON map with a single `KV.get` call and caching it in memory for the lifetime of the Worker isolate keeps KV reads to one per locale per isolate. Fallback chain config is itself stored in KV (`i18n:fallback:<locale>`) so it can be updated without redeployment.

---

## Core Implementation

```typescript
// types.ts
export type TranslationMap = Record<string, string>;
export type FallbackChain = string[]; // ordered, most-specific first

export interface Env {
  I18N: KVNamespace;
}

// i18n.ts
const localeCache = new Map<string, TranslationMap>();

/** Load a locale JSON map from KV (or return cached copy). */
async function loadLocale(
  kv: KVNamespace,
  locale: string,
  ctx: ExecutionContext
): Promise<TranslationMap> {
  if (localeCache.has(locale)) return localeCache.get(locale)!;

  const raw = await kv.get(`i18n:${locale}:_bundle`, { type: "text" });
  const map: TranslationMap = raw ? JSON.parse(raw) : {};

  localeCache.set(locale, map);

  // Refresh in background so next isolate picks up changes
  ctx.waitUntil(
    kv.get(`i18n:${locale}:_bundle`, { type: "text" }).then((fresh) => {
      if (fresh) localeCache.set(locale, JSON.parse(fresh));
    })
  );

  return map;
}

/** Read fallback chain from KV, e.g. ["en-GB", "en", "en-US"]. */
async function getFallbackChain(
  kv: KVNamespace,
  locale: string
): Promise<FallbackChain> {
  const raw = await kv.get(`i18n:fallback:${locale}`, { type: "text" });
  if (raw) return JSON.parse(raw) as FallbackChain;
  // Default: strip region subtag, then bare fallback
  const bare = locale.split("-")[0];
  return locale === bare ? [locale] : [locale, bare];
}

/**
 * Translate a key with locale fallback.
 * Returns the key itself when no translation is found anywhere in the chain.
 */
export async function t(
  key: string,
  locale: string,
  env: Env,
  ctx: ExecutionContext,
  defaultValue?: string
): Promise<string> {
  const chain = await getFallbackChain(env.I18N, locale);

  for (const l of chain) {
    const map = await loadLocale(env.I18N, l, ctx);
    if (map[key] !== undefined) return map[key];
  }

  return defaultValue ?? key;
}

// Worker entry point
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const locale = request.headers.get("Accept-Language")?.split(",")[0].trim() ?? "en";
    const greeting = await t("home.greeting", locale, env, ctx, "Hello");
    return new Response(greeting);
  },
};
```

---

## KV Key Scheme

| KV key | Value | Description |
|---|---|---|
| `i18n:<locale>:_bundle` | `{"key": "value", ...}` (JSON) | Full locale translation map |
| `i18n:fallback:<locale>` | `["en-GB", "en"]` (JSON array) | Ordered fallback chain |
| `i18n:<locale>:<key>` | `string` | Optional per-key override (takes priority) |

The `_bundle` suffix is reserved. Per-key KV entries are a secondary lookup path for hotfix overrides without redeploying the bundle.

---

## Per-Key Override Path

Extend `loadLocale` to first check `i18n:<locale>:<key>` before consulting the bundle. Useful for A/B copy tests:

```typescript
export async function tWithOverride(
  key: string,
  locale: string,
  env: Env,
  ctx: ExecutionContext
): Promise<string> {
  // Check per-key override first
  const override = await env.I18N.get(`i18n:${locale}:${key}`, { type: "text" });
  if (override !== null) return override;
  return t(key, locale, env, ctx);
}
```

---

## Management Endpoint: Uploading a Locale Bundle

Secure this endpoint with a secret header or Cloudflare Access:

```typescript
if (request.method === "PUT" && url.pathname.startsWith("/admin/i18n/")) {
  const locale = url.pathname.split("/").at(-1)!;
  const body = await request.text();
  // Validate JSON before writing
  JSON.parse(body); // throws on invalid JSON
  await env.I18N.put(`i18n:${locale}:_bundle`, body);
  localeCache.delete(locale); // bust isolate cache
  return new Response(`Uploaded bundle for ${locale}`, { status: 200 });
}
```

Uploading a new bundle invalidates the in-memory cache for the current isolate. Other isolates pick it up on their next `ctx.waitUntil` background refresh.

---

## Anti-patterns

- One KV `get` call per translation key per request — O(n) KV reads per response, latency compounds.
- Hard-coding fallback chains in Worker source code — requires redeployment to change language hierarchy.
- Storing the entire chain as one flat namespace without a key prefix — collides with non-i18n KV data.
- Using `kv.list()` to discover available locales at request time — slow and not cache-friendly.

---

## Gotchas

- **KV consistency**: KV changes take up to 60 seconds to propagate globally. The `ctx.waitUntil` refresh pattern updates the isolate after the first cold read but does not guarantee immediate consistency across all edge nodes.
- **Isolate lifetime**: The in-memory `localeCache` Map lives only as long as the isolate. A new isolate (cold start) must re-fetch from KV.
- **Bundle size**: KV values are limited to 25 MiB. Large locale bundles should be split by namespace (e.g., `i18n:en:_bundle:marketing`, `i18n:en:_bundle:checkout`).
- **Circular fallback**: If `i18n:fallback:en` points to `["en-GB"]` and `i18n:fallback:en-GB` points to `["en"]`, the loop in `t()` will not infinitely recurse (it is not recursive) but it will make redundant KV reads.

---

## Verification

```bash
# Upload a test bundle
curl -X PUT https://your-worker.workers.dev/admin/i18n/en-GB \
  -H "Content-Type: application/json" \
  -d '{"home.greeting": "Hullo!"}'

# Request with en-GB locale
curl https://your-worker.workers.dev/ -H "Accept-Language: en-GB"
# Expected: Hullo!

# Request with en-AU (no bundle) falls back to en-GB
curl https://your-worker.workers.dev/ -H "Accept-Language: en-AU"
# Expected: Hullo! (via fallback chain)
```

---

## Related

- `language-detection-workers-ai-d1.md`
- `intl-segmenter-text-tokenization-workers.md`
- `rtl-html-attribute-injection-workers.md`

## Sources

- Cloudflare KV documentation — https://developers.cloudflare.com/kv/
- `ExecutionContext.waitUntil` — https://developers.cloudflare.com/workers/runtime-apis/context/
- BCP 47 language tags — https://www.rfc-editor.org/rfc/rfc5646
