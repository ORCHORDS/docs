# Workers AI Multilingual Translation

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to translate user-facing strings to the visitor's locale inside a Cloudflare Worker with no third-party translation API, automatically detecting the target language from the `Accept-Language` header and Cloudflare's `cf.country` geolocation, caching translations in KV to avoid repeated inference calls, and supporting a batch endpoint for translating up to 50 strings per request.

---

## Context

`@cf/meta/m2m100-1.2b` (M2M-100) is a many-to-many multilingual translation model supporting 100 languages. The Workers AI binding accepts `input_text`, `source_lang`, and `target_lang` as ISO 639-1 codes. Auto-detecting the locale from the visitor's `Accept-Language` header (parsed with priority weights) and `cf.country` allows zero-configuration personalisation. KV caching with a `{sha256(source_text)}:{target_lang}` composite key prevents re-inference for repeated strings and dramatically reduces neuron budget consumption. Batch translation accepts an array of strings and fans them out to parallel `env.AI.run()` calls (up to Cloudflare's concurrency limit) for throughput.

---

## Section 1 — wrangler.toml / Config

```toml
name = "translation-worker"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[ai]
binding = "AI"

[[kv_namespaces]]
binding = "TRANSLATION_KV"
id = "<your-kv-namespace-id>"

[vars]
DEFAULT_SOURCE_LANG = "en"
DEFAULT_TARGET_LANG = "es"
CACHE_TTL_SECONDS = "86400"  # 24 hours
MAX_BATCH_SIZE = "50"
```

## Section 2 — Worker implementation

```typescript
interface Env {
  AI: Ai;
  TRANSLATION_KV: KVNamespace;
  DEFAULT_SOURCE_LANG: string;
  DEFAULT_TARGET_LANG: string;
  CACHE_TTL_SECONDS: string;
  MAX_BATCH_SIZE: string;
}

interface TranslationOutput {
  translated_text: string;
}

interface TranslateRequest {
  text: string;
  source_lang?: string;
  target_lang?: string;
}

interface BatchTranslateRequest {
  strings: string[];
  source_lang?: string;
  target_lang?: string;
}

// ─── Language detection helpers ───────────────────────────────────────────────

/**
 * Parse Accept-Language header and return the highest-priority language tag.
 * Example: 'fr-FR,fr;q=0.9,en;q=0.8' → 'fr'
 */
function parseAcceptLanguage(header: string | null): string | null {
  if (!header) return null;
  const parts = header.split(',').map((part) => {
    const [tag, q] = part.trim().split(';q=');
    return { tag: tag.trim().split('-')[0].toLowerCase(), q: parseFloat(q ?? '1') };
  });
  parts.sort((a, b) => b.q - a.q);
  return parts[0]?.tag ?? null;
}

// Map Cloudflare country codes to ISO 639-1 language codes
const COUNTRY_TO_LANG: Record<string, string> = {
  BR: 'pt', CN: 'zh', DE: 'de', ES: 'es', FR: 'fr',
  IT: 'it', JP: 'ja', KR: 'ko', MX: 'es', NL: 'nl',
  PL: 'pl', PT: 'pt', RU: 'ru', SA: 'ar', SE: 'sv',
  TR: 'tr', TW: 'zh', UA: 'uk', VN: 'vi',
};

/**
 * Determine the target language from request context.
 * Priority: explicit param > Accept-Language > cf.country > default.
 */
function detectTargetLang(
  request: Request,
  explicitLang: string | undefined,
  defaultLang: string
): string {
  if (explicitLang) return explicitLang.toLowerCase().slice(0, 2);

  const fromHeader = parseAcceptLanguage(request.headers.get('Accept-Language'));
  if (fromHeader && fromHeader !== 'en') return fromHeader;

  const country = (request.cf as { country?: string } | undefined)?.country ?? '';
  const fromCountry = COUNTRY_TO_LANG[country.toUpperCase()];
  if (fromCountry) return fromCountry;

  return defaultLang;
}

// ─── KV cache helpers ─────────────────────────────────────────────────────────

async function cacheKey(text: string, targetLang: string): Promise<string> {
  const encoder = new TextEncoder();
  const data = encoder.encode(text + '|' + targetLang);
  const hashBuffer = await crypto.subtle.digest('SHA-256', data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  const hashHex = hashArray.map((b) => b.toString(16).padStart(2, '0')).join('');
  return `tr:${hashHex.slice(0, 32)}:${targetLang}`;
}

async function getCached(kv: KVNamespace, key: string): Promise<string | null> {
  return kv.get(key);
}

async function setCached(
  kv: KVNamespace,
  key: string,
  value: string,
  ttlSeconds: number
): Promise<void> {
  await kv.put(key, value, { expirationTtl: ttlSeconds });
}

// ─── Translation ──────────────────────────────────────────────────────────────

async function translateText(
  ai: Ai,
  kv: KVNamespace,
  text: string,
  sourceLang: string,
  targetLang: string,
  ttlSeconds: number
): Promise<string> {
  // Same language — skip inference
  if (sourceLang === targetLang) return text;

  const key = await cacheKey(text, targetLang);
  const cached = await getCached(kv, key);
  if (cached !== null) return cached;

  const result = (await ai.run('@cf/meta/m2m100-1.2b', {
    text,
    source_lang: sourceLang,
    target_lang: targetLang,
  })) as TranslationOutput;

  const translated = result.translated_text;
  await setCached(kv, key, translated, ttlSeconds);
  return translated;
}

// ─── Route handlers ───────────────────────────────────────────────────────────

async function handleSingleTranslate(
  request: Request,
  env: Env
): Promise<Response> {
  const body = await request.json<TranslateRequest>();
  if (!body.text?.trim()) {
    return new Response(
      JSON.stringify({ error: '`text` is required' }),
      { status: 400, headers: { 'Content-Type': 'application/json' } }
    );
  }

  const sourceLang = (body.source_lang ?? env.DEFAULT_SOURCE_LANG).toLowerCase();
  const targetLang = detectTargetLang(request, body.target_lang, env.DEFAULT_TARGET_LANG);
  const ttl = parseInt(env.CACHE_TTL_SECONDS, 10);

  const translated = await translateText(
    env.AI,
    env.TRANSLATION_KV,
    body.text.trim(),
    sourceLang,
    targetLang,
    ttl
  );

  return Response.json({
    source_lang: sourceLang,
    target_lang: targetLang,
    original: body.text.trim(),
    translated,
  });
}

async function handleBatchTranslate(
  request: Request,
  env: Env
): Promise<Response> {
  const body = await request.json<BatchTranslateRequest>();
  const maxBatch = parseInt(env.MAX_BATCH_SIZE, 10);

  if (!Array.isArray(body.strings) || body.strings.length === 0) {
    return new Response(
      JSON.stringify({ error: '`strings` must be a non-empty array' }),
      { status: 400, headers: { 'Content-Type': 'application/json' } }
    );
  }

  if (body.strings.length > maxBatch) {
    return new Response(
      JSON.stringify({ error: `Maximum ${maxBatch} strings per batch request` }),
      { status: 422, headers: { 'Content-Type': 'application/json' } }
    );
  }

  const sourceLang = (body.source_lang ?? env.DEFAULT_SOURCE_LANG).toLowerCase();
  const targetLang = detectTargetLang(request, body.target_lang, env.DEFAULT_TARGET_LANG);
  const ttl = parseInt(env.CACHE_TTL_SECONDS, 10);

  // Fan out all translations in parallel
  const translations = await Promise.all(
    body.strings.map((text) =>
      translateText(env.AI, env.TRANSLATION_KV, text.trim(), sourceLang, targetLang, ttl)
    )
  );

  const results = body.strings.map((original, i) => ({
    original: original.trim(),
    translated: translations[i],
  }));

  return Response.json({
    source_lang: sourceLang,
    target_lang: targetLang,
    count: results.length,
    results,
  });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    if (url.pathname === '/translate') {
      return handleSingleTranslate(request, env);
    }
    if (url.pathname === '/translate/batch') {
      return handleBatchTranslate(request, env);
    }

    return new Response('Not found', { status: 404 });
  },
};
```

## Section 3 — Cache warming and cache invalidation

```typescript
// Warm the KV cache for a known set of UI strings on deploy.
// Run via a Cron Trigger or a one-off fetch to /warm.

const UI_STRINGS = [
  'Welcome to our platform',
  'Sign in',
  'Sign out',
  'Submit',
  'Cancel',
  'Loading…',
  'An error occurred. Please try again.',
];

const SUPPORTED_LANGS = ['es', 'fr', 'de', 'pt', 'it', 'ja', 'ko', 'zh', 'ar', 'ru'];

async function warmCache(ai: Ai, kv: KVNamespace, ttlSeconds: number): Promise<void> {
  const tasks: Promise<void>[] = [];

  for (const lang of SUPPORTED_LANGS) {
    for (const text of UI_STRINGS) {
      tasks.push(
        translateText(ai, kv, text, 'en', lang, ttlSeconds).then(() => undefined)
      );
    }
  }

  // Run in parallel but cap concurrency to avoid hitting AI rate limits
  const CONCURRENCY = 5;
  for (let i = 0; i < tasks.length; i += CONCURRENCY) {
    await Promise.all(tasks.slice(i, i + CONCURRENCY));
  }
}

// Invalidate all cached translations for a specific string (e.g., after copy changes)
async function invalidateString(
  kv: KVNamespace,
  text: string,
  langs: string[]
): Promise<void> {
  await Promise.all(
    langs.map(async (lang) => {
      const key = await cacheKey(text, lang);
      await kv.delete(key);
    })
  );
}

export { warmCache, invalidateString };
```

---

## Anti-patterns

- **Passing full page HTML to the model** — M2M-100 is a sentence-level model; feeding it multi-paragraph HTML degrades quality. Split content into individual strings before translating.
- **Using country code as the only language signal** — Many countries are multilingual (e.g., CH: de/fr/it). Always prefer `Accept-Language` over `cf.country`.
- **Skipping the KV cache** — Each M2M-100 invocation consumes ~0.3 M neurons. Translating the same string repeatedly without caching will exhaust your budget quickly.
- **Concatenating strings before translation** — Concatenation with delimiters (e.g., `|||`) causes the model to copy delimiters into output or split words incorrectly. Translate each string independently.

---

## Gotchas

- M2M-100 uses ISO 639-1 language codes but some less common languages need ISO 639-2/3 codes (e.g., `"zh"` works for Chinese but `"cmn"` does not). Test your target languages explicitly.
- The model may transliterate rather than translate for some source/target pairs. Validate output for your top locales manually.
- `Promise.all()` with 50 concurrent AI calls may hit Cloudflare's per-colo AI concurrency limit; cap parallelism to 5–10 for batch endpoints.
- `crypto.subtle.digest` is available in Workers but requires no polyfills; do not import a Node.js crypto shim.
- KV `expirationTtl` must be at least 60 seconds; do not use shorter TTLs for translation caches.
- `request.cf` is typed as `IncomingRequestCfProperties | undefined`; always guard with optional chaining.

---

## Verification

```bash
# Deploy
npx wrangler deploy

# Single translation (auto-detect target from Accept-Language)
curl -X POST https://translation-worker.<your-subdomain>.workers.dev/translate \
  -H 'Content-Type: application/json' \
  -H 'Accept-Language: fr-FR,fr;q=0.9,en;q=0.8' \
  -d '{"text":"Hello, welcome to our platform!"}'

# Single translation with explicit languages
curl -X POST https://translation-worker.<your-subdomain>.workers.dev/translate \
  -H 'Content-Type: application/json' \
  -d '{"text":"Good morning","source_lang":"en","target_lang":"ja"}'

# Batch translation (up to 50 strings)
curl -X POST https://translation-worker.<your-subdomain>.workers.dev/translate/batch \
  -H 'Content-Type: application/json' \
  -d '{
    "strings": ["Sign in", "Sign out", "Submit", "Cancel"],
    "source_lang": "en",
    "target_lang": "de"
  }' | jq '.results'

# Second request for same text — should return from KV cache (faster response time)
curl -X POST https://translation-worker.<your-subdomain>.workers.dev/translate \
  -H 'Content-Type: application/json' \
  -d '{"text":"Good morning","source_lang":"en","target_lang":"ja"}'
```

---

## Related

- `workers-ai-text-classification-moderation.md`
- `workers-ai-embeddings-vectorize-semantic-search.md`
- `workers-ai-whisper-speech-to-text.md`

---

## Sources

- Workers AI M2M-100 model — https://developers.cloudflare.com/workers-ai/models/m2m100-1.2b/
- Workers AI supported languages — https://developers.cloudflare.com/workers-ai/models/m2m100-1.2b/#supported-languages
- KV Namespace caching — https://developers.cloudflare.com/kv/api/write-key-value-pairs/
- Cloudflare cf object — https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
