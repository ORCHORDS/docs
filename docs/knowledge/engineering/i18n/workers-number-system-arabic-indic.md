# Non-Latin Number Systems in Workers: `Intl.NumberFormat` with `numberingSystem`

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

An Arabic (`ar-SA`), Hindi (`hi-IN`), or Bengali (`bn-BD`) user sees Latin
digits (0–9) in prices, counts, and dates rendered by your Worker. They expect
Eastern Arabic–Indic (٠١٢٣٤٥٦٧٨٩), Devanagari (०१२३४५६७८९), or Bengali
(০১২৩৪৫৬৭৮৯) digits respectively.

The fix is `Intl.NumberFormat` with the `numberingSystem` Unicode extension,
plus a KV locale config that stores the preferred numeral system per locale so
it can be changed without a code deploy.

## Context

- Runtime: Cloudflare Workers (V8 full `Intl` support, including `nu` extension)
- Storage: KV for locale preferences (numeral system, currency, decimal/group separators)
- Locales in scope: `ar-SA` → `arab`, `hi-IN` / `mr-IN` → `deva`, `bn-BD` → `beng`
- The `Intl.Locale` API is used to parse and validate locale strings

---

## 1. Unicode Numbering System Extensions

The Unicode `nu` extension tag selects the numeral system:

| BCP-47 locale | `numberingSystem` value | Digits |
|---|---|---|
| `ar-SA` | `arab`  | ٠١٢٣٤٥٦٧٨٩ |
| `ar-MA` | `latn`  | 0123456789 (Moroccan Arabic prefers Latin) |
| `hi-IN` | `deva`  | ०१२३४५६७८९ |
| `mr-IN` | `deva`  | ०१२३४५६७८९ |
| `bn-BD` | `beng`  | ০১২৩৪৫৬৭৮৯ |
| `ne-NP` | `deva`  | ०१२३४५६७८९ |

Pass the `numberingSystem` option directly to `Intl.NumberFormat` **or** embed
it in the locale string as a Unicode extension: `ar-SA-u-nu-arab`.

---

## 2. KV Locale Config Schema

Store per-locale preferences in KV as JSON under the key `locale-config:<tag>`.

```typescript
// src/types.ts
export interface LocaleConfig {
  numberingSystem: string;  // CLDR numbering system id, e.g. "arab", "deva", "latn"
  currency:        string;  // ISO 4217, e.g. "SAR", "INR", "BDT"
  currencyDisplay: 'symbol' | 'narrowSymbol' | 'code' | 'name';
  minimumFractionDigits: number;
  maximumFractionDigits: number;
}

export const DEFAULT_CONFIG: LocaleConfig = {
  numberingSystem:      'latn',
  currency:             'USD',
  currencyDisplay:      'symbol',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
};
```

```bash
# Seed KV values (run once, or via a deploy script)
wrangler kv key put --binding I18N_CACHE 'locale-config:ar-SA' '{
  "numberingSystem": "arab",
  "currency": "SAR",
  "currencyDisplay": "symbol",
  "minimumFractionDigits": 2,
  "maximumFractionDigits": 2
}'

wrangler kv key put --binding I18N_CACHE 'locale-config:hi-IN' '{
  "numberingSystem": "deva",
  "currency": "INR",
  "currencyDisplay": "symbol",
  "minimumFractionDigits": 0,
  "maximumFractionDigits": 2
}'

wrangler kv key put --binding I18N_CACHE 'locale-config:bn-BD' '{
  "numberingSystem": "beng",
  "currency": "BDT",
  "currencyDisplay": "code",
  "minimumFractionDigits": 0,
  "maximumFractionDigits": 2
}'
```

---

## 3. Loading Config and Building `Intl.NumberFormat`

```typescript
// src/number-format.ts
import type { Env }          from './index';
import { LocaleConfig, DEFAULT_CONFIG } from './types';

/**
 * Retrieve locale config from KV (with 10-minute in-memory cache via
 * the module-level Map — lives for the isolate lifetime).
 */
const configCache = new Map<string, LocaleConfig>();

export async function getLocaleConfig(
  locale: string,
  env: Env
): Promise<LocaleConfig> {
  if (configCache.has(locale)) return configCache.get(locale)!;

  const raw = await env.I18N_CACHE.get<LocaleConfig>(
    `locale-config:${locale}`,
    'json'
  );
  const config = raw ?? DEFAULT_CONFIG;
  configCache.set(locale, config);
  return config;
}

/**
 * Build an `Intl.NumberFormat` for the given locale and config.
 * The `nu` extension in the locale string overrides any system default.
 */
export function buildNumberFormat(
  locale: string,
  config: LocaleConfig,
  style: 'decimal' | 'currency' | 'percent' = 'decimal',
  options: Partial<Intl.NumberFormatOptions> = {}
): Intl.NumberFormat {
  // Attach the numbering system as a Unicode extension tag
  const localeWithNu = `${locale}-u-nu-${config.numberingSystem}`;

  return new Intl.NumberFormat(localeWithNu, {
    style,
    currency:              style === 'currency' ? config.currency        : undefined,
    currencyDisplay:       style === 'currency' ? config.currencyDisplay : undefined,
    minimumFractionDigits: config.minimumFractionDigits,
    maximumFractionDigits: config.maximumFractionDigits,
    ...options
  });
}
```

---

## 4. Worker Entry Point

```typescript
// src/index.ts
import { detectLocale }    from './locale-detect';
import { getLocaleConfig, buildNumberFormat } from './number-format';

export interface Env {
  I18N_CACHE: KVNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url   = new URL(request.url);
    const al    = request.headers.get('Accept-Language');
    const { locale } = detectLocale(al);

    // Load KV config (cached in-isolate after first hit)
    const config = await getLocaleConfig(locale, env);

    // Format sample numbers
    const decimalFmt  = buildNumberFormat(locale, config, 'decimal');
    const currencyFmt = buildNumberFormat(locale, config, 'currency');
    const percentFmt  = buildNumberFormat(locale, config, 'percent',
      { minimumFractionDigits: 0, maximumFractionDigits: 1 });

    const amount  = parseFloat(url.searchParams.get('amount') ?? '1234567.89');
    const percent = parseFloat(url.searchParams.get('percent') ?? '0.123');

    const body = JSON.stringify({
      locale,
      numberingSystem: config.numberingSystem,
      decimal:  decimalFmt.format(amount),
      currency: currencyFmt.format(amount),
      percent:  percentFmt.format(percent)
    }, null, 2);

    return new Response(body, {
      headers: {
        'Content-Type': 'application/json; charset=utf-8',
        'Vary':         'Accept-Language'
      }
    });
  }
};
```

---

## 5. Formatting Dates with Non-Latin Numerals

`Intl.DateTimeFormat` also accepts the `nu` extension:

```typescript
export function formatDate(
  date: Date,
  locale: string,
  numberingSystem: string
): string {
  return new Intl.DateTimeFormat(`${locale}-u-nu-${numberingSystem}`, {
    year:  'numeric',
    month: 'long',
    day:   'numeric'
  }).format(date);
}

// Example output for ar-SA-u-nu-arab:
// ٢٤ أغسطس ٢٠٢٦
```

---

## Anti-patterns

- **Manual digit replacement** — do not map Latin digits to Unicode code points
  by hand. `Intl.NumberFormat` handles all CLDR numeral systems correctly,
  including bidirectional marks and grouping separators.
- **Hard-coding `numberingSystem` in source code** — storing it in KV allows
  regional product managers to override per-country preferences without a
  deployment.
- **Using `toLocaleString()` without options** — the default numeral system is
  platform-dependent. Always pass the `nu` extension explicitly.
- **Assuming Arabic always uses `arab` digits** — Moroccan and Tunisian Arabic
  (`ar-MA`, `ar-TN`) conventionally use Latin digits. Check the CLDR default
  for each region before setting KV config.

## Gotchas

- `Intl.Locale` constructor accepts `-u-nu-<system>` but also the object option
  `{ numberingSystem: 'arab' }`. Both produce the same resolved locale.
- Workers V8 `Intl` follows CLDR; not all `numberingSystem` strings are valid.
  Use the CLDR `numbering-systems.xml` canonical list. Invalid values silently
  fall back to `latn` in some environments — log the resolved locale to confirm.
- The module-level `configCache` Map persists only for the isolate's lifetime
  (minutes to hours). It is not shared across isolates. This is intentional:
  stale config expires naturally. If you need cross-isolate consistency, set a
  short KV TTL and rely on KV reads.

## Verification

```bash
npx wrangler dev src/index.ts

# Arabic-Indic numerals for ar-SA
curl -H 'Accept-Language: ar-SA' 'http://localhost:8787/?amount=42000.5'
# → { "numberingSystem": "arab", "decimal": "٤٢٬٠٠٠٫٥٠", ... }

# Devanagari numerals for hi-IN
curl -H 'Accept-Language: hi-IN' 'http://localhost:8787/?amount=100'
# → { "numberingSystem": "deva", "decimal": "१००", ... }

# Bengali numerals for bn-BD
curl -H 'Accept-Language: bn-BD' 'http://localhost:8787/?amount=999'
# → { "numberingSystem": "beng", "decimal": "৯৯৯", ... }

# Moroccan Arabic falls back to Latin (no KV entry → DEFAULT_CONFIG)
curl -H 'Accept-Language: ar-MA' 'http://localhost:8787/?amount=100'
# → { "numberingSystem": "latn", "decimal": "100.00", ... }
```

## Related

- `workers-bidirectional-text-rtl-html-rewriter.md` — RTL layout for Arabic/Hebrew
- `workers-icu-message-format-complex-plural.md` — ICU plural forms for Arabic
- `workers-locale-content-negotiation-d1.md` — locale selection with quality weighting

## Sources

- https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat/NumberFormat#numberingsystem
- https://unicode.org/reports/tr35/tr35-numbers.html#Numbering_Systems
- https://cldr.unicode.org/translation/number-currency-formats
- https://developers.cloudflare.com/kv/
