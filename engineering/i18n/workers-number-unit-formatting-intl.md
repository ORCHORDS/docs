# Number and Unit Formatting with Intl.NumberFormat Unit Style in Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Your product pages display distances, temperatures, and weights in a single unit system — kilometres and Celsius — regardless of the visitor's locale. US users see `42.5 km` instead of `26.4 mi`, and UK users expect stone for body weight. Beyond unit switching, the decimal and grouping separators differ by country: `1,234.56` in the US, `1.234,56` in Germany, `1 234,56` in France. Hardcoded format strings break all of these simultaneously.

---

## Context

`Intl.NumberFormat` in modern runtimes (including Cloudflare Workers' V8 isolate) supports a `style: "unit"` option that produces localised unit strings conforming to CLDR's measurement data. The same API controls grouping separators and decimal symbols through `useGrouping` and the locale tag itself — no lookup tables required.

Measurement system (metric vs US customary vs UK imperial) is not directly encoded in BCP 47 locale tags, but can be inferred: `en-US` is US customary, `en-GB` is largely metric for distance/temperature but imperial for some everyday measures. The `-u-ms-` unicode extension (`metric` / `ussystem` / `uksystem`) can be set explicitly when the measurement system is known independently of language.

Key constraints:
- `Intl.NumberFormat` with `style: "unit"` requires a unit identifier from the [CLDR unit list](https://tc39.es/ecma402/#table-sanctioned-single-unit-identifiers): `kilometer`, `mile`, `celsius`, `fahrenheit`, `kilogram`, `pound`, `meter-per-second`, `mile-per-hour`, `kilobyte`, `megabyte`, etc.
- Compound units like `kilometer-per-hour` are supported.
- `unitDisplay` can be `"long"` (`42 kilometres`), `"short"` (`42 km`), or `"narrow"` (`42km` — no space in some locales).

---

## Solution

### 1. Measurement system detection from locale

```typescript
// src/measurement-system.ts

export type MeasurementSystem = "metric" | "ussystem" | "uksystem";

const US_REGIONS = new Set(["US", "LR", "MM"]); // only three countries use US customary
const UK_REGIONS = new Set(["GB"]);

export function getMeasurementSystem(locale: string): MeasurementSystem {
  // Check for explicit unicode extension: en-US-u-ms-ussystem
  const msMatch = locale.match(/-u-(?:[a-z0-9]+-)*ms-([a-z]+)/);
  if (msMatch) {
    const ms = msMatch[1];
    if (ms === "ussystem") return "ussystem";
    if (ms === "uksystem") return "uksystem";
    if (ms === "metric") return "metric";
  }

  // Infer from region subtag
  const region = locale.split("-")[1]?.toUpperCase();
  if (region && US_REGIONS.has(region)) return "ussystem";
  if (region && UK_REGIONS.has(region)) return "uksystem";
  return "metric";
}
```

### 2. Distance formatting (km vs miles)

```typescript
// src/units/distance.ts
import { getMeasurementSystem } from "../measurement-system";

interface FormatDistanceOpts {
  locale: string;
  displayUnit?: "long" | "short" | "narrow";
}

/**
 * Accepts value in kilometres; converts and formats for locale.
 */
export function formatDistance(
  km: number,
  opts: FormatDistanceOpts
): string {
  const system = getMeasurementSystem(opts.locale);
  let value: number;
  let unit: string;

  switch (system) {
    case "ussystem":
      value = km * 0.621_371;
      unit = "mile";
      break;
    case "uksystem":
      // UK uses miles on roads
      value = km * 0.621_371;
      unit = "mile";
      break;
    default:
      value = km;
      unit = "kilometer";
  }

  return new Intl.NumberFormat(opts.locale, {
    style: "unit",
    unit,
    unitDisplay: opts.displayUnit ?? "short",
    maximumFractionDigits: 1,
  }).format(value);
}

// formatDistance(42.195, { locale: "en-US" })  => "26.2 mi"
// formatDistance(42.195, { locale: "de-DE" })  => "42,2 km"
// formatDistance(42.195, { locale: "fr-FR" })  => "42,2 km"
// formatDistance(42.195, { locale: "zh-CN" })  => "42.2千米"  (narrow display varies)
```

### 3. Temperature formatting (°C vs °F)

```typescript
// src/units/temperature.ts
import { getMeasurementSystem } from "../measurement-system";

/**
 * Accepts Celsius; converts to °F for US/Belize/Cayman.
 */
export function formatTemperature(
  celsius: number,
  locale: string,
  displayUnit: "long" | "short" | "narrow" = "short"
): string {
  const system = getMeasurementSystem(locale);
  let value: number;
  let unit: string;

  if (system === "ussystem") {
    value = (celsius * 9) / 5 + 32;
    unit = "fahrenheit";
  } else {
    value = celsius;
    unit = "celsius";
  }

  return new Intl.NumberFormat(locale, {
    style: "unit",
    unit,
    unitDisplay: displayUnit,
    maximumFractionDigits: 1,
  }).format(value);
}

// formatTemperature(22, "en-US")  => "71.6°F"
// formatTemperature(22, "de-DE")  => "22°C"
// formatTemperature(22, "fr-FR")  => "22°C"
// formatTemperature(22, "en-US", "long")  => "71.6 degrees Fahrenheit"
```

### 4. Weight formatting (kg vs lbs vs stone)

```typescript
// src/units/weight.ts
import { getMeasurementSystem } from "../measurement-system";

export function formatWeight(
  kg: number,
  locale: string,
  displayUnit: "long" | "short" | "narrow" = "short"
): string {
  const system = getMeasurementSystem(locale);

  if (system === "ussystem") {
    const lbs = kg * 2.204_62;
    return new Intl.NumberFormat(locale, {
      style: "unit",
      unit: "pound",
      unitDisplay: displayUnit,
      maximumFractionDigits: 1,
    }).format(lbs);
  }

  if (system === "uksystem") {
    // UK colloquially uses stone+pounds for body weight, kg for products
    // For product weight, use kg
    return new Intl.NumberFormat(locale, {
      style: "unit",
      unit: "kilogram",
      unitDisplay: displayUnit,
      maximumFractionDigits: 2,
    }).format(kg);
  }

  return new Intl.NumberFormat(locale, {
    style: "unit",
    unit: "kilogram",
    unitDisplay: displayUnit,
    maximumFractionDigits: 2,
  }).format(kg);
}

// formatWeight(75, "en-US")  => "165.3 lb"
// formatWeight(75, "de-DE")  => "75 kg"
// formatWeight(75, "en-GB")  => "75 kg"
```

### 5. Byte size formatting

```typescript
// src/units/bytes.ts

const BYTE_UNITS: Array<{ unit: string; threshold: number }> = [
  { unit: "terabyte", threshold: 1e12 },
  { unit: "gigabyte", threshold: 1e9 },
  { unit: "megabyte", threshold: 1e6 },
  { unit: "kilobyte", threshold: 1e3 },
  { unit: "byte",     threshold: 0 },
];

export function formatBytes(
  bytes: number,
  locale: string,
  displayUnit: "long" | "short" | "narrow" = "short"
): string {
  const { unit, threshold } = BYTE_UNITS.find(b => bytes >= b.threshold)
    ?? BYTE_UNITS[BYTE_UNITS.length - 1];

  const value = threshold > 0 ? bytes / threshold : bytes;

  return new Intl.NumberFormat(locale, {
    style: "unit",
    unit,
    unitDisplay: displayUnit,
    maximumFractionDigits: 1,
  }).format(value);
}

// formatBytes(1_500_000, "en-US")   => "1.5 MB"
// formatBytes(1_500_000, "de-DE")   => "1,5 MB"
// formatBytes(1_500_000, "ar-EG")   => "١٫٥ ميغابايت"  (if Arabic numerals)
```

### 6. Locale-specific grouping separators

```typescript
// src/number-format.ts

export interface NumberFormatOpts {
  locale: string;
  style?: "decimal" | "percent" | "currency";
  currency?: string;       // ISO 4217, required when style=currency
  minimumFractionDigits?: number;
  maximumFractionDigits?: number;
  useGrouping?: boolean;
}

export function formatNumber(value: number, opts: NumberFormatOpts): string {
  return new Intl.NumberFormat(opts.locale, {
    style: opts.style ?? "decimal",
    currency: opts.currency,
    minimumFractionDigits: opts.minimumFractionDigits,
    maximumFractionDigits: opts.maximumFractionDigits ?? 2,
    useGrouping: opts.useGrouping ?? true,
  }).format(value);
}

// Grouping separator examples for 1,234,567.89:
// en-US  => "1,234,567.89"    (comma grouping, period decimal)
// de-DE  => "1.234.567,89"    (period grouping, comma decimal)
// fr-FR  => "1 234 567,89"    (narrow-space grouping, comma decimal)
// hi-IN  => "12,34,567.89"    (lakh grouping)
// ar-EG  => "١٬٢٣٤٬٥٦٧٫٨٩"  (Arabic-Indic digits)
// ch-CH  => "1'234'567.89"    (apostrophe grouping — Swiss)
```

### 7. Speed formatting

```typescript
// src/units/speed.ts
import { getMeasurementSystem } from "../measurement-system";

/**
 * Accepts m/s (SI); converts and formats for locale.
 */
export function formatSpeed(
  metersPerSecond: number,
  locale: string,
  displayUnit: "long" | "short" | "narrow" = "short"
): string {
  const system = getMeasurementSystem(locale);

  if (system === "ussystem") {
    const mph = metersPerSecond * 2.236_94;
    return new Intl.NumberFormat(locale, {
      style: "unit",
      unit: "mile-per-hour",
      unitDisplay: displayUnit,
      maximumFractionDigits: 0,
    }).format(mph);
  }

  const kph = metersPerSecond * 3.6;
  return new Intl.NumberFormat(locale, {
    style: "unit",
    unit: "kilometer-per-hour",
    unitDisplay: displayUnit,
    maximumFractionDigits: 0,
  }).format(kph);
}

// formatSpeed(27.78, "en-US")  => "62 mph"
// formatSpeed(27.78, "de-DE")  => "100 km/h"
// formatSpeed(27.78, "fr-FR")  => "100 km/h"
```

### 8. Worker entry point — /api/format/units

```typescript
// src/index.ts
import { formatDistance } from "./units/distance";
import { formatTemperature } from "./units/temperature";
import { formatWeight } from "./units/weight";
import { formatBytes } from "./units/bytes";
import { formatSpeed } from "./units/speed";
import { formatNumber } from "./number-format";
import { resolveLocale } from "./locale-resolver";

export default {
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname !== "/api/format/units") {
      return new Response("Not Found", { status: 404 });
    }

    const locale = resolveLocale(request);
    const raw = {
      distance_km: parseFloat(url.searchParams.get("km") ?? "100"),
      temp_c:      parseFloat(url.searchParams.get("c")  ?? "20"),
      weight_kg:   parseFloat(url.searchParams.get("kg") ?? "70"),
      bytes:       parseFloat(url.searchParams.get("bytes") ?? "1500000"),
      speed_ms:    parseFloat(url.searchParams.get("ms") ?? "13.89"),
      number:      parseFloat(url.searchParams.get("n")  ?? "1234567.89"),
    };

    const result = {
      distance:    formatDistance(raw.distance_km, { locale }),
      temperature: formatTemperature(raw.temp_c, locale),
      weight:      formatWeight(raw.weight_kg, locale),
      bytes:       formatBytes(raw.bytes, locale),
      speed:       formatSpeed(raw.speed_ms, locale),
      number:      formatNumber(raw.number, { locale }),
      locale,
    };

    return new Response(JSON.stringify(result, null, 2), {
      headers: { "Content-Type": "application/json" },
    });
  },
};
```

---

## Implementation Details

- **CLDR unit identifiers**: The full sanctioned list is at https://tc39.es/ecma402/#table-sanctioned-single-unit-identifiers — not all intuitive names work. Use `kilometer` not `km`, `kilogram` not `kg`.
- **Compound units**: `kilometer-per-hour`, `mile-per-hour`, `liter-per-kilometer`, and `mile-per-gallon` are all valid compound identifiers.
- **Lakh grouping**: `hi-IN` and `bn-IN` use the Indian numbering system (2-2-3 grouping) automatically when `useGrouping: true`.
- **Arabic-Indic digits**: `ar-EG`, `ar-SA` and similar locales use ٠١٢٣٤٥٦٧٨٩ by default. Force Latin digits with `-u-nu-latn`: `ar-EG-u-nu-latn`.
- **Swiss apostrophe separator**: `de-CH` uses `'` as the grouping separator. This is a real CLDR data point, not an artifact.

---

## Anti-patterns

- **Hardcoding `km` → `mi` conversion with `toFixed(1)` and string concatenation.** This produces wrong grouping separators for non-US locales.
- **Using `Intl.NumberFormat` without `style: "unit"` and manually appending a unit label.** The label will be in the wrong language and in the wrong position (some locales put unit before value).
- **Assuming `en-GB` is identical to `en-US`** for measurement systems. UK uses metric for distance in most modern contexts but miles on road signs.
- **Not passing `maximumFractionDigits`** for unit conversions. `mile` output from exact km values often produces 8+ decimal places without this guard.
- **Storing pre-formatted strings in the database.** Always store canonical SI units; format at response time.

---

## Gotchas

- **`style: "unit"` requires `unit` to be set** — passing `style: "unit"` without `unit` throws `TypeError`.
- **`unitDisplay: "narrow"` removes the space** between number and unit in many locales: `42km` instead of `42 km`. Ensure your UI has room for either form or use `"short"` for safety.
- **Persian/Farsi numerals**: `fa-IR` uses extended Arabic numerals (٠–٩ with different code points than Arabic). Add `-u-nu-latn` if your UI font doesn't support them.
- **`byte` vs `kilobyte`**: Intl.NumberFormat uses SI (decimal) kilobytes (1 kB = 1000 B), not IEC binary kibibytes (1 KiB = 1024 B). Document this to users if precision matters.
- **Compound unit ordering**: `gallon-per-mile` and `mile-per-gallon` are distinct identifiers and produce different units. Verify against the TC39 table, not intuition.

---

## Verification

```typescript
// tests/units.test.ts
import { describe, it, expect } from "vitest";
import { formatDistance } from "../src/units/distance";
import { formatTemperature } from "../src/units/temperature";
import { formatWeight } from "../src/units/weight";
import { formatBytes } from "../src/units/bytes";

describe("formatDistance", () => {
  it("converts km to miles for en-US", () => {
    const result = formatDistance(100, { locale: "en-US" });
    expect(result).toBe("62.1 mi");
  });

  it("keeps km for de-DE with comma decimal", () => {
    const result = formatDistance(100, { locale: "de-DE" });
    expect(result).toBe("100 km");
  });
});

describe("formatTemperature", () => {
  it("converts 0°C to 32°F for en-US", () => {
    expect(formatTemperature(0, "en-US")).toBe("32°F");
  });

  it("keeps Celsius for fr-FR", () => {
    expect(formatTemperature(22, "fr-FR")).toBe("22°C");
  });
});

describe("formatBytes", () => {
  it("formats 1.5 MB in en-US", () => {
    expect(formatBytes(1_500_000, "en-US")).toBe("1.5 MB");
  });

  it("formats with comma decimal in de-DE", () => {
    expect(formatBytes(1_500_000, "de-DE")).toBe("1,5 MB");
  });
});
```

```bash
npx wrangler deploy
curl "https://your-worker.workers.dev/api/format/units?km=42.195&c=22&kg=70" \
  -H "Accept-Language: en-US,en;q=0.9"
# {"distance":"26.2 mi","temperature":"71.6°F","weight":"154.3 lb",...}

curl "https://your-worker.workers.dev/api/format/units?km=42.195&c=22&kg=70" \
  -H "Accept-Language: de-DE"
# {"distance":"42,2 km","temperature":"22°C","weight":"70 kg",...}
```

---

## Related

- `documentation/categories/i18n/workers-intl-edge-locale.md`
- `documentation/categories/i18n/workers-date-time-formatting-intl-edge.md`
- `documentation/categories/i18n/accept-language-negotiation.md`
- `documentation/categories/i18n/workers-currency-formatting-intl-edge.md`

---

## Sources

- MDN: [Intl.NumberFormat](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat)
- TC39 ECMA-402: [Sanctioned Unit Identifiers](https://tc39.es/ecma402/#table-sanctioned-single-unit-identifiers)
- CLDR: [Measurement Systems](https://cldr.unicode.org/development/development-process/design-proposals/measurement-systems)
- Unicode: [BCP 47 -u- Extensions](https://unicode.org/reports/tr35/#u_Extension)
- Cloudflare Docs: [Workers Runtime APIs](https://developers.cloudflare.com/workers/runtime-apis/)
