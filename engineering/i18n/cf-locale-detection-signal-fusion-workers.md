# Cloudflare Request Signal Fusion for Locale Detection in Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Workers handler relies solely on the `Accept-Language` header for locale detection, but that header is missing or set to `*` for bots, headless browsers, and some mobile clients. You want to combine every signal Cloudflare exposes on the `Request` object — IP-derived country, edge timezone, TLS fingerprint region hints, and browser language preferences — into a single ranked locale decision without an external API call.

## Context

Every request that reaches a Cloudflare Worker carries rich geolocation and TLS metadata on the `cf` object (type `IncomingRequestCfProperties`). Combined with standard HTTP headers, these signals cover the vast majority of cases where `Accept-Language` is absent or ambiguous. The goal is a **signal-fusion function** that produces a ranked list of BCP 47 locale candidates, feeds them to locale negotiation, and resolves to the best supported locale — all at zero extra latency.

Available CF signals:
| Signal | Path | Example |
|---|---|---|
| Country (IP geolocation) | `cf.country` | `"JP"` |
| Region | `cf.region` | `"Tokyo"` |
| IANA timezone | `cf.timezone` | `"Asia/Tokyo"` |
| Continent | `cf.continent` | `"AS"` |
| Accept-Language | `headers.get("accept-language")` | `"ja,en-US;q=0.9"` |
| `Sec-CH-Lang` (Chrome hint) | `headers.get("sec-ch-lang")` | `"\"ja\", \"en\""` |

---

## Parsing Accept-Language with Quality Values

```typescript
interface LangCandidate {
  tag: string;
  q: number;
}

function parseAcceptLanguage(header: string | null): LangCandidate[] {
  if (!header || header === "*") return [];
  return header
    .split(",")
    .map((part) => {
      const [tag, qPart] = part.trim().split(";q=");
      return { tag: tag.trim(), q: qPart ? parseFloat(qPart) : 1.0 };
    })
    .filter((c) => c.tag && !isNaN(c.q))
    .sort((a, b) => b.q - a.q);
}
```

---

## Country-to-Likely-Locale Mapping

```typescript
// Minimal CLDR-derived map of ISO 3166-1 alpha-2 → primary BCP 47 tag.
// Full map belongs in KV; this is a small hot-path fallback.
const COUNTRY_LOCALE: Record<string, string> = {
  JP: "ja-JP", CN: "zh-Hans-CN", TW: "zh-Hant-TW", KR: "ko-KR",
  SA: "ar-SA", EG: "ar-EG", AE: "ar-AE",
  DE: "de-DE", FR: "fr-FR", ES: "es-ES", IT: "it-IT",
  BR: "pt-BR", PT: "pt-PT",
  IN: "hi-IN", BD: "bn-BD",
  RU: "ru-RU", UA: "uk-UA",
  US: "en-US", GB: "en-GB", AU: "en-AU", CA: "en-CA",
  MX: "es-MX", AR: "es-AR",
};

function countryToLocale(country: string | null): string | null {
  return country ? (COUNTRY_LOCALE[country.toUpperCase()] ?? null) : null;
}
```

---

## Signal Fusion Function

```typescript
interface LocaleSignals {
  acceptLanguage: string | null;
  secChLang: string | null;
  cfCountry: string | null;
  cfTimezone: string | null;
}

function fusedLocaleCandidates(signals: LocaleSignals): string[] {
  const candidates: string[] = [];

  // 1. Explicit browser preference (highest trust)
  const alCandidates = parseAcceptLanguage(signals.acceptLanguage);
  candidates.push(...alCandidates.map((c) => c.tag));

  // 2. Chrome Client Hint (structured, no quality values)
  if (signals.secChLang) {
    // Sec-CH-Lang format: "\"ja\", \"en\""
    const chLangs = signals.secChLang
      .replace(/"/g, "")
      .split(",")
      .map((s) => s.trim());
    candidates.push(...chLangs);
  }

  // 3. Country-derived locale (medium trust — user may be a traveller)
  const countryLocale = countryToLocale(signals.cfCountry);
  if (countryLocale) candidates.push(countryLocale);

  // 4. Timezone-derived region hint (lowest trust; broad strokes only)
  if (signals.cfTimezone) {
    const [, region] = signals.cfTimezone.split("/");
    // e.g. "Asia/Tokyo" → "Tokyo" — not a locale, but can disambiguate scripts
    // Only add if no country-derived locale was added
    if (!countryLocale && region) {
      // heuristic: use country fallback from timezone continent
      const continent = signals.cfTimezone.split("/")[0];
      if (continent === "Asia" && !candidates.length) candidates.push("en-US");
    }
  }

  // De-duplicate while preserving order
  return [...new Set(candidates)];
}
```

---

## Locale Negotiation Against Supported Locales

```typescript
const SUPPORTED_LOCALES = ["en-US", "en-GB", "fr-FR", "de-DE", "ja-JP",
                           "zh-Hans-CN", "zh-Hant-TW", "ar-SA", "pt-BR",
                           "es-MX", "ko-KR", "ru-RU", "hi-IN"];

function negotiateLocale(candidates: string[], supported: string[]): string {
  const supportedSet = new Set(supported);
  for (const candidate of candidates) {
    // Exact match
    if (supportedSet.has(candidate)) return candidate;
    // Language-only match (en-AU → en-US)
    const lang = candidate.split("-")[0];
    const langMatch = supported.find((s) => s.startsWith(lang + "-"));
    if (langMatch) return langMatch;
  }
  return "en-US"; // ultimate default
}

export async function detectLocale(request: Request): Promise<string> {
  const cf = request.cf as IncomingRequestCfProperties | undefined;
  const signals: LocaleSignals = {
    acceptLanguage: request.headers.get("accept-language"),
    secChLang: request.headers.get("sec-ch-lang"),
    cfCountry: cf?.country ?? null,
    cfTimezone: cf?.timezone ?? null,
  };
  const candidates = fusedLocaleCandidates(signals);
  return negotiateLocale(candidates, SUPPORTED_LOCALES);
}
```

---

## Full Workers Handler Integration

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const locale = await detectLocale(request);

    // Propagate via response header so CDN can vary the cache
    const response = await handleRequest(request, env, locale);
    const headers = new Headers(response.headers);
    headers.set("Content-Language", locale);
    headers.append("Vary", "Accept-Language");
    return new Response(response.body, { status: response.status, headers });
  },
};
```

---

## Anti-patterns

- **Trusting only `cf.country`**: a Japanese tourist in Germany would receive German. `Accept-Language` has higher trust because it reflects explicit browser configuration.
- **Hard-coding country→locale as 1-to-1**: multilingual countries (Switzerland, Belgium, Canada) need a list of locales; always allow `Accept-Language` to override.
- **Using `Intl.Locale.maximize()` on a country code**: `Intl.Locale` accepts BCP 47 language tags, not ISO 3166-1 codes; pass the tag, not the raw country.
- **Skipping `Vary: Accept-Language`**: without it, a CDN cache may serve a German-locale response to a Japanese user on the same edge node.

## Gotchas

- `cf.country` can be `"T1"` (Tor exit) or `"XX"` (unknown); handle these explicitly instead of passing them through the country map.
- `Sec-CH-Lang` requires the server to send `Accept-CH: Sec-CH-Lang` on a prior response; first-visit requests will not carry it.
- `cf.timezone` is `undefined` in `wrangler dev --local`; add a null check before calling `.split("/")`.
- The `request.cf` object is typed as `IncomingRequestCfProperties` in `@cloudflare/workers-types` but is `undefined` in unit-test environments — always default to `{}` in test helpers.

## Verification

```bash
# Simulate a Japanese request in wrangler dev
curl -H "Accept-Language: ja,en;q=0.8" \
     -H "CF-IPCountry: JP" \
     http://localhost:8787/ -v | grep content-language

# Unit test signal fusion
npx vitest run tests/locale-detection-fusion.test.ts

# Confirm Vary header is present on all locale-sensitive routes
wrangler tail | jq 'select(.outcome=="ok") | .response.headers["vary"]'
```

## Related

- `language-detection-workers-accept-language.md`
- `cloudflare-workers-geolocation-locale-routing.md`
- `locale-negotiation-accept-language.md`
- `locale-negotiation-cloudflare-pages-accept-language.md`
- `content-negotiation-vary-header.md`

## Sources

- Cloudflare `cf` object reference: https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
- BCP 47 language negotiation: https://www.rfc-editor.org/rfc/rfc4647
- CLDR likely subtags (country→locale): https://github.com/unicode-org/cldr/blob/main/common/supplemental/likelySubtags.xml
- Client Hints `Sec-CH-Lang`: https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Sec-CH-Lang
