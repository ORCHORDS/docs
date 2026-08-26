# Myanmar Zawgyi-to-Unicode Conversion in Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
User-generated content or legacy API responses from Myanmar contain Zawgyi-encoded text that renders
as gibberish in modern browsers expecting Unicode Myanmar, breaking search, sorting, and display.

## Context
Zawgyi is a legacy Myanmar encoding that reuses Unicode Myanmar codepoints in incompatible ways. It
was the dominant encoding on older Android phones and still appears in databases, imported CSVs, and
third-party feeds. A Cloudflare Worker sitting in front of your origin is the right place to detect
and normalise Zawgyi to Unicode NFC before the response reaches the client. The `myanmar-tools`
algorithm (open-source, Apache 2.0) provides a byte-pattern classifier that works without a DOM.

## Zawgyi Detection at the Edge

Zawgyi text contains statistical patterns (e.g. heavy use of U+103A immediately after vowels) that
differ from valid Unicode Myanmar. A lightweight port of the `myanmar-tools` detector can run as a
pure Worker module with no npm dependencies.

```typescript
// zawgyi-detector.ts
const ZAWGYI_SIGNALS = [
  /ျ[ေြ]/,   // medial ra + vowel (rare in Unicode)
  /ွှ/,            // medial wa + ha stack (Zawgyi-only sequence)
  /[ါာ]္/,   // vowel then asat (inverted order vs Unicode)
];

export function isLikelyZawgyi(text: string): boolean {
  let hits = 0;
  for (const re of ZAWGYI_SIGNALS) {
    if (re.test(text)) hits++;
  }
  return hits >= 2;
}
```

## Zawgyi-to-Unicode Conversion Rules

The conversion is a finite set of string-replacement rules ordered by precedence. Storing the rule
table in a Cloudflare KV namespace keeps the Worker bundle small — rules are fetched once and cached
in-process for the lifetime of the isolate.

```typescript
// converter.ts
type Rule = [RegExp, string];

let ruleCache: Rule[] | null = null;

async function loadRules(kv: KVNamespace): Promise<Rule[]> {
  if (ruleCache) return ruleCache;
  const raw = await kv.get("zawgyi_rules_v3", "json") as [string, string][];
  ruleCache = raw.map(([pattern, replacement]) => [new RegExp(pattern, "g"), replacement]);
  return ruleCache;
}

export async function zawgyiToUnicode(input: string, kv: KVNamespace): Promise<string> {
  const rules = await loadRules(kv);
  let output = input;
  for (const [re, replacement] of rules) {
    output = output.replace(re, replacement);
  }
  // Always normalise to NFC after conversion
  return output.normalize("NFC");
}
```

## Worker Middleware: Intercept and Convert Response Bodies

Wrap your origin fetch with a `TransformStream` that detects and converts Zawgyi in the response
body. Only apply to `text/html`, `text/plain`, and `application/json` content types.

```typescript
// worker.ts
import { isLikelyZawgyi } from "./zawgyi-detector";
import { zawgyiToUnicode } from "./converter";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const origin = await fetch(request);
    const ct = origin.headers.get("content-type") ?? "";
    const isText = /text\/|application\/json/.test(ct);
    if (!isText || !origin.body) return origin;

    const { readable, writable } = new TransformStream<Uint8Array, Uint8Array>({
      async transform(chunk, controller) {
        const text = new TextDecoder("utf-8").decode(chunk);
        const converted = isLikelyZawgyi(text)
          ? await zawgyiToUnicode(text, env.ZAWGYI_KV)
          : text;
        controller.enqueue(new TextEncoder().encode(converted));
      },
    });

    origin.body.pipeTo(writable);
    const headers = new Headers(origin.headers);
    headers.set("X-Myanmar-Encoding", "unicode-normalised");
    return new Response(readable, { status: origin.status, headers });
  },
};
```

## Caching Converted Strings in D1

For high-traffic strings (e.g. product names in a catalogue), cache the Zawgyi→Unicode mapping in
D1 to avoid repeated rule evaluation. Use a SHA-256 hash of the raw bytes as the cache key.

```typescript
// cache.ts
async function convertWithCache(
  raw: string,
  kv: KVNamespace,
  db: D1Database
): Promise<string> {
  const hash = await sha256Hex(raw);
  const row = await db
    .prepare("SELECT unicode_text FROM zawgyi_cache WHERE zawgyi_hash = ?")
    .bind(hash)
    .first<{ unicode_text: string }>();
  if (row) return row.unicode_text;

  const converted = await zawgyiToUnicode(raw, kv);
  await db
    .prepare("INSERT OR IGNORE INTO zawgyi_cache (zawgyi_hash, unicode_text) VALUES (?, ?)")
    .bind(hash, converted)
    .run();
  return converted;
}

async function sha256Hex(text: string): Promise<string> {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, "0")).join("");
}
```

## Serving the Correct Font

Even after Unicode conversion, browsers need a Zawgyi-aware font fallback removed and a proper
Unicode Myanmar font (Noto Sans Myanmar, Padauk) served. Inject a `<link>` or `font-face` override
via an HTMLRewriter pass that runs after the body transform.

```typescript
// font-injector.ts
export function injectMyanmarFont(response: Response): Response {
  return new HTMLRewriter()
    .on("head", {
      element(el) {
        el.prepend(
          `<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+Myanmar:wght@400;700&display=swap">
           <style>*{font-family:'Noto Sans Myanmar',Pyidaungsu,sans-serif}</style>`,
          { html: true }
        );
      },
    })
    .transform(response);
}
```

## Anti-patterns
- Detecting Zawgyi by checking for the Zawgyi-One font name in CSS — font names are often stripped
- Applying conversion unconditionally without detection — NFC Unicode Myanmar will be double-converted
- Splitting the response body at fixed byte boundaries — may split a multi-byte Myanmar codepoint
- Storing Zawgyi text in D1 — always convert before INSERT; index on the Unicode form only

## Gotchas
- Zawgyi and Unicode Myanmar share codepoints U+1000–U+109F; you cannot rely on codepoint range alone
- Some Myanmar text mixes Zawgyi and Unicode within a single string (legacy copy-paste); process sentence-by-sentence
- The Zawgyi classifier scores vary by text length — short strings (< 20 chars) produce unreliable results
- After `zawgyiToUnicode`, always call `.normalize("NFC")` — some rules produce NFD intermediates
- Workers isolate memory is reset per request; hold the rule cache in a module-level variable, not `globalThis`

## Verification
1. Send a known Zawgyi string (e.g. `မြန်မာ`) to the Worker and assert
   the response body equals the Unicode equivalent `မြန်နာ` after NFC.
2. Use Playwright to screenshot a page with Myanmar text and compare against a reference rendered with
   Noto Sans Myanmar — pixel diff should be < 0.5%.
3. Send valid Unicode Myanmar through the detector and assert `isLikelyZawgyi` returns `false`.
4. Query D1 cache table after 100 conversion requests and confirm hit rate > 95% for repeated strings.

## Related
- `/documentation/categories/i18n/indic-script-rendering.md`
- `/documentation/categories/i18n/ethiopic-amharic-script-rendering-workers.md`
- `/documentation/categories/i18n/unicode-normalization-nfc-nfd.md`
- `/documentation/categories/i18n/multilingual-font-loading-subsetting.md`
- `/documentation/categories/i18n/translation-kv-caching-ttl-strategy.md`

## Sources
- Myanmar Tools (Google): https://github.com/google/myanmar-tools
- Unicode Myanmar block: https://www.unicode.org/charts/PDF/U1000.pdf
- Cloudflare HTMLRewriter: https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/
- Zawgyi-Unicode conversion rules: https://github.com/nickcoutsos/zawgyi-unicode-converter
