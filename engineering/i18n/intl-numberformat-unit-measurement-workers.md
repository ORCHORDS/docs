# Intl.NumberFormat Unit Style Measurement Formatting Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A example project e-commerce Worker displays product dimensions, weights, speeds, and data sizes to a global audience. Displaying `12.5 kg` to a US user and `27.6 lb` to a UK user, `32 km` vs `20 mi`, or `1.5 GB` with locale-appropriate number grouping all require `Intl.NumberFormat` with `style: "unit"`. Developers often reach for a static conversion table and string concatenation, producing outputs that ignore the locale's preferred number system, grouping separator, and decimal marker.

---

## Context

`Intl.NumberFormat` with `style: "unit"` formats a number with an attached unit label in the correct grammatical form for the target locale — singular, plural, long or short form, with locale-appropriate separators. The `unit` option accepts a well-known unit identifier from ECMA-402 (itself derived from the CLDR unit identifiers). Unit **conversion** (kg → lb) is a separate concern handled before calling `Intl.NumberFormat`.

On the example project platform, a Worker receives a measurement in SI base units (kg, m, m/s, bytes), converts to the preferred measurement system for the user's locale, then formats with `Intl.NumberFormat` with `style: "unit"`. Conversion factors and unit-system preferences are cached in KV, keyed by BCP 47 region subtag.

---

## ECMA-402 Unit Identifiers Reference

The complete list is defined in ECMA-402 §6.5.6. Key identifiers for e-commerce and platform use:

| Category        | Identifiers                                                          |
|-----------------|----------------------------------------------------------------------|
| Mass            | `kilogram`, `gram`, `milligram`, `pound`, `ounce`, `stone`           |
| Length          | `meter`, `centimeter`, `millimeter`, `kilometer`, `mile`, `inch`, `foot`, `yard` |
| Area            | `square-meter`, `square-centimeter`, `square-kilometer`, `square-mile`, `square-foot`, `acre`, `hectare` |
| Volume          | `liter`, `milliliter`, `gallon`, `fluid-ounce`, `cup`, `tablespoon`, `teaspoon` |
| Speed           | `kilometer-per-hour`, `mile-per-hour`, `meter-per-second`            |
| Digital storage | `byte`, `kilobyte`, `megabyte`, `gigabyte`, `terabyte`, `petabyte`, `bit`, `kilobit`, `megabit`, `gigabit` |
| Temperature     | `celsius`, `fahrenheit`, `kelvin`                                    |
| Duration        | `year`, `month`, `week`, `day`, `hour`, `minute`, `second`, `millisecond` |
| Energy          | `kilowatt-hour`, `joule`, `calorie`, `kilojoule`                     |

Compound units like `kilometer-per-hour` use the `<numerator>-per-<denominator>` syntax.

---

## Basic Unit Formatting

```typescript
// src/lib/unit-format.ts

export type UnitDisplay = "short" | "long" | "narrow";

/**
 * Format a pre-converted value with a unit label in the target locale.
 */
export function formatUnit(
  value: number,
  unit: string,
  locale: string,
  display: UnitDisplay = "short"
): string {
  return new Intl.NumberFormat(locale, {
    style: "unit",
    unit,
    unitDisplay: display,
    maximumFractionDigits: 2,
  }).format(value);
}

// Examples:
// formatUnit(27.6, "pound", "en-US")          → "27.6 lb"
// formatUnit(27.6, "pound", "en-US", "long")  → "27.6 pounds"
// formatUnit(12.5, "kilogram", "de-DE")        → "12,5 kg"
// formatUnit(12.5, "kilogram", "ar-EG")        → "١٢٫٥ كغم"
// formatUnit(55, "mile-per-hour", "en-GB")     → "55 mph"
// formatUnit(1536, "megabyte", "zh-Hans")      → "1,536兆字节"
```

---

## Measurement System Detection and Conversion

The `measurementSystem` field on `Intl.Locale` (proposed, available via `maximize()` in V8) is not yet stable. Rely instead on a KV-backed region-to-system map.

```typescript
// src/lib/measurement-system.ts

export type MeasurementSystem = "metric" | "us" | "uk";

// These are the only three regions that use non-metric for everyday measurements.
const US_REGIONS = new Set(["US", "LR", "MM"]);
const UK_REGIONS = new Set(["GB"]); // UK uses metric for most, imperial for speed/distance

export function measurementSystemForLocale(locale: string): MeasurementSystem {
  try {
    const region = new Intl.Locale(locale).maximize().region;
    if (!region) return "metric";
    if (US_REGIONS.has(region)) return "us";
    if (UK_REGIONS.has(region)) return "uk";
    return "metric";
  } catch {
    return "metric";
  }
}

export interface MassResult {
  value: number;
  unit: string; // ECMA-402 unit identifier
}

/** Convert a mass in kg to the system-preferred unit. */
export function convertMass(kg: number, system: MeasurementSystem): MassResult {
  if (system === "us") return { value: kg * 2.20462, unit: "pound" };
  if (system === "uk") {
    // UK: stone + pound for people; kg for products — use kg
    return { value: kg, unit: "kilogram" };
  }
  return { value: kg, unit: "kilogram" };
}

export interface LengthResult {
  value: number;
  unit: string;
}

/** Convert a length in meters to the system-preferred unit. */
export function convertLength(
  meters: number,
  system: MeasurementSystem
): LengthResult {
  if (system === "us") {
    if (meters < 0.3) return { value: meters * 39.3701, unit: "inch" };
    if (meters < 1) return { value: meters * 3.28084, unit: "foot" };
    if (meters < 1609.34) return { value: meters * 1.09361, unit: "yard" };
    return { value: meters / 1609.34, unit: "mile" };
  }
  if (system === "uk") {
    if (meters >= 1609.34) return { value: meters / 1609.34, unit: "mile" };
    return { value: meters * 100, unit: "centimeter" };
  }
  if (meters < 0.01) return { value: meters * 1000, unit: "millimeter" };
  if (meters < 1) return { value: meters * 100, unit: "centimeter" };
  if (meters < 1000) return { value: meters, unit: "meter" };
  return { value: meters / 1000, unit: "kilometer" };
}

/** Convert temperature from Celsius to system preference. */
export function convertTemperature(
  celsius: number,
  system: MeasurementSystem
): { value: number; unit: string } {
  if (system === "us") {
    return { value: celsius * 9 / 5 + 32, unit: "fahrenheit" };
  }
  return { value: celsius, unit: "celsius" };
}
```

---

## Worker Handler: Formatting Product Measurements

```typescript
// src/index.ts

import { measurementSystemForLocale, convertMass, convertLength, convertTemperature } from "./lib/measurement-system";
import { formatUnit } from "./lib/unit-format";

export interface Env {
  DB: D1Database;
  FORMAT_CACHE: KVNamespace;
}

interface ProductRow {
  product_id: string;
  name: string;
  weight_kg: number;
  length_m: number;
  width_m: number;
  height_m: number;
  temperature_c: number | null;
  data_bytes: bigint | null;
}

function formatDataSize(bytes: number, locale: string): string {
  const units: [number, string][] = [
    [1e15, "petabyte"],
    [1e12, "terabyte"],
    [1e9,  "gigabyte"],
    [1e6,  "megabyte"],
    [1e3,  "kilobyte"],
    [1,    "byte"],
  ];
  for (const [threshold, unit] of units) {
    if (bytes >= threshold) {
      return new Intl.NumberFormat(locale, {
        style: "unit",
        unit,
        unitDisplay: "short",
        maximumFractionDigits: 1,
      }).format(bytes / threshold);
    }
  }
  return new Intl.NumberFormat(locale, {
    style: "unit",
    unit: "byte",
    unitDisplay: "short",
  }).format(bytes);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const productId = url.searchParams.get("product_id");
    const locale = request.headers.get("X-Detected-Locale")
      ?? url.searchParams.get("locale")
      ?? "en-US";

    if (!productId) return new Response("product_id required", { status: 400 });

    const cacheKey = `product-fmt:${productId}:${locale}`;
    const cached = await env.FORMAT_CACHE.get(cacheKey, "json") as Record<string, string> | null;
    if (cached) {
      return new Response(JSON.stringify(cached), {
        headers: { "Content-Type": "application/json", "X-Cache": "HIT" },
      });
    }

    const row = await env.DB
      .prepare("SELECT * FROM products WHERE product_id = ?")
      .bind(productId)
      .first<ProductRow>();

    if (!row) return new Response("Not found", { status: 404 });

    const system = measurementSystemForLocale(locale);

    const mass = convertMass(row.weight_kg, system);
    const len  = convertLength(row.length_m, system);
    const wid  = convertLength(row.width_m, system);
    const hgt  = convertLength(row.height_m, system);

    const formatted: Record<string, string> = {
      weight: formatUnit(mass.value, mass.unit, locale),
      length: formatUnit(len.value, len.unit, locale),
      width:  formatUnit(wid.value, wid.unit, locale),
      height: formatUnit(hgt.value, hgt.unit, locale),
    };

    if (row.temperature_c !== null) {
      const temp = convertTemperature(row.temperature_c, system);
      formatted.temperature = formatUnit(temp.value, temp.unit, locale);
    }

    if (row.data_bytes !== null) {
      formatted.dataSize = formatDataSize(Number(row.data_bytes), locale);
    }

    await env.FORMAT_CACHE.put(cacheKey, JSON.stringify(formatted), {
      expirationTtl: 300, // 5 min — product data can change
    });

    return new Response(JSON.stringify({ ...formatted, locale, measurementSystem: system }), {
      headers: { "Content-Type": "application/json", "X-Cache": "MISS" },
    });
  },
};
```

---

## Formatting Parts for Custom Rendering

`Intl.NumberFormat.prototype.formatToParts` lets you separate the numeric value from the unit label for custom styling (e.g., rendering the unit in a smaller font).

```typescript
// src/lib/unit-parts.ts

export interface UnitParts {
  number: string;      // e.g. "27.6"
  literal: string;     // e.g. " "
  unit: string;        // e.g. "lb"
}

export function formatUnitToParts(
  value: number,
  unit: string,
  locale: string,
  display: "short" | "long" | "narrow" = "short"
): UnitParts {
  const fmt = new Intl.NumberFormat(locale, {
    style: "unit",
    unit,
    unitDisplay: display,
    maximumFractionDigits: 2,
  });

  const parts = fmt.formatToParts(value);
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";

  return {
    number: parts
      .filter((p) => ["integer", "decimal", "fraction", "group", "minusSign"].includes(p.type))
      .map((p) => p.value)
      .join(""),
    literal: get("literal"),
    unit: get("unit"),
  };
}

// formatUnitToParts(12.5, "kilogram", "de-DE")
// → { number: "12,5", literal: " ", unit: "kg" }
// Render as: <span class="value">12,5</span><span class="unit"> kg</span>
```

---

## Anti-patterns

- **Concatenating a number string with a static unit abbreviation.** `"${weight} kg"` ignores locale number separators, plural rules (some locales use different forms), and right-to-left unit placement.
- **Using `style: "unit"` with `currency` or `percent` style simultaneously.** Each call to `Intl.NumberFormat` has exactly one `style`. For compound displays (e.g., price-per-kilogram), format each part separately and concatenate.
- **Assuming the ECMA-402 unit identifier matches the display abbreviation.** `"kilometer-per-hour"` renders as `"km/h"` in most locales but as `"kph"` or `"км/ч"` in others. Do not compare the formatted string against the identifier.
- **Passing arbitrary unit strings.** Only the identifiers enumerated in ECMA-402 §6.5.6 are valid. Unrecognized identifiers throw a `RangeError`.
- **Hardcoding conversion factors in the response.** Products have an authoritative SI value in D1. Convert at formatting time, not at storage time, so no data migration is needed when adding a new locale cluster.

---

## Gotchas

- `"stone"` (for UK body weight) is in the ECMA-402 list but is formatted poorly in most locales' CLDR data — the long form may say "stones" regardless of quantity. Check browser and V8 ICU data version before relying on it.
- `"fluid-ounce"` formats differently for US fluid ounces vs. UK fluid ounces — the CLDR data for `en-GB` will render "fl oz" (UK fl oz ≈ 28.4 ml) but the numeric value you pass must already be in UK fl oz. There is no separate `"uk-fluid-ounce"` identifier; the unit identifier always represents the conventional value for that locale.
- The `unitDisplay: "narrow"` option produces the most compact form and may drop the space between number and unit (e.g., `"5km"` vs `"5 km"`). This is correct per CLDR data and locale convention.
- `BigInt` values from D1 (for byte counts stored as `INTEGER`) must be converted to `Number` before passing to `Intl.NumberFormat`. Values over 2⁵³ lose precision, but byte counts for files in that range are not common.
- On older V8 versions (pre-2023) bundled in some Workers environments, not all ECMA-402 unit identifiers are supported. Use `Intl.supportedValuesOf("unit")` to enumerate the available identifiers at runtime.

---

## Verification

```typescript
// tests/unit-format.test.ts
import { describe, it, expect } from "vitest";
import { formatUnit } from "../src/lib/unit-format";
import { convertMass, measurementSystemForLocale } from "../src/lib/measurement-system";

describe("unit formatting", () => {
  it("formats kilograms with German decimal comma", () => {
    expect(formatUnit(12.5, "kilogram", "de-DE")).toBe("12,5 kg");
  });

  it("converts kg to lb for US locale", () => {
    const system = measurementSystemForLocale("en-US");
    expect(system).toBe("us");
    const { value, unit } = convertMass(10, system);
    expect(unit).toBe("pound");
    expect(formatUnit(value, unit, "en-US")).toMatch(/22\.0\d lb/);
  });

  it("formats data size in megabytes", () => {
    const bytes = 1_500_000;
    // 1.5 megabytes
    expect(formatUnit(bytes / 1e6, "megabyte", "en-US")).toBe("1.5 MB");
  });

  it("uses Arabic-Indic digits for ar-EG", () => {
    const result = formatUnit(12.5, "kilogram", "ar-EG");
    // Arabic-Indic digit ١ is U+0661
    expect(result).toMatch(/[١-٩]/);
  });
});
```

Run: `npx vitest run tests/unit-format.test.ts`

Verify that `Intl.supportedValuesOf("unit")` in the Workers runtime includes the identifiers you use:

```typescript
// Quick runtime check (add temporarily to Worker init)
const supported = Intl.supportedValuesOf("unit");
console.log("Units supported:", supported.length);
console.log("Has kilometer-per-hour:", supported.includes("kilometer-per-hour"));
```

---

## Related

- `cldr-unit-preferences-conversion-and-user-overrides.md`
- `measurement-system-unit-conversion-2026.md`
- `number-currency-formatting-2026.md`
- `intl-numberformat-explicit-rounding-policy.md`
- `intl-supportedvaluesof-capability-enumeration.md`

---

## Sources

- ECMA-402 §6.5.6, Measurement Unit Identifiers: https://tc39.es/ecma402/#sec-issanctionedsingleunitidentifier
- CLDR Unit Identifiers: https://github.com/unicode-org/cldr/blob/main/common/validity/unit.xml
- MDN `Intl.NumberFormat` `style: "unit"`: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat/NumberFormat#unit
- `Intl.supportedValuesOf("unit")`: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/supportedValuesOf
- Cloudflare Workers ECMA-402 support: https://developers.cloudflare.com/workers/runtime-apis/web-standards/
