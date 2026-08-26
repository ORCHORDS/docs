# Currency Formatting in Cloudflare Workers with Intl.NumberFormat

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

Currency amounts render correctly on desktop Chrome but show wrong decimal separators on
Android WebView or produce `RangeError: invalid currency code` inside a Cloudflare Worker.
KV-cached formatter objects are undefined on the second request because Workers
serialise only JSON-safe values.

## Context

example project (example.com) is a Next.js static export deployed on Cloudflare Pages with a
Cloudflare Workers API layer that uses D1 and R2. Price data is fetched from the Worker
and rendered client-side. The Worker must emit locale-correct currency strings for SSR
fallbacks and for Open Graph / meta tags. V8 isolates in Workers support `Intl` but
formatter construction is not free — naive per-request instantiation adds ~0.5–2 ms per
call at high throughput. Mobile browsers carry locale quirks that differ from desktop even
on the same OS version.

---

## Intl.NumberFormat Currency Basics at the Edge

Workers run V8 with full ICU data as of the `nodejs_compat` flag. Currency formatting
follows the same API as the browser, but the *available locale data* subset shipped in
the isolate may differ from Node LTS.

```typescript
// workers/src/currency.ts
export function formatCurrency(
  amount: number,
  currency: string,
  locale: string
): string {
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency,                  // ISO 4217: "USD", "EUR", "SAR"
    currencyDisplay: "symbol", // "narrowSymbol" collapses US$ → $
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount);
}
```

| locale   | currency | output (Workers V8) |
|----------|----------|---------------------|
| en-US    | USD      | $1,234.56           |
| de-DE    | EUR      | 1.234,56 €          |
| ar-SA    | SAR      | ١٢٣٤٫٥٦ ر.س.       |
| fr-FR    | EUR      | 1 234,56 €          |
| hi-IN    | INR      | ₹1,234.56           |

Always validate the currency code before passing it to `Intl.NumberFormat`; an invalid
code throws synchronously and crashes the request handler.

```typescript
const ISO_4217_RE = /^[A-Z]{3}$/;

export function safeCurrency(code: unknown): string {
  if (typeof code !== "string" || !ISO_4217_RE.test(code)) {
    throw new RangeError(`Invalid currency code: ${code}`);
  }
  return code;
}
```

---

## Mobile Decimal-Locale Differences

Android system locale and browser locale can diverge. A device set to `en-US` system
locale but browsing with a manually chosen `de-DE` browser locale sends
`Accept-Language: de-DE,de;q=0.9,en-US;q=0.8`. The Worker must honour the
*first strong match*, not the OS default.

| Platform             | Locale sent          | Decimal sep | Thousands sep |
|----------------------|----------------------|-------------|---------------|
| Android Chrome 124   | de-DE                | ,           | .             |
| iOS Safari 17        | fr-FR                | ,           | espace fine   |
| Samsung Internet 24  | ko-KR                | .           | ,             |
| Android WebView      | en-US (system only)  | .           | ,             |

Samsung Internet 24 and older Android WebView sometimes send a bare language tag
(`ko` instead of `ko-KR`). Apply `Intl.getCanonicalLocales` + likely-subtag expansion
before constructing the formatter:

```typescript
import { maximize } from "@formatjs/intl-localematcher"; // pure JS, edge-safe

export function resolveLocale(raw: string): string {
  try {
    const [canonical] = Intl.getCanonicalLocales(raw);
    return maximize(canonical); // "ko" → "ko-Hang-KR"
  } catch {
    return "en-US";
  }
}
```

---

## KV-Cached Formatter Instances

`Intl.NumberFormat` objects are not serialisable (they contain internal slots). Storing
them in KV or the global `caches` API loses the instance. The correct caching strategy is
to cache the *construction parameters* and hold live instances in a Worker-level
module-scope `Map` that persists across requests within the same isolate.

```typescript
// Isolate-scoped cache — survives multiple requests in the same V8 instance.
const formatterCache = new Map<string, Intl.NumberFormat>();

export function getCurrencyFormatter(
  locale: string,
  currency: string
): Intl.NumberFormat {
  const key = `${locale}::${currency}`;
  if (!formatterCache.has(key)) {
    formatterCache.set(
      key,
      new Intl.NumberFormat(locale, {
        style: "currency",
        currency,
        currencyDisplay: "narrowSymbol",
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })
    );
  }
  return formatterCache.get(key)!;
}
```

KV is appropriate for *display rules* (which locale maps to which currency code) rather
than for formatter objects.

```typescript
// Store locale→currency mapping in KV
const mapping = await env.I18N_KV.get<Record<string, string>>(
  "locale-currency-map",
  "json"
);
const currency = mapping?.[locale] ?? "USD";
const fmt = getCurrencyFormatter(locale, currency);
```

---

## Cloudflare Pages Static Export Integration

Next.js static export cannot run server-side `Intl` on Pages. Formatted currency must
come from one of two sources:

1. **Worker API response** — the Worker formats the value and returns a string field.
2. **Client hydration** — the browser runs `Intl.NumberFormat` after JS loads.

Prefer option 1 for Open Graph tags and the initial HTML shell; prefer option 2 for
dynamic user-facing UI to avoid a round trip.

```typescript
// app/api/price/route.ts  (Worker via next-on-pages adapter)
export const runtime = "edge";

export async function GET(req: Request): Promise<Response> {
  const locale = req.headers.get("Accept-Language")?.split(",")[0] ?? "en-US";
  const currency = req.headers.get("X-Currency") ?? "USD";
  const amount = 4999; // cents
  const formatted = getCurrencyFormatter(locale, safeCurrency(currency)).format(
    amount / 100
  );
  return Response.json({ formatted, raw: amount, currency });
}
```

---

## Anti-patterns

- Constructing `new Intl.NumberFormat()` inside every request handler — adds latency and
  causes GC pressure in the isolate.
- Storing formatter instances in KV — they are not JSON-serialisable and silently become
  `null` on retrieval.
- Using `currencyDisplay: "code"` in UI strings — produces "USD 1,234.56" which confuses
  users expecting a symbol.
- Accepting raw user-supplied currency strings from query parameters without validation —
  allows RangeError crashes or information leakage via error messages.
- Assuming system locale equals browser locale on mobile — detect from `Accept-Language`,
  not from `CF-IPCountry`.

---

## Gotchas

- `narrowSymbol` falls back to `symbol` silently for locales without a narrow variant;
  always test with `ar-SA`, `hi-IN`, and `ko-KR`.
- Workers ICU data may lag behind browser ICU by one Unicode release; minor rounding
  or symbol differences can appear for exotic locales.
- `CF-IPCountry` gives a *country*, not a *currency* or *locale* — the mapping is
  many-to-one and must be maintained separately in KV.
- iOS Safari 17 uses a narrow no-break space (U+202F) as the French thousands separator;
  ensure downstream systems handle it if the formatted string is stored.
- `maximumSignificantDigits` and `maximumFractionDigits` cannot both be set in the same
  options object — pick one strategy.

---

## Verification

```bash
# Run a local Miniflare dev session and curl the price endpoint
npx wrangler dev --local

curl -H "Accept-Language: de-DE" \
     -H "X-Currency: EUR" \
     http://localhost:8787/api/price
# Expected: {"formatted":"4.999,00 €","raw":499900,"currency":"EUR"}

# Confirm KV formatter cache does not grow unboundedly
# (module-scope Map resets only on isolate recycle, not per request)
```

```typescript
// Unit test with vitest
import { describe, it, expect } from "vitest";
import { formatCurrency } from "../src/currency";

describe("formatCurrency", () => {
  it("formats EUR for de-DE", () => {
    expect(formatCurrency(1234.56, "EUR", "de-DE")).toBe("1.234,56 €");
  });
  it("throws on invalid currency code", () => {
    expect(() => formatCurrency(1, "XX", "en-US")).toThrow(RangeError);
  });
});
```

---

## Related

- `intl-api-workers-edge-formatting.md`
- `locale-aware-number-currency-formatting.md`
- `number-currency-formatting-2026.md`
- `locale-negotiation-accept-language.md`
- `cloudflare-workers-geolocation-locale-routing.md`

---

## Sources

- MDN Web Docs — Intl.NumberFormat: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat
- Cloudflare Workers Runtime APIs — Intl: https://developers.cloudflare.com/workers/runtime-apis/web-standards/#javascript-standards
- ISO 4217 Currency Codes: https://www.iso.org/iso-4217-currency-codes.html
- CLDR Currency Data: https://cldr.unicode.org/index/downloads
- Cloudflare Workers KV documentation: https://developers.cloudflare.com/kv/
