# Script Detection Unicode Category Workers Language Routing

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A multilingual platform receives user-submitted text — search queries, usernames, chat messages — and must route them to the correct locale pipeline without a reliable `Accept-Language` header. A user typing `Привет` should reach the Cyrillic handler; one typing `مرحبا` should reach the Arabic/RTL pipeline; one typing `こんにちは` should reach CJK processing. Inferring script from Unicode character properties at the edge, before hitting any backend, allows the Worker to make a fast routing decision with no external API call.

---

## Context

Unicode assigns every codepoint a **Script** property (UAX #24). The set of scripts that appear in the dominant run of a string is a reliable proxy for the writing system the user is working in — and therefore for the locale cluster that should handle the request.

Cloudflare Workers do not bundle an ICU data table, so there is no built-in `Unicode.script(cp)` function. However, Workers do support Unicode property escapes in regular expressions (`/\p{Script=...}/u`), which V8 resolves against the ICU data it compiles in. This means script detection via `RegExp.prototype.test` works in the Workers runtime without any polyfill.

The example project platform uses a `SCRIPT_ROUTES` KV namespace that maps detected script codes to locale clusters (e.g., `Cyrl → ["uk", "ru", "bg", "sr"]`). A thin middleware layer reads this map and sets an `X-Detected-Script` header before the request reaches the origin.

---

## Unicode Script Property Regexes in Workers

V8 in Workers supports the full set of Unicode script names available in the bundled ICU. Test a string for a given script with `/\p{Script=<name>}/u`.

```typescript
// src/lib/script-detector.ts

// Ordered by global traffic weight on the platform.
// Each entry: [ISO 15924 code, Unicode Script= value, display label]
const SCRIPT_PROFILES: [string, string, string][] = [
  ["Latn", "Latin",      "Latin"],
  ["Cyrl", "Cyrillic",   "Cyrillic"],
  ["Arab", "Arabic",     "Arabic"],
  ["Deva", "Devanagari", "Devanagari"],
  ["Hans", "Han",        "Han (CJK)"],
  ["Hang", "Hangul",     "Hangul"],
  ["Hebr", "Hebrew",     "Hebrew"],
  ["Thai", "Thai",       "Thai"],
  ["Tibt", "Tibetan",    "Tibetan"],
  ["Grek", "Greek",      "Greek"],
  ["Geor", "Georgian",   "Georgian"],
  ["Armn", "Armenian",   "Armenian"],
  ["Ethi", "Ethiopic",   "Ethiopic"],
  ["Mymr", "Myanmar",    "Myanmar"],
  ["Sinh", "Sinhala",    "Sinhala"],
  ["Khmr", "Khmer",      "Khmer"],
  ["Beng", "Bengali",    "Bengali"],
  ["Gujr", "Gujarati",   "Gujarati"],
  ["Guru", "Gurmukhi",   "Gurmukhi"],
  ["Knda", "Kannada",    "Kannada"],
  ["Mlym", "Malayalam",  "Malayalam"],
  ["Orya", "Oriya",      "Oriya"],
  ["Taml", "Tamil",      "Tamil"],
  ["Telu", "Telugu",     "Telugu"],
  ["Geez", "Ethiopic",   "Ge'ez"],
];

// Build regex cache once at module load (cold start), not per request.
const SCRIPT_REGEX_MAP = new Map<string, RegExp>(
  SCRIPT_PROFILES.map(([code, uname]) => [
    code,
    new RegExp(`\\p{Script=${uname}}`, "u"),
  ])
);

export interface ScriptProfile {
  /** ISO 15924 four-letter code */
  script: string;
  /** Fraction of non-whitespace codepoints in this script, 0–1 */
  dominance: number;
  /** Whether the script is conventionally RTL */
  rtl: boolean;
}

const RTL_SCRIPTS = new Set(["Arab", "Hebr", "Thaa", "Tfng", "Adlm", "Rohg"]);

/**
 * Returns a ranked list of scripts detected in `text`, most dominant first.
 * Only scripts with >5 % presence are returned.
 */
export function detectScripts(text: string): ScriptProfile[] {
  if (!text) return [];

  // Strip whitespace and digits for counting
  const chars = [...text.replace(/[\s\d]/g, "")];
  if (chars.length === 0) return [];

  const counts = new Map<string, number>();
  for (const ch of chars) {
    for (const [code, re] of SCRIPT_REGEX_MAP) {
      if (re.test(ch)) {
        counts.set(code, (counts.get(code) ?? 0) + 1);
        break; // each character assigned to one script only
      }
    }
  }

  const total = chars.length;
  const results: ScriptProfile[] = [];
  for (const [script, count] of counts) {
    const dominance = count / total;
    if (dominance >= 0.05) {
      results.push({ script, dominance, rtl: RTL_SCRIPTS.has(script) });
    }
  }
  results.sort((a, b) => b.dominance - a.dominance);
  return results;
}

/** Returns the single dominant script or null if input is mixed/empty. */
export function dominantScript(text: string): ScriptProfile | null {
  const [top] = detectScripts(text);
  return top?.dominance >= 0.6 ? top : null;
}
```

---

## KV-Backed Script-to-Locale Routing Map

The `SCRIPT_ROUTES` namespace stores JSON arrays keyed by ISO 15924 code. The first element is the canonical locale; remaining elements are fallback candidates fed to Intl.LocaleMatcher.

```typescript
// src/lib/script-router.ts

export interface ScriptRoute {
  locales: string[];       // BCP 47 tags, first is canonical
  pipeline: string;        // downstream handler identifier
  rtl: boolean;
}

const DEFAULT_ROUTE: ScriptRoute = {
  locales: ["en"],
  pipeline: "latin-default",
  rtl: false,
};

export async function resolveRoute(
  script: string,
  kv: KVNamespace
): Promise<ScriptRoute> {
  const raw = await kv.get(`script:${script}`, "json") as ScriptRoute | null;
  return raw ?? DEFAULT_ROUTE;
}

// Example KV entries (set via wrangler kv:key put):
// key: "script:Cyrl"
// value: {"locales":["uk","ru","bg","sr","mk"],"pipeline":"cyrillic","rtl":false}
//
// key: "script:Arab"
// value: {"locales":["ar","fa","ur","ps"],"pipeline":"arabic-rtl","rtl":true}
//
// key: "script:Deva"
// value: {"locales":["hi","mr","ne","bho"],"pipeline":"devanagari","rtl":false}
```

---

## Worker Middleware: Detecting Script and Injecting Routing Headers

```typescript
// src/middleware/script-route.ts

import { dominantScript } from "../lib/script-detector";
import { resolveRoute } from "../lib/script-router";

export interface Env {
  SCRIPT_ROUTES: KVNamespace;
}

/**
 * Reads the request body text (for POST) or `q` query param (for GET)
 * and injects script-routing headers before passing to the next handler.
 */
export async function scriptRouteMiddleware(
  request: Request,
  env: Env,
  next: (req: Request) => Promise<Response>
): Promise<Response> {
  let sample = "";

  const url = new URL(request.url);
  const method = request.method.toUpperCase();

  if (method === "GET") {
    sample = url.searchParams.get("q") ?? "";
  } else if (method === "POST") {
    const ct = request.headers.get("Content-Type") ?? "";
    if (ct.includes("application/json")) {
      try {
        const body = await request.clone().json<{ q?: string; text?: string }>();
        sample = body.q ?? body.text ?? "";
      } catch {
        // malformed JSON: route without script detection
      }
    } else if (ct.includes("text/plain")) {
      sample = await request.clone().text();
    }
  }

  const truncated = sample.slice(0, 500); // cap at 500 chars for perf
  const profile = dominantScript(truncated);

  const mutated = new Request(request);
  const headers = new Headers(request.headers);

  if (profile) {
    const route = await resolveRoute(profile.script, env.SCRIPT_ROUTES);
    headers.set("X-Detected-Script", profile.script);
    headers.set("X-Detected-Locale", route.locales[0]);
    headers.set("X-Locale-Pipeline", route.pipeline);
    headers.set("X-Text-Dir", profile.rtl ? "rtl" : "ltr");
    headers.set("X-Script-Dominance", profile.dominance.toFixed(2));
  } else {
    headers.set("X-Detected-Script", "Zyyy"); // ISO 15924: Common
    headers.set("X-Detected-Locale", "en");
    headers.set("X-Locale-Pipeline", "latin-default");
    headers.set("X-Text-Dir", "ltr");
  }

  return next(new Request(request.url, { ...request, headers }));
}
```

---

## Logging Detected Script Distribution to D1

Track which scripts are most common to tune KV route coverage and catch gaps.

```typescript
// src/lib/script-analytics.ts

export interface Env {
  DB: D1Database;
}

export async function logScriptEvent(
  script: string,
  locale: string,
  ctx: ExecutionContext,
  env: Env
): Promise<void> {
  // Use waitUntil so analytics never delay the response
  ctx.waitUntil(
    env.DB.prepare(
      `INSERT INTO script_detections (script, resolved_locale, detected_at)
       VALUES (?, ?, unixepoch())`
    )
      .bind(script, locale)
      .run()
      .catch(() => {
        // Non-critical: swallow D1 write errors for analytics
      })
  );
}
```

```sql
-- migrations/0002_script_detections.sql

CREATE TABLE IF NOT EXISTS script_detections (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  script          TEXT    NOT NULL,
  resolved_locale TEXT    NOT NULL,
  detected_at     INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_script_detections_script
  ON script_detections (script, detected_at DESC);
```

---

## Anti-patterns

- **Using `charCodeAt` comparisons for script detection.** Hard-coded Unicode range checks (e.g., `cp >= 0x0600 && cp <= 0x06FF` for Arabic) miss Extended Arabic, Arabic Supplement, and Presentation Forms blocks. Use `\p{Script=Arabic}` instead.
- **Detecting script on the full body.** For routing purposes, 100–500 characters is sufficient. Reading the full body burns memory and adds latency for large payloads.
- **Treating CJK as a single locale.** Han (`Hans`/`Hant`) characters appear in Chinese, Japanese, and Korean. After detecting Han, use secondary signals (Hiragana/Katakana presence for Japanese, Hangul for Korean) to disambiguate.
- **Overwriting a user-explicit `Accept-Language` header.** Script detection is a fallback. If the user sent a valid `Accept-Language`, honor it over the detected script.
- **Caching script route lookups in memory across requests.** Workers share isolates but memory is not reliably shared between requests. Use KV with a reasonable TTL (e.g., 300 s) instead of in-memory Maps.

---

## Gotchas

- `\p{Script=Han}` matches all CJK Unified Ideographs but also kanji in Japanese and hanja in Korean. Always check for Hiragana/Katakana before concluding Chinese.
- The `Script` property is distinct from `Script_Extensions`. A character can belong to multiple script extensions (e.g., U+0040 `@` is Common but used in many scripts). `\p{Script=Latin}` will **not** match `@`, which is correct for routing.
- Workers execute regex engine code at isolate startup. A module-level `new RegExp(...)` runs once per isolate cold start, not once per request — this is the desired behavior for the regex cache pattern above.
- ISO 15924 codes are four characters (first uppercase): `Cyrl`, not `cyrl` or `CYRL`. KV key casing must match the codes emitted by `detectScripts`.
- `String` iteration via `for...of` yields Unicode codepoints (not UTF-16 code units), which is correct for codepoint-level script detection. `s[i]` indexing is not safe for non-BMP characters.

---

## Verification

```typescript
// tests/script-detector.test.ts
import { describe, it, expect } from "vitest";
import { detectScripts, dominantScript } from "../src/lib/script-detector";

describe("detectScripts", () => {
  it("detects Cyrillic from Russian text", () => {
    const result = dominantScript("Привет мир, как дела");
    expect(result?.script).toBe("Cyrl");
    expect(result?.rtl).toBe(false);
  });

  it("detects Arabic and marks RTL", () => {
    const result = dominantScript("مرحبا بالعالم");
    expect(result?.script).toBe("Arab");
    expect(result?.rtl).toBe(true);
  });

  it("returns null for mixed short text below 60% threshold", () => {
    // 50/50 Latin and Cyrillic
    const result = dominantScript("hello привет world мир");
    expect(result).toBeNull();
  });

  it("detects Devanagari", () => {
    const result = dominantScript("नमस्ते दुनिया");
    expect(result?.script).toBe("Deva");
  });

  it("detects Han for Chinese", () => {
    const profiles = detectScripts("你好世界");
    expect(profiles[0].script).toBe("Hans");
  });
});
```

Run: `npx vitest run tests/script-detector.test.ts`

Verify routing headers in production with `curl -s -D - -o /dev/null -X GET 'https://api.example.com/search?q=Привет'` and confirm `X-Detected-Script: Cyrl` appears in the response headers.

---

## Related

- `unicode-script-extensions-mixed-script-analysis.md`
- `language-detection-workers-accept-language.md`
- `cloudflare-workers-geolocation-locale-routing.md`
- `bidi-algorithm-unicode.md`
- `locale-negotiation-accept-language.md`

---

## Sources

- Unicode Standard Annex #24, Unicode Script Property: https://www.unicode.org/reports/tr24/
- V8 Unicode property escapes: https://v8.dev/features/regexp-unicode-property-escapes
- ISO 15924, Codes for the Representation of Names of Scripts: https://www.unicode.org/iso15924/
- Cloudflare Workers Regex support: https://developers.cloudflare.com/workers/runtime-apis/web-standards/
- IANA Language Subtag Registry (Script subtags): https://www.iana.org/assignments/language-subtag-registry/
