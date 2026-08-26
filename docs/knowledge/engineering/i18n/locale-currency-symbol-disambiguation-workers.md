# Locale Currency Symbol Disambiguation in Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A user in Australia sees "$12.00" and assumes US dollars. The symbol `$` alone maps to at least eight distinct currencies (USD, CAD, AUD, NZD, SGD, HKD, MXN, CLP). Displaying a bare symbol without context causes mis-reading of pricing, failed payments, and support tickets.

## Context

`Intl.NumberFormat` exposes three `currencyDisplay` modes:

| Mode         | USD in en-US  | USD in en-AU  | AUD in en-AU  |
|--------------|---------------|---------------|---------------|
| `symbol`     | $1.00         | US$1.00       | $1.00         |
| `narrowSymbol`| $1.00        | $1.00         | $1.00         |
| `code`       | USD 1.00      | USD 1.00      | AUD 1.00      |
| `name`       | 1.00 US dollar| 1.00 US dollars| 1.00 Australian dollar |

`narrowSymbol` is the most compact form but the most ambiguous.

---

## Detecting Symbol Ambiguity

```typescript
// currency/ambiguity.ts
export function isAmbiguous(currency: string, locale: string): boolean {
  const narrow = new Intl.NumberFormat(locale, {
    style: "currency", currency, currencyDisplay: "narrowSymbol",
  }).format(1);

  const standard = new Intl.NumberFormat(locale, {
    style: "currency", currency, currencyDisplay: "symbol",
  }).format(1);

  return narrow !== standard;
}
// isAmbiguous("USD", "en-AU") → true
// isAmbiguous("AUD", "en-AU") → false
```

---

## Choosing the Right Display Mode

```typescript
type CurrencyDisplay = "symbol" | "narrowSymbol" | "code" | "name";

export function chooseCurrencyDisplay(
  currency: string,
  locale: string,
  prefer: "compact" | "unambiguous" = "unambiguous"
): CurrencyDisplay {
  if (prefer === "compact") return "narrowSymbol";

  const homeCurrency = getLocaleCurrency(locale);
  if (homeCurrency === currency) return "narrowSymbol";
  if (isAmbiguous(currency, locale)) return "code";
  return "symbol";
}
```

---

## Mapping Locale to Home Currency

```typescript
export function getLocaleCurrency(locale: string): string {
  const TABLE: Record<string, string> = {
    "en-US": "USD", "en-GB": "GBP", "en-AU": "AUD", "en-CA": "CAD",
    "en-NZ": "NZD", "en-SG": "SGD", "en-HK": "HKD", "zh-HK": "HKD",
    "de": "EUR", "fr": "EUR", "es": "EUR", "it": "EUR", "pt-PT": "EUR",
    "pt-BR": "BRL", "ja": "JPY", "ko": "KRW", "zh": "CNY",
  };
  return TABLE[locale] ?? TABLE[locale.split("-")[0]] ?? "USD";
}
```

---

## Worker Request Handler

```typescript
export function formatPrice(req: { amount: number; currency: string; locale: string }): string {
  const display = chooseCurrencyDisplay(req.currency, req.locale);
  return new Intl.NumberFormat(req.locale, {
    style: "currency",
    currency: req.currency,
    currencyDisplay: display,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(req.amount);
}

export default {
  async fetch(req: Request): Promise<Response> {
    const { amount, currency, locale } = await req.json<{ amount: number; currency: string; locale: string }>();
    if (!amount || !currency.match(/^[A-Z]{3}$/) || !locale) {
      return new Response("Bad request", { status: 400 });
    }
    return Response.json({ formatted: formatPrice({ amount, currency, locale }) });
  },
};
```

---

## Anti-patterns

- **Hardcoding `currencyDisplay: "narrowSymbol"` globally** — ambiguous for foreign currencies.
- **Using a static symbol lookup table** — misses locale context.
- **Displaying ISO code everywhere** — reads awkwardly in running English text.

## Gotchas

- `Intl.NumberFormat` with `narrowSymbol` throws in some older V8 versions; add try/catch and fall back to `symbol`.
- The same ISO code can have different narrow symbols per locale.

## Verification

```bash
curl -X POST https://your-worker.example.com/price \
  -H "Content-Type: application/json" \
  -d '{"amount":12.50,"currency":"USD","locale":"en-AU"}' | jq .formatted
# Expected: "US$12.50"
```

## Related

- `currency-formatting-cloudflare-workers-intl-numberformat.md`
- `locale-aware-invoice-receipt-generation-d1-workers.md`

## Sources

- MDN Intl.NumberFormat currencyDisplay — https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat/NumberFormat#currencydisplay
- CLDR currency data — https://github.com/unicode-org/cldr
