# Automatic Language Detection for i18n Routing

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Your application serves users across multiple locales. You want to:
1. Detect the language of user-submitted content (search queries, messages, form fields)
   without relying on `Accept-Language` headers (which reflect browser settings, not
   content language).
2. Route users to the correct locale variant of your site when the URL does not already
   specify one.
3. Provide fallback content in the correct language when translations are missing.

Rule-based detectors (langdetect, franc) fail on short strings (< 20 chars), mixed-language
text, and code-switched content. LLMs handle all three cases reliably.

## Context

Language detection at the edge fits naturally into a Cloudflare Worker middleware layer.
The detection step can be:

- **Header-based (fast path):** Read `Accept-Language`, `CF-IPCountry`, or a stored user
  preference cookie. No AI call needed.
- **Content-based (ML path):** Run Workers AI when the content itself needs to be
  classified—search queries, user messages, submitted text.

The fast path should always be checked first. The ML path is the fallback for ambiguous
or missing header signals, or when the content language must be trusted over browser locale.

Workers AI provides language models that return ISO 639-1 codes. For dedicated language
identification, `@cf/meta/m2m100-1.2b` (a multilingual translation model) can be queried
in "detection only" mode. Alternatively, small instruction-tuned LLMs handle detection
as a zero-shot classification task with near-perfect accuracy on 20+ tokens.

## Fast-Path Detection Middleware

```typescript
// middleware/language.ts
export interface LangContext {
  lang: string;       // ISO 639-1 code, e.g. "en"
  source: "cookie" | "accept-language" | "cf-country" | "ai" | "default";
  confidence: number; // 0.0–1.0
}

export function detectFromHeaders(request: Request): LangContext | null {
  // 1. Explicit user preference (highest priority)
  const cookie = parseCookie(request.headers.get("Cookie") ?? "");
  if (cookie["lang"] && isValidLang(cookie["lang"])) {
    return { lang: cookie["lang"], source: "cookie", confidence: 1.0 };
  }

  // 2. Accept-Language header
  const acceptLang = request.headers.get("Accept-Language");
  if (acceptLang) {
    const primary = acceptLang.split(",")[0].split(";")[0].trim().slice(0, 2).toLowerCase();
    if (isValidLang(primary)) {
      return { lang: primary, source: "accept-language", confidence: 0.8 };
    }
  }

  // 3. Cloudflare IP geolocation → map country to default language
  const country = request.headers.get("CF-IPCountry");
  if (country) {
    const lang = COUNTRY_TO_LANG[country];
    if (lang) return { lang, source: "cf-country", confidence: 0.65 };
  }

  return null;
}

// Country → default language mapping (partial example)
const COUNTRY_TO_LANG: Record<string, string> = {
  US: "en", GB: "en", AU: "en", CA: "en",
  DE: "de", AT: "de", CH: "de",
  FR: "fr", BE: "fr",
  ES: "es", MX: "es", AR: "es",
  BR: "pt", PT: "pt",
  JP: "ja", KR: "ko", CN: "zh",
  RU: "ru", UA: "uk", PL: "pl",
  IT: "it", NL: "nl", SE: "sv",
};
```

## AI-Based Content Language Detection

```typescript
// workers-ai language detection for user-supplied text
export async function detectContentLanguage(
  ai: Ai,
  text: string
): Promise<LangContext> {
  // Very short strings are unreliable—default to "en"
  if (text.trim().length < 5) {
    return { lang: "en", source: "default", confidence: 0.3 };
  }

  const supported = ["en","es","fr","de","pt","it","ja","ko","zh","ru","ar","hi","nl","pl","sv","uk","tr"];

  const prompt =
    `Identify the language of the following text. ` +
    `Reply with ONLY the ISO 639-1 two-letter language code from this list: ${supported.join(", ")}.\n\n` +
    `Text: "${text.slice(0, 300)}"`;

  try {
    const response = await ai.run("@cf/meta/llama-3.1-8b-instruct", {
      messages: [{ role: "user", content: prompt }],
      max_tokens: 8,
      temperature: 0.0,
    });

    const raw = ((response as { response: string }).response ?? "").trim().toLowerCase().slice(0, 2);

    if (supported.includes(raw)) {
      return { lang: raw, source: "ai", confidence: 0.92 };
    }
  } catch {
    // Fall through to default
  }

  return { lang: "en", source: "default", confidence: 0.3 };
}
```

## i18n URL Routing Middleware

```typescript
// Routing: /search?q=Bonjour → /fr/search?q=Bonjour
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    // Already has locale prefix → pass through
    const localeSegment = url.pathname.split("/")[1];
    const SUPPORTED_LOCALES = ["en", "es", "fr", "de", "pt", "ja", "ko", "zh"];
    if (SUPPORTED_LOCALES.includes(localeSegment)) {
      return fetch(request);
    }

    // Attempt fast-path detection
    let langCtx = detectFromHeaders(request);

    // For search/content endpoints, detect from query param
    if (!langCtx || langCtx.confidence < 0.7) {
      const query = url.searchParams.get("q");
      if (query) {
        langCtx = await detectContentLanguage(env.AI, query);
      }
    }

    const lang = langCtx?.lang ?? "en";
    const locale = SUPPORTED_LOCALES.includes(lang) ? lang : "en";

    // Redirect to locale-prefixed URL
    const localeUrl = new URL(url);
    localeUrl.pathname = `/${locale}${url.pathname}`;

    // Store detected language in cookie for subsequent requests
    const response = Response.redirect(localeUrl.toString(), 302);
    response.headers.set(
      "Set-Cookie",
      `lang=${locale}; Path=/; Max-Age=2592000; SameSite=Lax`
    );
    return response;
  },
};
```

## Caching Detection Results in KV

Language detection for the same query string should be cached to avoid repeated AI calls:

```typescript
async function detectWithCache(
  ai: Ai,
  kv: KVNamespace,
  text: string
): Promise<LangContext> {
  const cacheKey = `lang:${await hashText(text)}`;
  const cached = await kv.get(cacheKey, "json") as LangContext | null;
  if (cached) return cached;

  const result = await detectContentLanguage(ai, text);

  // Cache for 1 hour; language of a string doesn't change
  await kv.put(cacheKey, JSON.stringify(result), { expirationTtl: 3600 });
  return result;
}

async function hashText(text: string): Promise<string> {
  const buf = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(text.slice(0, 300))
  );
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("").slice(0, 16);
}
```

## Handling Mixed-Language Content

Some content switches languages mid-sentence (code-switching). For routing purposes,
detect the dominant language:

```typescript
async function detectDominantLanguage(
  ai: Ai,
  text: string
): Promise<{ dominant: string; mixed: boolean }> {
  const prompt =
    `The following text may contain multiple languages. ` +
    `Identify the DOMINANT language (the language most of the text is written in). ` +
    `Also state if the text mixes languages. ` +
    `Reply with JSON: {"dominant":"<ISO 639-1 code>","mixed":<true|false>}\n\n` +
    `Text: "${text.slice(0, 500)}"`;

  const response = await ai.run("@cf/meta/llama-3.1-8b-instruct", {
    messages: [{ role: "user", content: prompt }],
    response_format: { type: "json_object" },
    max_tokens: 48,
    temperature: 0.0,
  });

  try {
    return JSON.parse((response as { response: string }).response);
  } catch {
    return { dominant: "en", mixed: false };
  }
}
```

## Anti-patterns

- **Calling the LLM on every request.** Language detection from headers is O(1). Only
  invoke AI when headers are absent or unreliable, and cache the result in KV.
- **Redirecting search bots.** Language-based redirects confuse crawlers. Check
  `User-Agent` and serve the canonical URL to bots; only redirect human traffic.
- **Using only `CF-IPCountry` for language.** IP geolocation reflects physical location,
  not language preference. A German expat in Brazil speaks German.
- **Failing closed.** If detection fails, default to `en` (or the most common language
  in your user base). Never return a 500 because language detection errored.
- **Detecting language on every keystroke** in a search box. Debounce detection to fire
  after the user pauses typing (400–600 ms), not on every input event.
- **Storing language in the URL path for SPAs.** Hydration mismatches occur if the
  server-rendered path (`/fr/...`) differs from client-side routing. Use a cookie or
  query param for SPAs to avoid SSR/CSR splits.

## Gotchas

- ISO 639-1 codes are two characters, but some languages need ISO 639-3 (e.g. `cmn` for
  Mandarin Chinese). Decide whether to use `zh` (broad) or `cmn`/`yue` (specific) and
  be consistent.
- `Accept-Language` quality values (`;q=0.9`) are intentionally sent by browsers to
  indicate preference weight, not confidence. Do not interpret them as detection confidence.
- Chinese (`zh`) needs further disambiguation (Simplified vs. Traditional) for some UIs.
  A second pass detecting script (`Hans` vs. `Hant`) can use the `CF-IPCountry` as a
  tiebreaker (CN→Simplified, TW/HK→Traditional).
- Workers AI `temperature=0.0` is greedy decoding and fully deterministic for language
  detection; identical inputs always return identical outputs. This makes KV caching
  100% effective.
- The `CF-IPCountry` header is not available in local `wrangler dev` without the
  `--remote` flag. Detection logic that depends on it will silently fall through to the
  AI path locally.
- Overly short max_tokens (e.g. 4) can truncate a two-letter code if the model emits a
  leading space or newline token. Use 8–12 to be safe.

## Verification

```bash
# Test detection endpoint with French text
curl -X POST https://api.example.com/detect-language \
  -H "Content-Type: application/json" \
  -d '{"text":"Bonjour, comment puis-je vous aider?"}'
# Expected: {"lang":"fr","source":"ai","confidence":0.92}

# Test header-based fast path
curl -H "Accept-Language: de-DE,de;q=0.9" https://example.com/search?q=hello
# Expected: 302 redirect to /de/search?q=hello with Set-Cookie: lang=de

# Verify KV caching (second call should have source="cache")
curl -X POST https://api.example.com/detect-language \
  -H "Content-Type: application/json" \
  -d '{"text":"Bonjour, comment puis-je vous aider?"}'
# Expected: source changes or latency drops significantly

# Test short text fallback
curl -X POST https://api.example.com/detect-language \
  -H "Content-Type: application/json" \
  -d '{"text":"Hi"}'
# Expected: {"lang":"en","source":"default","confidence":0.3}
```

## Related

- `llm-for-classification.md` — zero-shot classification foundations
- `ai-cold-start-patterns.md` — reducing AI call latency for interactive routing
- `llm-for-translation.md` — after detection, translate content to user language
- `semantic-caching-patterns.md` — cache detection results with semantic similarity keys
- `cloudflare-workers-ai-streaming-inference.md` — streaming patterns for AI responses

## Sources

- Cloudflare Workers AI model catalogue: https://developers.cloudflare.com/workers-ai/models/
- IANA Language Subtag Registry: https://www.iana.org/assignments/language-subtag-registry
- Cloudflare `CF-IPCountry` header docs: https://developers.cloudflare.com/fundamentals/reference/http-request-headers/
- Unicode CLDR locale data: https://cldr.unicode.org/
- MDN — Accept-Language: https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Accept-Language
